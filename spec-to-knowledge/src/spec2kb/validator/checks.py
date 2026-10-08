"""Fidelity validation: source (PDF text layer) vs generated Markdown.

Checks
  * per page: numeric values with units, bare numbers, signal names and protected
    identifiers present in the source must appear in the Markdown (multiset), with
    "similar value" hints for distortions (moved decimal point, rounding, unit change)
  * per page: text coverage ratio
  * tables: grid integrity, rendered row/column structure (also after user edits), sparsity
  * numbering: duplicate / missing heading, figure and table numbers
  * figures: AI description failed / uncertain / unverifiable, missing image files
  * scanned pages: OCR missing or unverified
  * export: broken relative links and images, frontmatter presence
AI descriptions are excluded from the target text so that they cannot mask a
value that was dropped from the body text.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

from ..exporter.markdown import MarkdownRenderer, escape_inline, figure_caption, table_needs_html
from ..profiles.model import Profile
from ..schema import CanonicalDocument, Issue
from ..util import short_hash
from .tokens import digits_close, extract_tokens, markdown_to_plain, similar_values, value_display

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _issue(severity: str, code: str, message: str, page: int | None = None, ref: str | None = None,
           file: str | None = None, key: str = "", **details: Any) -> Issue:
    return Issue(id=f"val-{code}-{page}-{short_hash(ref, file, key, length=10)}", severity=severity, code=code,
                 message=message, page=page, ref=ref, file=file, source="validator", details=details)


# ---------------------------------------------------------------------------
# target text per page
# ---------------------------------------------------------------------------

def figure_target_text(doc: CanonicalDocument, fig_id: str, profile: Profile) -> str:
    f = doc.figure(fig_id)
    if f is None:
        return ""
    if f.md_override is not None:
        return markdown_to_plain(f.md_override)
    parts = [figure_caption(f)]
    if profile.markdown.include_embedded_text:
        parts += f.embedded_text
    return "\n".join(parts)


def page_targets(doc: CanonicalDocument, profile: Profile) -> dict[int, list[str]]:
    renderer = MarkdownRenderer(doc, profile)
    out: dict[int, list[str]] = defaultdict(list)
    for b in doc.blocks:
        if b.type == "figure" and b.ref:
            text = figure_target_text(doc, b.ref, profile)
            pages = [b.page]
        else:
            text = markdown_to_plain(renderer.render_block(b))
            pages = list(b.pages or [b.page])
            if b.type == "table" and b.ref:
                t = doc.table(b.ref)
                if t:
                    pages = sorted({p.page for p in t.parts} | set(pages))
        for p in pages:
            out[p].append(text)
    return out


def page_source(doc: CanonicalDocument, page_no: int, profile: Profile) -> str:
    p = doc.page(page_no)
    if p is None:
        return ""
    src = p.source_text
    if not profile.markdown.include_embedded_text:
        for f in doc.figures:
            if f.page == page_no:
                for ln in f.embedded_text:
                    src = src.replace(ln, " ", 1)
    return src


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_fidelity(doc: CanonicalDocument, profile: Profile) -> list[Issue]:
    v = profile.validation
    issues: list[Issue] = []
    targets = page_targets(doc, profile)
    for page in doc.pages:
        if page.kind in ("toc", "scanned", "blank") or page.status == "skipped":
            continue
        src_text = page_source(doc, page.number, profile)
        if not src_text.strip():
            continue
        tgt_text = "\n".join(targets.get(page.number, []))
        src = extract_tokens(src_text, v.units, v.signal_patterns, v.extra_token_patterns)
        tgt = extract_tokens(tgt_text, v.units, v.signal_patterns, v.extra_token_patterns)

        missing_values = {k: n - tgt.values.get(k, 0) for k, n in src.values.items() if tgt.values.get(k, 0) < n}
        new_values = [k for k in tgt.values if k not in src.values]
        if missing_values:
            distorted = {value_display(k): [value_display(x) for x in similar_values(k, new_values)]
                         for k in missing_values}
            distorted = {k: v_ for k, v_ in distorted.items() if v_}
            shown = ", ".join(value_display(k) + (f" ×{n}" if n > 1 else "") for k, n in sorted(missing_values.items()))
            msg = f"{page.number}쪽: 원문의 수치·단위 {len(missing_values)}종이 Markdown에 없습니다: {shown}"
            if distorted:
                msg += " (왜곡 의심: " + "; ".join(f"{k} → {', '.join(x)}" for k, x in distorted.items()) + ")"
            issues.append(_issue("error", "value_missing", msg, page.number, key=shown,
                                 missing=[value_display(k) for k in missing_values], distorted=distorted))
        covered_nums = {k.split(" ")[0] for k in missing_values}
        missing_nums = {k: n - tgt.numbers.get(k, 0) for k, n in src.numbers.items()
                        if tgt.numbers.get(k, 0) < n and k not in covered_nums}
        new_nums = [k for k in tgt.numbers if k not in src.numbers]
        distorted_nums = {k: [x for x in new_nums if digits_close(k, x)][:3] for k in missing_nums}
        distorted_nums = {k: v_ for k, v_ in distorted_nums.items() if v_}
        if distorted_nums:
            shown = "; ".join(f"{k} → {', '.join(v_)}" for k, v_ in sorted(distorted_nums.items()))
            issues.append(_issue("error", "number_distorted",
                                 f"{page.number}쪽: 원문 숫자가 Markdown에서 다른 값으로 바뀐 것으로 보입니다: {shown}",
                                 page.number, key=shown, distorted=distorted_nums))
        missing_nums = {k: n for k, n in missing_nums.items() if k not in distorted_nums}
        if missing_nums:
            shown = ", ".join(k + (f" ×{n}" if n > 1 else "") for k, n in sorted(missing_nums.items()))
            issues.append(_issue("warning", "number_missing",
                                 f"{page.number}쪽: 원문의 숫자 {len(missing_nums)}종이 Markdown에 없거나 개수가 줄었습니다: {shown}",
                                 page.number, key=shown, missing=sorted(missing_nums)))
        miss_sig = {k: n - tgt.signals.get(k, 0) for k, n in src.signals.items() if tgt.signals.get(k, 0) < n}
        if miss_sig:
            shown = ", ".join(k + (f" (원문 {src.signals[k]}회 → {tgt.signals.get(k, 0)}회)" if tgt.signals.get(k, 0) else "")
                              for k in sorted(miss_sig))
            issues.append(_issue("warning", "signal_missing",
                                 f"{page.number}쪽: 원문의 신호명/파라미터명이 Markdown에서 빠졌습니다: {shown}",
                                 page.number, key=shown, missing=sorted(miss_sig)))
        miss_ex = {k: n - tgt.extras.get(k, 0) for k, n in src.extras.items() if tgt.extras.get(k, 0) < n}
        if miss_ex:
            shown = ", ".join(sorted(miss_ex))
            issues.append(_issue("error", "identifier_missing",
                                 f"{page.number}쪽: 보존 대상 식별자가 Markdown에서 빠졌습니다: {shown}",
                                 page.number, key=shown, missing=sorted(miss_ex)))
        s_chars = len(re.sub(r"[\W_]", "", src_text))
        t_chars = len(re.sub(r"[\W_]", "", tgt_text))
        if s_chars >= 80:
            ratio = min(t_chars / s_chars, 9.99)
            if ratio < v.coverage_warn_ratio:
                issues.append(_issue("warning", "text_coverage_low",
                                     f"{page.number}쪽: 원문 대비 Markdown 텍스트 보존율이 {ratio:.0%}입니다. 누락된 문단이 있는지 확인하세요.",
                                     page.number, key=f"{ratio:.2f}", ratio=round(ratio, 3)))
    return issues


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[int, int]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th") and self.rows:
            a = dict(attrs)
            self.rows[-1].append((int(a.get("rowspan") or 1), int(a.get("colspan") or 1)))


def table_shape_from_markdown(md: str) -> tuple[int, int, bool] | None:
    """(rows, cols, ragged) of the first table found in a Markdown fragment."""
    if "<table" in md.lower():
        p = _TableParser()
        p.feed(md)
        if not p.rows:
            return None
        carry: dict[int, int] = {}
        widths = []
        for row in p.rows:
            col = 0
            width = 0
            cells = iter(row)
            pending = list(cells)
            i = 0
            new_carry: dict[int, int] = {}
            while i < len(pending) or col in carry:
                if carry.get(col, 0) > 0:
                    if carry[col] > 1:
                        new_carry[col] = carry[col] - 1
                    col += 1
                    width += 1
                    continue
                if i >= len(pending):
                    break
                rs, cs = pending[i]
                for k in range(col, col + cs):
                    if rs > 1:
                        new_carry[k] = rs - 1
                col += cs
                width += cs
                i += 1
            carry = new_carry
            widths.append(width)
        cols = max(widths)
        return len(p.rows), cols, any(w != cols for w in widths)
    rows = [ln.strip() for ln in md.splitlines() if ln.strip().startswith("|") and ln.strip().endswith("|")]
    if len(rows) < 2:
        return None
    counts = []
    for r in rows:
        if re.fullmatch(r"\|(\s*:?-{3,}:?\s*\|)+", r):
            continue
        counts.append(len(re.split(r"(?<!\\)\|", r.strip()[1:-1])))
    if not counts:
        return None
    return len(counts), max(counts), len(set(counts)) > 1


def check_tables(doc: CanonicalDocument, profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    renderer = MarkdownRenderer(doc, profile)
    for t in doc.tables:
        label = f"Table {t.number}" if t.number else t.id
        cover = Counter()
        for c in t.cells:
            for r in range(c.row, c.row + c.rowspan):
                for k in range(c.col, c.col + c.colspan):
                    cover[(r, k)] += 1
        holes = [(r, k) for r in range(t.n_rows) for k in range(t.n_cols) if cover[(r, k)] != 1]
        if holes:
            issues.append(_issue("error", "table_grid_invalid",
                                 f"{label}: 셀 그리드가 올바르지 않습니다 (중복/누락 위치 {len(holes)}개).",
                                 t.page, t.id, key=str(len(holes))))
        md = renderer.render_table(t)
        shape = table_shape_from_markdown(md)
        if t.md_override is None:
            fmt = profile.markdown.table_format
            use_html = fmt == "html" or (fmt == "auto" and table_needs_html(t))
            expected_rows = t.n_rows if use_html else (t.n_rows - max(1, t.header_rows) + 1)
        else:
            expected_rows = None
        if shape is None:
            issues.append(_issue("error" if t.md_override is None else "warning", "table_not_rendered",
                                 f"{label}: Markdown에서 표 구조를 찾을 수 없습니다.", t.page, t.id))
        else:
            rows, cols, ragged = shape
            if ragged:
                issues.append(_issue("error", "table_ragged",
                                     f"{label}: Markdown 표의 행마다 열 수가 다릅니다.", t.page, t.id))
            if cols != t.n_cols:
                issues.append(_issue("warning" if t.md_override is not None else "error", "table_cols_changed",
                                     f"{label}: 열 수가 원본({t.n_cols})과 Markdown({cols})에서 다릅니다.",
                                     t.page, t.id, key=f"{cols}", expected=t.n_cols, actual=cols))
            if expected_rows is not None and rows != expected_rows:
                issues.append(_issue("error", "table_rows_changed",
                                     f"{label}: 행 수가 원본({expected_rows})과 Markdown({rows})에서 다릅니다.",
                                     t.page, t.id, key=f"{rows}"))
            if expected_rows is None:
                exp = t.n_rows - max(1, t.header_rows) + 1
                if rows not in (t.n_rows, exp):
                    issues.append(_issue("warning", "table_rows_changed",
                                         f"{label}: 사용자 수정 후 행 수({rows})가 원본({t.n_rows})과 다릅니다.",
                                         t.page, t.id, key=f"{rows}"))
        body = [c for c in t.cells if not c.header]
        if len(body) >= 6:
            empty = sum(1 for c in body if not c.text.strip()) / len(body)
            if empty > 0.5:
                issues.append(_issue("warning", "table_sparse",
                                     f"{label}: 본문 셀의 {empty:.0%}가 비어 있습니다. 추출 오류 가능성이 있습니다.",
                                     t.page, t.id, key=f"{empty:.2f}"))
        if t.confidence < 0.8:
            issues.append(_issue("info", "table_low_confidence",
                                 f"{label}: 추출 신뢰도 {t.confidence:.0%} ({t.method}).", t.page, t.id))
    return issues


def _seq_gaps(numbers: list[str]) -> tuple[list[str], list[str]]:
    dup = sorted(n for n, c in Counter(numbers).items() if c > 1)
    groups: dict[str, list[int]] = defaultdict(list)
    for n in numbers:
        m = re.fullmatch(r"(?:(.*?)[.\-])?(\d+)", n)
        if m:
            groups[m.group(1) or ""].append(int(m.group(2)))
    missing = []
    for prefix, vals in groups.items():
        vals = sorted(set(vals))
        for x in range(vals[0], vals[-1]):
            if x not in vals:
                missing.append(f"{prefix}.{x}" if prefix else str(x))
    return dup, missing


def check_numbering(doc: CanonicalDocument, profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    partial = len(doc.processing.pages_processed) < doc.source.page_count
    sev = "info" if partial else "warning"
    heads = [b.number for b in doc.blocks if b.type == "heading" and b.number]
    dup = sorted(n for n, c in Counter(heads).items() if c > 1)
    if dup:
        issues.append(_issue("warning", "heading_duplicate", f"중복된 절 번호: {', '.join(dup)}", key=",".join(dup)))
    for kind, items in (("Figure", [f.number for f in doc.figures if f.number]),
                        ("Table", [t.number for t in doc.tables if t.number])):
        d, m = _seq_gaps(items)
        if d:
            issues.append(_issue("warning", f"{kind.lower()}_number_duplicate",
                                 f"{kind} 번호 중복: {', '.join(d)}", key=",".join(d)))
        if m:
            issues.append(_issue(sev, f"{kind.lower()}_number_gap",
                                 f"{kind} 번호가 비어 있습니다: {', '.join(m)} — 해당 {kind.lower()}가 누락되었는지 확인하세요."
                                 + (" (일부 페이지만 처리됨)" if partial else ""), key=",".join(m)))
    return issues


def check_figures(doc: CanonicalDocument, profile: Profile, assets_dir: Path | None) -> list[Issue]:
    issues: list[Issue] = []
    for f in doc.figures:
        label = f"Figure {f.number}" if f.number else ("스캔 페이지" if f.kind == "page" else f"그림({f.id})")
        if assets_dir is not None and f.asset and not (assets_dir / f.asset).exists():
            issues.append(_issue("error", "asset_missing", f"{label}: 이미지 파일이 없습니다 ({f.asset}).", f.page, f.id))
        if f.kind == "page":
            continue
        if not f.number:
            issues.append(_issue("info", "figure_uncaptioned",
                                 f"{f.page}쪽의 캡션 없는 그림을 보존했습니다. 필요 없으면 Markdown에서 제거하세요.",
                                 f.page, f.id))
        if f.description_override is not None or f.md_override is not None:
            continue
        d = f.description
        if d is None or d.status == "pending":
            issues.append(_issue("warning", "vision_pending", f"{label}: AI 설명이 아직 생성되지 않았습니다.", f.page, f.id))
        elif d.status == "failed":
            issues.append(_issue("error", "vision_failed", f"{label}: AI 설명 생성 실패 — {d.error[:300]}",
                                 f.page, f.id, key=d.error[:80], error=d.error))
        elif d.status == "skipped":
            issues.append(_issue("info", "vision_skipped", f"{label}: AI 설명 생략 ({d.error or '설정에 따라'}).",
                                 f.page, f.id))
        elif d.status == "uncertain":
            why = d.warnings + ([f"모델이 불확실하다고 표시: {', '.join(d.uncertain[:5])}"] if d.uncertain else [])
            issues.append(_issue("warning", "vision_uncertain", f"{label}: AI 설명 검토 필요 — " + " / ".join(why)[:600],
                                 f.page, f.id, key="|".join(why)[:200], warnings=d.warnings, uncertain=d.uncertain))
    return issues


def check_ocr(doc: CanonicalDocument, profile: Profile) -> list[Issue]:
    issues = []
    for p in doc.pages:
        if p.kind != "scanned":
            continue
        has_ocr = any(b.page == p.number and b.origin == "ocr" and b.type != "figure" for b in doc.blocks)
        if has_ocr:
            issues.append(_issue("warning", "ocr_unverified",
                                 f"{p.number}쪽: OCR로 추출한 텍스트입니다. 원본 이미지와 대조해 검토하세요.", p.number))
        elif profile.parsing.scanned.ocr and profile.vision.enabled:
            issues.append(_issue("error", "ocr_missing",
                                 f"{p.number}쪽: 스캔 페이지 OCR 결과가 없습니다 (Provider 오류 또는 미설정).", p.number))
        else:
            issues.append(_issue("warning", "ocr_disabled",
                                 f"{p.number}쪽: 스캔 페이지이지만 OCR이 꺼져 있어 이미지로만 보존됩니다.", p.number))
    return issues


LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


def check_export(files: dict[str, str], all_paths: set[str], layout: str, required_fm: list[str]) -> list[Issue]:
    """files: kb-relative path -> content. all_paths: every kb-relative file path."""
    issues: list[Issue] = []
    for path, content in files.items():
        base = PurePosixPath(path).parent
        for m in list(LINK_RE.finditer(content)) + list(SRC_RE.finditer(content)):
            target = m.group(1).split("#", 1)[0]
            if not target or re.match(r"^[a-z]+:", target) or target.startswith("/"):
                if target.startswith("/"):
                    issues.append(_issue("error", "absolute_link", f"{path}: 절대 경로 링크 '{target}'", file=path, key=target))
                continue
            resolved = _normalize(base / target)
            candidates = {resolved}
            if layout == "wiki" and not resolved.endswith((".md", ".png", ".jpg", ".svg")):
                candidates.add(resolved + ".md")
            if not candidates & all_paths:
                issues.append(_issue("error", "broken_link", f"{path}: 연결 대상이 없습니다 → {target}",
                                     file=path, key=target, target=target))
        if required_fm and path.endswith(".md"):
            if not content.startswith("---\n"):
                issues.append(_issue("error", "frontmatter_missing", f"{path}: Frontmatter가 없습니다.", file=path))
            else:
                head = content.split("\n---", 1)[0]
                missing = [k for k in required_fm if not re.search(rf"^{re.escape(k)}:", head, re.M)]
                if missing:
                    issues.append(_issue("error", "frontmatter_incomplete",
                                         f"{path}: Frontmatter 필드 누락: {', '.join(missing)}", file=path,
                                         key=",".join(missing)))
    return issues


def _normalize(p: PurePosixPath) -> str:
    parts: list[str] = []
    for part in p.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def validate(doc: CanonicalDocument, profile: Profile, assets_dir: Path | None = None) -> list[Issue]:
    v = profile.validation
    if not v.enabled:
        return []
    issues: list[Issue] = []
    issues += check_fidelity(doc, profile)
    if v.check_tables:
        issues += check_tables(doc, profile)
    if v.check_numbering:
        issues += check_numbering(doc, profile)
    issues += check_figures(doc, profile, assets_dir)
    issues += check_ocr(doc, profile)
    return issues


def apply_validation(doc: CanonicalDocument, profile: Profile, assets_dir: Path | None,
                     statuses: dict[str, str] | None = None, export_issues: list[Issue] | None = None) -> None:
    """Replace validator/export issues on the document and refresh page statuses."""
    keep = [i for i in doc.issues if i.source in ("parser",)]
    new = validate(doc, profile, assets_dir) + list(export_issues or [])
    seen: set[str] = set()
    merged: list[Issue] = []
    for i in keep + new:
        if i.id in seen:
            continue
        seen.add(i.id)
        if statuses and i.id in statuses:
            i.status = statuses[i.id]  # type: ignore[assignment]
        merged.append(i)
    merged.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 3), i.page or 0, i.code))
    doc.issues = merged
    worst: dict[int, str] = {}
    for i in merged:
        if i.page is None or i.status != "open":
            continue
        cur = worst.get(i.page)
        if cur is None or SEVERITY_ORDER[i.severity] < SEVERITY_ORDER[cur]:
            worst[i.page] = i.severity
    for p in doc.pages:
        if p.status == "skipped" or p.kind == "toc":
            continue
        sev = worst.get(p.number)
        p.status = "error" if sev == "error" else "warning" if sev == "warning" else "ok"


def summarize(doc: CanonicalDocument) -> dict[str, Any]:
    open_issues = [i for i in doc.issues if i.status == "open"]
    by_sev = Counter(i.severity for i in open_issues)
    by_code = Counter(i.code for i in open_issues)
    figs = Counter((f.description.status if f.description else "none") for f in doc.figures if f.kind != "page")
    return {"errors": by_sev.get("error", 0), "warnings": by_sev.get("warning", 0), "infos": by_sev.get("info", 0),
            "ignored": sum(1 for i in doc.issues if i.status != "open"), "by_code": dict(by_code),
            "pages": len(doc.pages), "pages_ok": sum(1 for p in doc.pages if p.status == "ok"),
            "headings": sum(1 for b in doc.blocks if b.type == "heading"), "tables": len(doc.tables),
            "figures": sum(1 for f in doc.figures if f.kind != "page"), "figure_status": dict(figs),
            "edited_blocks": sum(1 for b in doc.blocks if b.md_override is not None)
            + sum(1 for t in doc.tables if t.md_override is not None)
            + sum(1 for f in doc.figures if f.md_override is not None or f.description_override is not None)}


def report_markdown(doc: CanonicalDocument) -> str:
    s = summarize(doc)
    meta = doc.effective_metadata()
    lines = [f"# Validation report — {escape_inline(meta.title or doc.source.filename)}", "",
             f"- Source: `{doc.source.filename}` ({doc.source.page_count} pages, sha256 `{doc.source.sha256[:16]}…`)",
             f"- Profile: `{doc.processing.profile_id}` · generator {doc.processing.generator}",
             f"- Open issues: **{s['errors']} errors**, {s['warnings']} warnings, {s['infos']} info "
             f"({s['ignored']} ignored)",
             f"- Headings {s['headings']} · tables {s['tables']} · figures {s['figures']} · user edits {s['edited_blocks']}",
             "", "| Severity | Page | Code | Message | Status |", "|---|---|---|---|---|"]
    for i in doc.issues:
        msg = escape_inline(i.message).replace("|", "\\|")
        lines.append(f"| {i.severity} | {i.page or ''} | {i.code} | {msg} | {i.status} |")
    return "\n".join(lines) + "\n"
