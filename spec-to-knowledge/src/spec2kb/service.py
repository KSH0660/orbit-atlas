"""Workspace service: every operation of the web UI / CLI (upload, process, reprocess, edit, export)."""

from __future__ import annotations

import io
import logging
import posixpath
import re
import shutil
import time
from pathlib import Path
from typing import Any, BinaryIO

from . import __version__
from .config import Settings
from .exporter import KbItem, build_kb, zip_tree
from .exporter.markdown import MarkdownRenderer
from .exporter.package import DocumentExporter
from .htmlrender import render_markdown
from .jobs import BusyError, Job, JobContext, JobManager
from .parser import PdfDoc, PdfOpenError, apply_overlay, assemble, carry_over_descriptions, parse_pages_raw
from .parser.pdfdoc import PDFIUM_LOCK, validate_pdf_bytes
from .parser.pipeline import RawPage
from .profiles import Profile, ProfileError, ProfileStore, deep_merge
from .providers import Provider, ProviderError, ProviderStore
from .schema import CanonicalDocument, Issue, SourceInfo, utcnow
from .store import DocRecord, DocumentStore
from .util import parse_page_range, safe_join, sha256_file, slugify
from .validator import apply_validation, check_export, report_markdown, summarize
from .vision import VisionCache, run_ocr, run_vision

log = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Workspace:
    def __init__(self, settings: Settings):
        settings.ensure_dirs()
        self.settings = settings
        self.profiles = ProfileStore(settings.profiles_dir)
        self.providers = ProviderStore(settings.providers_file, settings.allow_api_key_storage,
                                       settings.providers_seed)
        self.docs = DocumentStore(settings.docs_dir)
        self.jobs = JobManager(settings.docs_dir, settings.workers)
        self.cache = VisionCache(settings.cache_dir / "vision")
        self.exports_dir = settings.data_dir / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        for doc_id in set(self.jobs.recover()):
            if self.docs.exists(doc_id):
                rec = self.docs.record(doc_id)
                if rec.status in ("queued", "processing"):
                    rec.status = "failed"
                    rec.error = "서버 재시작으로 처리가 중단되었습니다. 다시 실행하세요."
                    self.docs.save_record(rec)

    def close(self) -> None:
        self.jobs.shutdown()

    # ------------------------------------------------------------------------------------
    # profiles / providers
    # ------------------------------------------------------------------------------------
    def resolve_profile(self, rec: DocRecord) -> Profile:
        try:
            return self.profiles.resolve(rec.profile_id, rec.options or None)
        except ProfileError as exc:
            raise ServiceError(str(exc)) from exc

    def provider_for(self, profile: Profile, ocr: bool = False) -> tuple[Provider | None, str]:
        pid = (profile.vision.ocr_provider if ocr else "") or profile.vision.provider or self.settings.default_provider
        try:
            return self.providers.provider(pid), ""
        except ProviderError as exc:
            return None, str(exc)

    # ------------------------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------------------------
    def add_document(self, filename: str, stream: BinaryIO, profile_id: str = "jedec",
                     options: dict[str, Any] | None = None) -> DocRecord:
        filename = Path(filename or "document.pdf").name[:200]
        if not filename.lower().endswith(".pdf"):
            raise ServiceError(f"PDF 파일만 업로드할 수 있습니다: {filename}")
        if not self.profiles.exists(profile_id):
            raise ServiceError(f"프로필을 찾을 수 없습니다: {profile_id}")
        doc_id = self.docs.new_id()
        d = self.docs.dir(doc_id)
        d.mkdir(parents=True)
        src = self.docs.source_path(doc_id)
        limit = self.settings.max_upload_mb * 1024 * 1024
        size = 0
        head = b""
        try:
            with open(src, "wb") as fh:
                while True:
                    chunk = stream.read(1 << 20)
                    if not chunk:
                        break
                    if not head:
                        head = chunk[:1024]
                    size += len(chunk)
                    if size > limit:
                        raise ServiceError(f"파일이 너무 큽니다 (최대 {self.settings.max_upload_mb} MB).", 413)
                    fh.write(chunk)
            if not validate_pdf_bytes(head):
                raise ServiceError(f"PDF 형식이 아닙니다: {filename}")
            try:
                with PdfDoc(src) as pdf:
                    pages = pdf.page_count
                    meta = pdf.metadata()
            except PdfOpenError as exc:
                raise ServiceError(f"{filename}: {exc}") from exc
            if pages == 0:
                raise ServiceError(f"{filename}: 페이지가 없는 PDF입니다.")
        except BaseException:
            shutil.rmtree(d, ignore_errors=True)
            raise
        sha = sha256_file(src)
        dup = next((r.id for r in self.docs.list() if r.sha256 == sha and r.id != doc_id), "")
        rec = DocRecord(id=doc_id, filename=filename, title=meta.get("Title", "").strip() or Path(filename).stem,
                        profile_id=profile_id, options=options or {}, sha256=sha, size_bytes=size,
                        page_count=pages, duplicate_of=dup)
        self.docs.save_record(rec)
        return rec

    def get_record(self, doc_id: str) -> DocRecord:
        try:
            return self.docs.record(doc_id)
        except (KeyError, FileNotFoundError) as exc:
            raise ServiceError("문서를 찾을 수 없습니다.", 404) from exc

    def update_document(self, doc_id: str, profile_id: str | None = None, options: dict[str, Any] | None = None,
                        title: str | None = None) -> DocRecord:
        self._ensure_idle(doc_id)
        rec = self.get_record(doc_id)
        if profile_id is not None:
            if not self.profiles.exists(profile_id):
                raise ServiceError(f"프로필을 찾을 수 없습니다: {profile_id}")
            rec.profile_id = profile_id
        if options is not None:
            rec.options = options
            try:
                self.profiles.resolve(rec.profile_id, options or None)
            except ProfileError as exc:
                raise ServiceError(str(exc)) from exc
            pr = (options.get("parsing") or {}).get("page_range")
            if pr:
                try:
                    parse_page_range(pr, rec.page_count)
                except ValueError as exc:
                    raise ServiceError(str(exc)) from exc
        if title is not None:
            rec.title = title.strip() or rec.title
        self.docs.save_record(rec)
        return rec

    def delete_document(self, doc_id: str) -> None:
        self._ensure_idle(doc_id)
        self.get_record(doc_id)
        self.docs.delete(doc_id)

    def _ensure_idle(self, doc_id: str) -> None:
        if self.jobs.active_job(doc_id):
            raise ServiceError("처리 중인 문서입니다. 작업이 끝난 뒤 다시 시도하세요.", 409)

    def doc_summary(self, rec: DocRecord) -> dict[str, Any]:
        job = self.jobs.active_job(rec.id)
        data = rec.model_dump()
        data["active_job"] = job.model_dump() if job else None
        return data

    # ------------------------------------------------------------------------------------
    # processing jobs
    # ------------------------------------------------------------------------------------
    def _submit(self, doc_id: str, type_: str, title: str, fn, params: dict[str, Any]) -> Job:
        rec = self.get_record(doc_id)
        try:
            job = self.jobs.submit(type_, doc_id, fn, title=title, params=params, on_finish=self._on_finish)
        except BusyError as exc:
            raise ServiceError(str(exc), 409) from exc
        rec.status = "processing"
        rec.last_job_id = job.id
        rec.error = ""
        self.docs.save_record(rec)
        return job

    def _on_finish(self, job: Job) -> None:
        if not self.docs.exists(job.doc_id):
            return
        rec = self.docs.record(job.doc_id)
        has_canonical = (self.docs.dir(job.doc_id) / "canonical.json").exists()
        if job.status == "done":
            rec.status = "ready"
            rec.processed_at = utcnow()
            rec.error = ""
        elif job.status == "cancelled":
            rec.status = "ready" if has_canonical else "cancelled"
            rec.error = job.error
        else:
            rec.status = "ready" if (has_canonical and job.type != "process") else "failed"
            rec.error = job.error
        doc = self.docs.canonical(job.doc_id) if has_canonical else None
        if doc is not None:
            rec.summary = summarize(doc)
            if doc.effective_metadata().title:
                rec.title = doc.effective_metadata().title
        self.docs.save_record(rec)

    def start_process(self, doc_id: str) -> Job:
        self.get_record(doc_id)
        return self._submit(doc_id, "process", "전체 변환", lambda ctx: self._process(ctx, doc_id, None), {})

    def start_reprocess_pages(self, doc_id: str, pages: list[int]) -> Job:
        rec = self.get_record(doc_id)
        if not (self.docs.dir(doc_id) / "canonical.json").exists():
            raise ServiceError("먼저 전체 변환을 실행하세요.")
        pages = sorted({int(p) for p in pages if 1 <= int(p) <= rec.page_count})
        if not pages:
            raise ServiceError("재처리할 페이지를 선택하세요.")
        return self._submit(doc_id, "reprocess_pages", f"페이지 재처리 ({', '.join(map(str, pages[:10]))})",
                            lambda ctx: self._process(ctx, doc_id, pages), {"pages": pages})

    def start_redescribe(self, doc_id: str, figure_ids: list[str], image_type: str | None = None,
                         prompt_extra: str | None = None) -> Job:
        doc = self._canonical(doc_id)
        figs = [f for f in doc.figures if f.id in set(figure_ids)]
        if not figs:
            raise ServiceError("재처리할 그림을 선택하세요.")
        rec = self.get_record(doc_id)
        profile = self.resolve_profile(rec)
        if image_type and not profile.image_type(image_type):
            raise ServiceError(f"프로필에 없는 이미지 유형입니다: {image_type}")
        with self.docs.lock(doc_id):
            overlay = self.docs.overlay(doc_id)
            for f in figs:
                ed = overlay["figures"].setdefault(f.id, {})
                if image_type:
                    ed["image_type"] = image_type
                if prompt_extra is not None:
                    ed["prompt_extra"] = prompt_extra
                ed.pop("description_override", None)
                ed["edited_at"] = utcnow()
            self.docs.save_overlay(doc_id, overlay)
        ids = [f.id for f in figs]
        return self._submit(doc_id, "redescribe", f"그림 재해석 ({', '.join(ids[:5])})",
                            lambda ctx: self._redescribe(ctx, doc_id, ids), {"figures": ids})

    def _process(self, ctx: JobContext, doc_id: str, pages: list[int] | None) -> dict[str, Any]:
        rec = self.get_record(doc_id)
        profile = self.resolve_profile(rec)
        src = self.docs.source_path(doc_id)
        assets = self.docs.assets_dir(doc_id)
        previous = self.docs.canonical(doc_id)
        t0 = time.monotonic()
        if pages is None:
            try:
                selected = parse_page_range(profile.parsing.page_range, rec.page_count)
            except ValueError as exc:
                raise ServiceError(str(exc)) from exc
            ctx.log(f"전체 변환 시작: {len(selected)}쪽, 프로필 '{profile.id}'")
            raw, furniture, _ = parse_pages_raw(src, profile, selected, assets, progress=ctx.progress,
                                                cancel=ctx.cancelled)
            existing: dict[int, RawPage] = {}
        else:
            existing = self.docs.load_raw(doc_id)
            furniture = (previous.processing.stats.get("furniture") if previous else None)
            body = float(previous.processing.stats.get("body_size", 0)) if previous else 0.0
            ctx.log(f"페이지 재처리 시작: {pages}")
            raw, furniture, _ = parse_pages_raw(src, profile, pages, assets, furniture=furniture, body_hint=body,
                                                progress=ctx.progress, cancel=ctx.cancelled)
        ocr_provider, ocr_err = self.provider_for(profile, ocr=True)
        ocr_pages = run_ocr(raw, profile, ocr_provider, assets, force=True, progress=ctx.progress,
                            cancel=ctx.cancelled)
        if ocr_pages:
            ctx.log(f"OCR 완료: {ocr_pages}")
        elif ocr_err and any(rp.info.kind == "scanned" for rp in raw.values()):
            ctx.log(f"OCR Provider 오류: {ocr_err}")
        merged_raw = dict(existing)
        merged_raw.update(raw)
        ctx.progress("assemble", 0, 1, "문서 조립")
        with self.docs.lock(doc_id):
            if pages is None:
                self.docs.clear_raw(doc_id)
            self.docs.save_raw(doc_id, raw)
        doc = self._assemble(rec, profile, merged_raw, furniture or [], previous)
        doc.processing.started_at = previous.processing.started_at if (previous and pages) else utcnow()
        provider, perr = self.provider_for(profile)
        stats = run_vision(doc, profile, provider, assets, self.cache, progress=ctx.progress,
                           cancel=ctx.cancelled, provider_error=perr)
        ctx.log(f"그림 설명: 생성 {stats['described']}, 캐시 {stats['cached']}, 실패 {stats['failed']}, 생략 {stats['skipped']}")
        if provider is not None:
            doc.processing.vision_provider = provider.id
            doc.processing.vision_model = provider.model
        ctx.progress("validate", 0, 1, "검증")
        self._validate_and_save(doc_id, doc, profile)
        doc.processing.finished_at = utcnow()
        doc.processing.duration_s = round(time.monotonic() - t0, 2)
        with self.docs.lock(doc_id):
            self.docs.save_canonical(doc_id, doc)
        ctx.progress("save", 1, 1, "저장 완료")
        s = summarize(doc)
        ctx.log(f"완료: 오류 {s['errors']}, 경고 {s['warnings']}, 표 {s['tables']}, 그림 {s['figures']}")
        return {"summary": s, "vision": stats, "pages": pages or "all"}

    def _assemble(self, rec: DocRecord, profile: Profile, raw: dict[int, RawPage], furniture: list[str],
                  previous: CanonicalDocument | None) -> CanonicalDocument:
        with PdfDoc(self.docs.source_path(rec.id)) as pdf:
            pdf_meta = pdf.metadata()
        source = SourceInfo(filename=rec.filename, sha256=rec.sha256, size_bytes=rec.size_bytes,
                            page_count=rec.page_count, pdf_metadata=pdf_meta)
        slug = slugify(rec.title or rec.filename, 40)
        doc = assemble(rec.id, slug, source, profile, raw, furniture)
        carry_over_descriptions(doc, previous)
        overlay = self.docs.overlay(rec.id)
        doc.issues.extend(apply_overlay(doc, overlay))
        return doc

    def _redescribe(self, ctx: JobContext, doc_id: str, figure_ids: list[str]) -> dict[str, Any]:
        rec = self.get_record(doc_id)
        profile = self.resolve_profile(rec)
        doc = self._canonical(doc_id)
        overlay = self.docs.overlay(doc_id)
        apply_overlay(doc, overlay)
        for fid in figure_ids:
            f = doc.figure(fid)
            if f is not None:
                f.description_override = None
        provider, perr = self.provider_for(profile)
        stats = run_vision(doc, profile, provider, self.docs.assets_dir(doc_id), self.cache,
                           figure_ids=set(figure_ids), force=True, progress=ctx.progress, cancel=ctx.cancelled,
                           provider_error=perr, bypass_cache=True)
        ctx.log(f"그림 재해석: 생성 {stats['described']}, 실패 {stats['failed']}")
        self._validate_and_save(doc_id, doc, profile)
        return {"vision": stats, "figures": figure_ids}

    # ------------------------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------------------------
    def _export_issues(self, doc: CanonicalDocument, profile: Profile, assets: Path) -> list[Issue]:
        exp = DocumentExporter(doc, profile, assets, "doc", profile.markdown.layout, utcnow()).build()
        files = {f.path: f.content for f in exp.files}
        issues = check_export(files, set(files) | set(exp.assets), profile.markdown.layout,
                              profile.markdown.frontmatter_fields if profile.markdown.frontmatter else [])
        for name in exp.missing_assets:
            issues.append(Issue(id=f"export-asset-{name}", severity="error", code="asset_missing",
                                message=f"이미지 파일이 없습니다: {name}", source="export"))
        for i in issues:
            i.source = "export"
        return issues

    def _validate_and_save(self, doc_id: str, doc: CanonicalDocument, profile: Profile) -> None:
        assets = self.docs.assets_dir(doc_id)
        overlay = self.docs.overlay(doc_id)
        apply_validation(doc, profile, assets, overlay.get("issues"), self._export_issues(doc, profile, assets))
        with self.docs.lock(doc_id):
            self.docs.save_canonical(doc_id, doc)

    def revalidate(self, doc_id: str) -> dict[str, Any]:
        self._ensure_idle(doc_id)
        rec = self.get_record(doc_id)
        doc = self._canonical(doc_id)
        self._validate_and_save(doc_id, doc, self.resolve_profile(rec))
        rec.summary = summarize(doc)
        self.docs.save_record(rec)
        return rec.summary

    # ------------------------------------------------------------------------------------
    # edits
    # ------------------------------------------------------------------------------------
    def _canonical(self, doc_id: str) -> CanonicalDocument:
        self.get_record(doc_id)
        doc = self.docs.canonical(doc_id)
        if doc is None:
            raise ServiceError("아직 변환되지 않은 문서입니다. 먼저 변환을 실행하세요.", 409)
        return doc

    def _edit(self, doc_id: str, kind: str, ref: str, fields: dict[str, Any]) -> CanonicalDocument:
        self._ensure_idle(doc_id)
        rec = self.get_record(doc_id)
        profile = self.resolve_profile(rec)
        with self.docs.lock(doc_id):
            doc = self._canonical(doc_id)
            target = {"blocks": doc.block, "tables": doc.table, "figures": doc.figure}[kind](ref)
            if target is None:
                raise ServiceError(f"항목을 찾을 수 없습니다: {ref}", 404)
            overlay = self.docs.overlay(doc_id)
            ed = overlay[kind].setdefault(ref, {})
            for k, v in fields.items():
                if v is None:
                    ed.pop(k, None)
                else:
                    ed[k] = v
            if not [k for k in ed if k != "edited_at"]:
                overlay[kind].pop(ref, None)
            else:
                ed["edited_at"] = utcnow()
            self.docs.save_overlay(doc_id, overlay)
            apply_overlay(doc, overlay)
            if kind == "blocks" and "md_override" in fields and fields["md_override"] is None:
                target.md_override = None
            if kind == "tables" and fields.get("md_override", 0) is None:
                target.md_override = None
            if kind == "figures":
                for k in ("md_override", "description_override"):
                    if k in fields and fields[k] is None:
                        setattr(target, k, None)
                if "image_type" in fields and fields["image_type"] is None:
                    target.image_type_source = "rule"
            self._validate_and_save(doc_id, doc, profile)
        rec.summary = summarize(doc)
        self.docs.save_record(rec)
        return doc

    def edit_block(self, doc_id: str, block_id: str, md_override: str | None) -> CanonicalDocument:
        return self._edit(doc_id, "blocks", block_id, {"md_override": md_override})

    def edit_table(self, doc_id: str, table_id: str, md_override: str | None) -> CanonicalDocument:
        return self._edit(doc_id, "tables", table_id, {"md_override": md_override})

    def edit_figure(self, doc_id: str, figure_id: str, fields: dict[str, Any]) -> CanonicalDocument:
        allowed = {k: v for k, v in fields.items() if k in ("md_override", "description_override", "image_type",
                                                           "prompt_extra")}
        if allowed.get("image_type"):
            profile = self.resolve_profile(self.get_record(doc_id))
            if not profile.image_type(allowed["image_type"]):
                raise ServiceError(f"프로필에 없는 이미지 유형입니다: {allowed['image_type']}")
        return self._edit(doc_id, "figures", figure_id, allowed)

    def edit_metadata(self, doc_id: str, fields: dict[str, Any]) -> CanonicalDocument:
        self._ensure_idle(doc_id)
        rec = self.get_record(doc_id)
        with self.docs.lock(doc_id):
            doc = self._canonical(doc_id)
            overlay = self.docs.overlay(doc_id)
            for k in ("title", "doc_number", "revision", "date", "publisher"):
                if k in fields:
                    v = (fields[k] or "").strip()
                    if v:
                        overlay["metadata"][k] = v
                    else:
                        overlay["metadata"].pop(k, None)
            self.docs.save_overlay(doc_id, overlay)
            doc.metadata_override = dict(overlay["metadata"])
            self.docs.save_canonical(doc_id, doc)
        if doc.effective_metadata().title:
            rec.title = doc.effective_metadata().title
            self.docs.save_record(rec)
        return doc

    def set_issue_status(self, doc_id: str, issue_id: str, status: str) -> None:
        if status not in ("open", "ignored", "resolved"):
            raise ServiceError("잘못된 상태입니다.")
        self._ensure_idle(doc_id)
        rec = self.get_record(doc_id)
        with self.docs.lock(doc_id):
            doc = self._canonical(doc_id)
            issue = next((i for i in doc.issues if i.id == issue_id), None)
            if issue is None:
                raise ServiceError("이슈를 찾을 수 없습니다.", 404)
            overlay = self.docs.overlay(doc_id)
            if status == "open":
                overlay["issues"].pop(issue_id, None)
            else:
                overlay["issues"][issue_id] = status
            self.docs.save_overlay(doc_id, overlay)
            issue.status = status  # type: ignore[assignment]
            self.docs.save_canonical(doc_id, doc)
        rec.summary = summarize(doc)
        self.docs.save_record(rec)

    # ------------------------------------------------------------------------------------
    # views
    # ------------------------------------------------------------------------------------
    def asset_url_mapper(self, doc_id: str, doc: CanonicalDocument):
        names: dict[str, str] = {}
        for f in doc.figures:
            if f.asset:
                names[MarkdownRenderer.figure_asset_name(f)] = f.asset
        for t in doc.tables:
            for i, p in enumerate(t.parts):
                if p.snapshot:
                    names[MarkdownRenderer.table_asset_name(t, i)] = p.snapshot
        return lambda name: f"/api/docs/{doc_id}/assets/{names.get(name, name)}"

    def page_view(self, doc_id: str, page_no: int) -> dict[str, Any]:
        rec = self.get_record(doc_id)
        doc = self._canonical(doc_id)
        profile = self.resolve_profile(rec)
        page = doc.page(page_no)
        if page is None:
            raise ServiceError("페이지가 없습니다.", 404)
        renderer = MarkdownRenderer(doc, profile, self.asset_url_mapper(doc_id, doc))
        blocks = []
        for b in doc.blocks:
            pages = set(b.pages or [b.page])
            if b.type == "table" and b.ref:
                t = doc.table(b.ref)
                if t:
                    pages |= {p.page for p in t.parts}
            if page_no not in pages:
                continue
            md = renderer.render_block(b)
            item: dict[str, Any] = {"block": b.model_dump(exclude={"hints"}), "markdown": md,
                                    "html": render_markdown(md), "edited": b.md_override is not None}
            if b.type == "table" and b.ref:
                t = doc.table(b.ref)
                item["table"] = t.model_dump(exclude={"cells"}) if t else None
                item["edited"] = bool(t and t.md_override is not None)
                item["generated_markdown"] = MarkdownRenderer(doc, profile).render_table(
                    t.model_copy(update={"md_override": None})) if t else ""
            elif b.type == "figure" and b.ref:
                f = doc.figure(b.ref)
                item["figure"] = f.model_dump() if f else None
                item["edited"] = bool(f and (f.md_override is not None or f.description_override is not None))
            else:
                item["generated_markdown"] = MarkdownRenderer(doc, profile).render_block(
                    b.model_copy(update={"md_override": None}))
            blocks.append(item)
        issues = [i.model_dump() for i in doc.issues if i.page == page_no]
        return {"page": page.model_dump(), "blocks": blocks, "issues": issues,
                "page_count": doc.source.page_count,
                "image_types": [{"id": r.id, "label": r.label} for r in profile.vision.image_types if r.enabled]}

    def pages_overview(self, doc_id: str) -> list[dict[str, Any]]:
        doc = self._canonical(doc_id)
        counts: dict[int, dict[str, int]] = {}
        for i in doc.issues:
            if i.page is None or i.status != "open":
                continue
            c = counts.setdefault(i.page, {"error": 0, "warning": 0, "info": 0})
            c[i.severity] += 1
        return [{"number": p.number, "kind": p.kind, "status": p.status,
                 "issues": counts.get(p.number, {"error": 0, "warning": 0, "info": 0}),
                 "figures": sum(1 for f in doc.figures if f.page == p.number),
                 "tables": sum(1 for t in doc.tables if any(x.page == p.number for x in t.parts))}
                for p in doc.pages]

    def page_image(self, doc_id: str, page_no: int, dpi: int | None = None) -> Path:
        rec = self.get_record(doc_id)
        if not 1 <= page_no <= rec.page_count:
            raise ServiceError("페이지가 없습니다.", 404)
        dpi = max(50, min(300, dpi or self.settings.preview_dpi))
        out = self.docs.previews_dir(doc_id) / f"p{page_no:04d}-{dpi}.png"
        if out.exists():
            return out
        import pypdfium2 as pdfium
        with PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(str(self.docs.source_path(doc_id)))
            try:
                page = pdf[page_no - 1]
                bitmap = page.render(scale=dpi / 72)
                img = bitmap.to_pil()
                page.close()
            finally:
                pdf.close()
        out.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", optimize=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(buf.getvalue())
        tmp.replace(out)
        return out

    def asset_file(self, doc_id: str, name: str) -> Path:
        self.get_record(doc_id)
        try:
            p = safe_join(self.docs.assets_dir(doc_id), name)
        except ValueError as exc:
            raise ServiceError("잘못된 경로입니다.", 400) from exc
        if not p.is_file():
            raise ServiceError("파일이 없습니다.", 404)
        return p

    # ------------------------------------------------------------------------------------
    # preview & export
    # ------------------------------------------------------------------------------------
    def _kb_item(self, doc_id: str) -> KbItem:
        rec = self.get_record(doc_id)
        doc = self._canonical(doc_id)
        profile = self.resolve_profile(rec)
        validation = {"summary": summarize(doc), "issues": [i.model_dump() for i in doc.issues]}
        return KbItem(doc, profile, self.docs.assets_dir(doc_id), validation, report_markdown(doc))

    def build_preview(self, doc_id: str) -> dict[str, Any]:
        item = self._kb_item(doc_id)
        root = self.docs.preview_kb_dir(doc_id)
        with self.docs.lock(doc_id):
            exports = build_kb([item], root, item.doc.effective_metadata().title or "Preview",
                               layout=item.profile.markdown.layout)
        exp = exports[0]
        return {"layout": item.profile.markdown.layout, "index": exp.index_path,
                "files": [{"path": f.path, "title": f.title, "section": f.section, "pages": f.pages}
                          for f in exp.files],
                "assets": sorted(exp.assets)}

    def preview_file(self, doc_id: str, path: str) -> dict[str, Any]:
        root = self.docs.preview_kb_dir(doc_id)
        if not root.exists():
            self.build_preview(doc_id)
        try:
            p = safe_join(root, path)
        except ValueError as exc:
            raise ServiceError("잘못된 경로입니다.") from exc
        if not p.is_file() or p.suffix != ".md":
            raise ServiceError("파일이 없습니다.", 404)
        text = p.read_text(encoding="utf-8")
        base = posixpath.dirname(path)

        def rewrite(tag: str, url: str) -> str:
            if re.match(r"^[a-z]+:|^#|^/", url):
                return url
            target = posixpath.normpath(posixpath.join(base, url.split("#", 1)[0]))
            if tag == "img":
                return f"/api/docs/{doc_id}/preview/raw?path={target}"
            if target.endswith(".md") or "." not in posixpath.basename(target):
                if not target.endswith(".md"):
                    target += ".md"
                return f"#preview:{target}"
            return f"/api/docs/{doc_id}/preview/raw?path={target}"

        return {"path": path, "markdown": text, "html": render_markdown(text, rewrite)}

    def preview_raw(self, doc_id: str, path: str) -> Path:
        root = self.docs.preview_kb_dir(doc_id)
        try:
            p = safe_join(root, path)
        except ValueError as exc:
            raise ServiceError("잘못된 경로입니다.") from exc
        if not p.is_file():
            raise ServiceError("파일이 없습니다.", 404)
        return p

    def export_zip(self, doc_ids: list[str], kb_name: str = "", layout: str | None = None) -> Path:
        if not doc_ids:
            raise ServiceError("내보낼 문서를 선택하세요.")
        items = []
        for d in doc_ids:
            if self.jobs.active_job(d):
                raise ServiceError("처리 중인 문서가 포함되어 있습니다.", 409)
            items.append(self._kb_item(d))
        if layout not in (None, "", "mkdocs", "wiki"):
            raise ServiceError("layout은 mkdocs 또는 wiki 여야 합니다.")
        name = kb_name.strip() or (items[0].doc.effective_metadata().title if len(items) == 1 else "Knowledge Base")
        slug = slugify(name, 50, fallback="knowledge-base")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        work = self.exports_dir / f"{slug}-{stamp}"
        root = work / slug
        build_kb(items, root, name, layout or None,
                 providers_public=[p.public() for p in self.providers.list()])
        zip_path = self.exports_dir / f"{slug}-{stamp}.zip"
        zip_tree(root, zip_path)
        shutil.rmtree(work, ignore_errors=True)
        self._prune_exports()
        return zip_path

    def _prune_exports(self, keep: int = 30) -> None:
        zips = sorted(self.exports_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in zips[keep:]:
            old.unlink(missing_ok=True)

    # ------------------------------------------------------------------------------------
    # provider test
    # ------------------------------------------------------------------------------------
    def test_provider(self, provider_id: str, with_image: bool = True) -> dict[str, Any]:
        from PIL import Image, ImageDraw
        try:
            provider = self.providers.provider(provider_id)
        except ProviderError as exc:
            raise ServiceError(str(exc), 404) from exc
        images = []
        if with_image and provider.config.supports_vision:
            img = Image.new("RGB", (160, 60), "white")
            ImageDraw.Draw(img).text((10, 20), "CK_t 1.1 V", fill="black")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            images = [buf.getvalue()]
        t0 = time.monotonic()
        try:
            resp = provider.complete(system="You are a connectivity test.", prompt="Reply with the word OK.",
                                     images=images, max_tokens=10, temperature=0)
        except ProviderError as exc:
            return {"ok": False, "error": str(exc), "latency_ms": int((time.monotonic() - t0) * 1000)}
        return {"ok": True, "reply": resp.text[:200], "model": resp.model, "latency_ms": resp.latency_ms,
                "image_sent": bool(images)}

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "data_dir": str(self.settings.data_dir),
                "documents": len(self.docs.list()), "workers": self.settings.workers,
                "default_provider": self.settings.default_provider,
                "auth": bool(self.settings.basic_auth)}


def merge_options(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    return deep_merge(base, extra)
