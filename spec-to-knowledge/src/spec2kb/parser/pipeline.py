"""Parsing pipeline: raw per-page results -> assembled canonical document.

Raw page results are stored separately (one JSON per page) so that a single
page can be re-parsed and the canonical document re-assembled without losing
user edits (overlay) or AI descriptions (carried over by figure id + image hash).
"""

from __future__ import annotations

import copy
import logging
import re
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from .. import __version__
from ..profiles.model import Profile
from ..profiles.store import profile_hash
from ..schema import (Block, CanonicalDocument, Figure, Issue, PageInfo, SourceInfo, Table, utcnow)
from ..util import short_hash
from .finalize import (compute_body_size, demote_title_block, detect_cover_pages, ensure_unique_ids, extract_metadata,
                       finalize_headings, merge_continued_tables, merge_page_break_paragraphs)
from .layout import furniture_patterns
from .page import DocContext, parse_page
from .pdfdoc import PdfDoc

log = logging.getLogger(__name__)

Progress = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]


class Cancelled(Exception):
    pass


class RawPage(BaseModel):
    info: PageInfo
    blocks: list[Block] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    meta_lines: list[tuple[str, float, bool]] = Field(default_factory=list)
    body_size: float = 0.0
    ocr_text: str | None = None
    ocr_meta: dict[str, Any] = Field(default_factory=dict)


def _noop(*_a, **_k) -> None:
    return None


def compute_furniture(pdf: PdfDoc, profile: Profile, progress: Progress = _noop,
                      cancel: CancelCheck = lambda: False) -> list[str]:
    hf = profile.parsing.header_footer
    if not hf.enabled:
        return []
    bands: dict[int, tuple[list[str], list[str]]] = {}
    for n in range(1, pdf.page_count + 1):
        if cancel():
            raise Cancelled()
        top, bottom, _ = pdf.band_text(n, hf.top_ratio, hf.bottom_ratio)
        bands[n] = (top, bottom)
        if n % 25 == 0:
            progress("scan", n, pdf.page_count, "머리글/바닥글 분석")
    return furniture_patterns(bands, hf.min_repeat_ratio)


