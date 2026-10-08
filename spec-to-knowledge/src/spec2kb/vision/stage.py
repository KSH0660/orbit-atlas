"""Vision stage: classify + describe figures, OCR scanned pages (concurrent, cached)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ..parser.pipeline import Cancelled, RawPage
from ..profiles.model import Profile
from ..providers.base import Provider, ProviderError
from ..schema import CanonicalDocument, Figure, VisionResult, utcnow
from .describe import (VisionCache, classification_prompt, classify_by_rules, describe_figure,
                       build_prompt, prepare_image)

log = logging.getLogger(__name__)


def section_of(doc: CanonicalDocument) -> dict[str, str]:
    """figure id -> nearest preceding heading ('4.2 Ball Assignment')."""
    out: dict[str, str] = {}
    current = ""
    for b in doc.blocks:
        if b.type == "heading":
            current = f"{b.number} {b.text}".strip() if b.number else b.text
        elif b.type == "figure" and b.ref:
            out[b.ref] = current
    return out


def classify_figures(doc: CanonicalDocument, profile: Profile, provider: Provider | None,
                     figure_ids: set[str] | None = None) -> None:
    for fig in doc.figures:
        if fig.kind == "page" or fig.image_type_source == "user":
            continue
        if figure_ids is not None and fig.id not in figure_ids:
            continue
        mode = profile.vision.classification
        type_id, source = classify_by_rules(fig, profile) if mode in ("rules", "rules_then_llm") else ("generic", "default")
        if provider is not None and profile.vision.enabled and (
                mode == "llm" or (mode == "rules_then_llm" and source == "default")):
            try:
                resp = provider.complete(system=profile.vision.system_prompt,
                                         prompt=classification_prompt(fig, profile), images=[],
                                         max_tokens=20, temperature=0)
                answer = resp.text.strip().split()[0].strip("`'\".,") if resp.text.strip() else ""
                if profile.image_type(answer):
                    type_id, source = answer, "llm"
            except ProviderError as exc:
                log.warning("classification failed for %s: %s", fig.id, exc)
        fig.image_type, fig.image_type_source = type_id, source


def needs_description(fig: Figure, profile: Profile, provider: Provider | None, section: str,
                      doc_title: str, force: bool) -> bool:
    if fig.kind == "page":
        return False
    if force or fig.description is None or fig.description.status in ("pending", "failed", "skipped"):
        return True
    if provider is None:
        return False
    rule = profile.image_type(fig.image_type) or profile.image_type("generic")
    if rule is None:
        return True
    _, _, phash = build_prompt(fig, rule, profile, section, doc_title, provider.model)
    return fig.description.prompt_hash != phash or fig.description.image_type != fig.image_type


def run_vision(doc: CanonicalDocument, profile: Profile, provider: Provider | None, assets_dir: Path,
               cache: VisionCache | None, figure_ids: set[str] | None = None, force: bool = False,
               progress: Callable[[str, int, int, str], None] = lambda *a: None,
               cancel: Callable[[], bool] = lambda: False, provider_error: str = "",
               bypass_cache: bool = False) -> dict[str, int]:
    """Describe figures in place. Returns counters."""
    stats = {"described": 0, "cached": 0, "failed": 0, "skipped": 0}
    classify_figures(doc, profile, provider, figure_ids)
    sections = section_of(doc)
    page_text = {p.number: p.source_text for p in doc.pages}
    doc_title = doc.effective_metadata().title
    todo = [f for f in doc.figures if (figure_ids is None or f.id in figure_ids)
            and f.kind != "page"
            and needs_description(f, profile, provider, sections.get(f.id, ""), doc_title, force)]
    if not profile.vision.enabled or provider is None:
        reason = "AI 그림 설명이 프로필에서 꺼져 있습니다." if not profile.vision.enabled else \
            (provider_error or "Vision Provider가 설정되지 않았습니다.")
        for f in todo:
            f.description = VisionResult(status="skipped" if not profile.vision.enabled else "failed",
                                         image_type=f.image_type, error=reason, created_at=utcnow())
            stats["skipped" if not profile.vision.enabled else "failed"] += 1
        return stats
    total = len(todo)
    progress("vision", 0, total, f"그림 {total}개 설명 생성")

    def work(fig: Figure) -> tuple[Figure, VisionResult]:
        if cancel():
            raise Cancelled()
        path = assets_dir / fig.asset
        if not fig.asset or not path.exists():
            return fig, VisionResult(status="failed", image_type=fig.image_type, error="그림 이미지 파일이 없습니다.",
                                     created_at=utcnow())
        return fig, describe_figure(fig, path, provider, profile, sections.get(fig.id, ""), doc_title,
                                    page_text.get(fig.page, ""), cache, bypass_cache=bypass_cache)

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, profile.vision.concurrency)) as pool:
        futures = [pool.submit(work, f) for f in todo]
        try:
            for fut in as_completed(futures):
                fig, res = fut.result()
                fig.description = res
                done += 1
                if res.status == "failed":
                    stats["failed"] += 1
                elif res.cached:
                    stats["cached"] += 1
                else:
                    stats["described"] += 1
                progress("vision", done, total, f"{fig.number and 'Figure ' + fig.number or fig.id} 완료")
        except Cancelled:
            for f in futures:
                f.cancel()
            raise
    return stats


def run_ocr(raw_pages: dict[int, RawPage], profile: Profile, provider: Provider | None, assets_dir: Path,
            pages: set[int] | None = None, force: bool = False,
            progress: Callable[[str, int, int, str], None] = lambda *a: None,
            cancel: Callable[[], bool] = lambda: False) -> list[int]:
    """OCR scanned pages in place (raw page ocr_text). Returns pages processed."""
    if not profile.parsing.scanned.ocr or provider is None or not profile.vision.enabled:
        return []
    todo = [rp for n, rp in sorted(raw_pages.items()) if rp.info.kind == "scanned"
            and (pages is None or n in pages) and (force or not rp.ocr_text)]
    out = []
    for i, rp in enumerate(todo):
        if cancel():
            raise Cancelled()
        progress("ocr", i, len(todo), f"{rp.info.number}쪽 OCR")
        fig = next((f for f in rp.figures if f.kind == "page"), None)
        if fig is None or not (assets_dir / fig.asset).exists():
            continue
        try:
            img = prepare_image(assets_dir / fig.asset, max(profile.vision.max_image_px, 2000))
            resp = provider.complete(system=profile.vision.system_prompt, prompt=profile.parsing.scanned.ocr_prompt,
                                     images=[img], max_tokens=max(profile.vision.max_tokens, 3000), temperature=0)
            rp.ocr_text = resp.text.strip()
            rp.ocr_meta = {"provider": provider.id, "model": resp.model, "created_at": utcnow(),
                           "duration_ms": resp.latency_ms}
            out.append(rp.info.number)
        except ProviderError as exc:
            rp.ocr_meta = {"provider": provider.id, "error": str(exc)[:500], "created_at": utcnow()}
    return out