def parse_pages_raw(pdf_path: Path, profile: Profile, pages: list[int], assets_dir: Path,
                    furniture: list[str] | None = None, body_hint: float = 0.0,
                    progress: Progress = _noop, cancel: CancelCheck = lambda: False,
                    render: bool = True) -> tuple[dict[int, RawPage], list[str], int]:
    """Parse the given pages. Returns (raw pages, furniture patterns, page count)."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: dict[int, RawPage] = {}
    with PdfDoc(pdf_path) as pdf:
        if furniture is None:
            progress("scan", 0, pdf.page_count, "머리글/바닥글 분석")
            furniture = compute_furniture(pdf, profile, progress, cancel)
        ctx = DocContext(pdf=pdf, profile=profile, furniture=furniture, assets_dir=assets_dir,
                         body_size_hint=body_hint, render=render)
        total = len(pages)
        for i, n in enumerate(pages):
            if cancel():
                raise Cancelled()
            if n < 1 or n > pdf.page_count:
                continue
            progress("parse", i, total, f"{n}쪽 분석 중")
            t0 = time.monotonic()
            try:
                res = parse_page(ctx, n)
                rp = RawPage(info=res.info, blocks=res.blocks, tables=res.tables, figures=res.figures,
                             issues=res.issues, meta_lines=res.meta_lines, body_size=res.body_size)
            except Exception as exc:  # one broken page must not stop the document
                log.exception("page %s failed", n)
                w, h = pdf.page_size(n)
                info = PageInfo(number=n, width=w, height=h, status="error", processed_at=utcnow(),
                                messages=[f"페이지 분석 실패: {type(exc).__name__}: {exc}"])
                rp = RawPage(info=info, issues=[Issue(
                    id=f"parser-page_failed-{n}", severity="error", code="page_parse_failed",
                    message=f"{n}쪽 분석 중 오류가 발생했습니다: {type(exc).__name__}: {exc}",
                    page=n, source="parser",
                    details={"traceback": traceback.format_exc(limit=6)})])
            rp.info.messages.append(f"분석 시간 {time.monotonic() - t0:.2f}s")
            out[n] = rp
        progress("parse", total, total, "페이지 분석 완료")
        return out, furniture, pdf.page_count


def ocr_blocks(rp: RawPage, profile: Profile) -> list[Block]:
    """Turn OCR text of a scanned page into (low-confidence) blocks."""
    if not rp.ocr_text:
        return []
    num_re = re.compile(profile.parsing.headings.numbered_pattern)
    blocks: list[Block] = []
    paras = [p.strip() for p in re.split(r"\n\s*\n", rp.ocr_text) if p.strip()]
    n = rp.info.number
    idx = 0
    for para in paras:
        lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
        if not lines:
            continue
        first = lines[0]
        m = num_re.match(first)
        if m and len(first) <= profile.parsing.headings.max_length:
            idx += 1
            blocks.append(Block(id=f"p{n:04d}-o{idx:03d}", type="heading", page=n, text=m.group("title"),
                                number=m.group("num"), origin="ocr", confidence=0.6, bold=True,
                                hints={"hc": {"kind": "numbered", "num": m.group("num").rstrip("."),
                                              "title": m.group("title").strip(), "size": 0, "bold": True,
                                              "text": first}}))
            lines = lines[1:]
        if lines:
            idx += 1
            blocks.append(Block(id=f"p{n:04d}-o{idx:03d}", type="paragraph", page=n,
                                text=" ".join(lines), origin="ocr", confidence=0.6))
    return blocks


def assemble(doc_id: str, slug: str, source: SourceInfo, profile: Profile, raw: dict[int, RawPage],
             furniture: list[str]) -> CanonicalDocument:
    doc = CanonicalDocument(doc_id=doc_id, slug=slug, source=source)
    meta_lines: list[tuple[str, float, bool]] = []
    for n in range(1, source.page_count + 1):
        rp = raw.get(n)
        if rp is None:
            doc.pages.append(PageInfo(number=n, width=0, height=0, status="skipped",
                                      messages=["처리 범위 밖의 페이지"]))
            continue
        rp = copy.deepcopy(rp)
        doc.pages.append(rp.info)
        page_blocks = list(rp.blocks)
        if rp.ocr_text:
            # OCR text follows the page image block
            page_blocks = page_blocks + ocr_blocks(rp, profile)
        doc.blocks.extend(page_blocks)
        doc.tables.extend(rp.tables)
        doc.figures.extend(rp.figures)
        doc.issues.extend(rp.issues)
        if n <= 2:
            meta_lines.extend(rp.meta_lines)
    body = compute_body_size(doc.blocks)
    cover = detect_cover_pages(doc, body)
    demote_title_block(doc, body)
    finalize_headings(doc, profile, body, cover)
    ensure_unique_ids(doc)
    merge_continued_tables(doc, profile)
    merge_page_break_paragraphs(doc, profile)
    doc.metadata = extract_metadata(profile, meta_lines, source.pdf_metadata, source.filename)
    doc.processing.generator = f"spec2kb {__version__}"
    doc.processing.profile_id = profile.id
    doc.processing.profile_hash = profile_hash(profile)
    doc.processing.pages_processed = sorted(raw)
    doc.processing.stats = {
        "body_size": body,
        "furniture": furniture,
        "blocks": len(doc.blocks),
        "headings": sum(1 for b in doc.blocks if b.type == "heading"),
        "tables": len(doc.tables),
        "figures": len(doc.figures),
        "scanned_pages": [p.number for p in doc.pages if p.kind == "scanned"],
        "toc_pages": [p.number for p in doc.pages if p.kind == "toc"],
    }
    return doc


def apply_overlay(doc: CanonicalDocument, overlay: dict[str, Any]) -> list[Issue]:
    """Re-apply user edits; returns issues for edits whose target disappeared."""
    issues: list[Issue] = []
    for bid, ed in (overlay.get("blocks") or {}).items():
        b = doc.block(bid)
        if b is None:
            issues.append(_orphan(bid, ed))
            continue
        b.md_override = ed.get("md_override")
        b.edited_at = ed.get("edited_at")
    for tid, ed in (overlay.get("tables") or {}).items():
        t = doc.table(tid)
        if t is None:
            issues.append(_orphan(tid, ed))
            continue
        t.md_override = ed.get("md_override")
        t.edited_at = ed.get("edited_at")
    for fid, ed in (overlay.get("figures") or {}).items():
        f = doc.figure(fid)
        if f is None:
            issues.append(_orphan(fid, ed))
            continue
        if ed.get("image_type"):
            f.image_type = ed["image_type"]
            f.image_type_source = "user"
        if "description_override" in ed:
            f.description_override = ed.get("description_override")
        if "md_override" in ed:
            f.md_override = ed.get("md_override")
        if ed.get("prompt_extra") is not None:
            f.prompt_extra = ed.get("prompt_extra") or ""
        f.edited_at = ed.get("edited_at")
    doc.metadata_override = dict(overlay.get("metadata") or {})
    statuses = overlay.get("issues") or {}
    for i in doc.issues:
        if i.id in statuses:
            i.status = statuses[i.id]
    return issues


def _orphan(ref: str, ed: dict) -> Issue:
    preview = (ed.get("md_override") or ed.get("description_override") or "")[:200]
    return Issue(id=f"parser-edit_orphaned-{short_hash(ref)}", severity="warning", code="edit_orphaned",
                 message=f"재처리 후 '{ref}' 항목을 찾지 못해 사용자 수정 내용을 적용하지 못했습니다. 상세 정보에서 수정 내용을 확인하세요.",
                 ref=ref, source="parser", details={"edit_preview": preview})


def carry_over_descriptions(new: CanonicalDocument, old: CanonicalDocument | None) -> None:
    if old is None:
        return
    old_figs = {f.id: f for f in old.figures}
    for f in new.figures:
        o = old_figs.get(f.id)
        if o is None or o.description is None:
            continue
        if o.asset_sha256 and o.asset_sha256 == f.asset_sha256:
            f.description = o.description
            if o.image_type_source in ("rule", "llm", "default"):
                f.image_type, f.image_type_source = o.image_type, o.image_type_source
