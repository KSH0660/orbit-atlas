"""Document-level passes over the per-page results.

* body font size (global) and heading acceptance with numbering-sequence checks
* cover page detection
* continued tables merged across pages (header de-duplication)
* paragraphs merged across page breaks
* unique table / figure ids
* document metadata (title, number, revision)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..profiles.model import Profile
from ..schema import Block, CanonicalDocument, Cell, DocMetadata, Issue, Table
from ..util import short_hash
from .blocks import TERMINAL_PUNCT

NumComp = int | str


def parse_number(num: str) -> list[NumComp]:
    out: list[NumComp] = []
    for p in num.strip(".").split("."):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
        elif p:
            out.append(p)
    return out


def _cmp_key(c: NumComp) -> tuple[int, Any]:
    return (0, c) if isinstance(c, int) else (1, c)


def successor_status(prev: list[NumComp] | None, cur: list[NumComp]) -> str | None:
    """'ok' for an expected successor, 'gap' for a plausible jump, None otherwise."""
    if not prev:
        return "ok"
    if len(cur) == len(prev) + 1 and cur[:-1] == prev and cur[-1] in (0, 1):
        return "ok"
    L = len(cur)
    if 1 <= L <= len(prev) and cur[:-1] == prev[:L - 1]:
        a, b = prev[L - 1], cur[-1]
        if isinstance(a, int) and isinstance(b, int):
            if b == a + 1:
                return "ok"
            if a + 1 < b <= a + 3:
                return "gap"
        elif isinstance(a, str) and isinstance(b, str) and len(a) == 1 and len(b) == 1:
            if ord(b) == ord(a) + 1:
                return "ok"
    if len(cur) > len(prev) + 1 and cur[:len(prev)] == prev and all(c in (0, 1) for c in cur[len(prev):]):
        return "gap"
    if len(cur) == len(prev) + 1 and cur[:-1] == prev and isinstance(cur[-1], int) and cur[-1] <= 3:
        return "gap"
    return None


def is_forward(prev: list[NumComp] | None, cur: list[NumComp], max_top_jump: int = 3) -> bool:
    if not prev:
        return True
    if [_cmp_key(c) for c in cur] <= [_cmp_key(c) for c in prev]:
        return False
    a, b = prev[0], cur[0]
    if isinstance(a, int) and isinstance(b, int) and b - a > max_top_jump:
        return False
    return True


def _issue(severity: str, code: str, msg: str, page: int | None, ref: str | None = None, **details) -> Issue:
    return Issue(id=f"parser-{code}-{page}-{short_hash(ref, msg, length=8)}", severity=severity, code=code,
                 message=msg, page=page, ref=ref, source="parser", details=details)


def compute_body_size(blocks: list[Block]) -> float:
    c: Counter[float] = Counter()
    for b in blocks:
        if b.type in ("paragraph", "list_item", "note") and b.font_size and b.origin == "text_layer":
            c[round(b.font_size, 1)] += len(b.text)
    return c.most_common(1)[0][0] if c else 10.0


def finalize_headings(doc: CanonicalDocument, profile: Profile, body: float, cover_pages: set[int]) -> None:
    h = profile.parsing.headings
    prev: list[NumComp] | None = None
    for b in doc.blocks:
        hc = b.hints.get("hc")
        if not hc:
            continue
        size = float(hc.get("size") or 0)
        bold = bool(hc.get("bold"))
        larger = size >= body * h.emphasis_size_ratio
        emphasized = bold or larger
        kind = hc.get("kind")
        title = (hc.get("title") or "").strip()
        accept = False
        level = 1
        number = None
        warn = None
        if kind == "annex":
            if emphasized or not h.require_emphasis:
                accept, level, number = True, 1, f"Annex {hc['num']}"
                prev = [hc["num"]]
        elif kind == "numbered":
            comps = parse_number(hc["num"])
            level = len(comps)
            if level > h.max_level or not title:
                accept = False
            elif h.require_emphasis and not emphasized:
                accept = False
            elif not h.check_sequence:
                accept = True
            else:
                status = successor_status(prev, comps)
                if status == "ok":
                    accept = True
                elif status == "gap" or is_forward(prev, comps):
                    accept = True
                    warn = "gap"
                elif bold and larger:
                    accept = True
                    warn = "order"
            if accept:
                number = hc["num"]
                prev = comps
        elif kind == "unnumbered":
            if b.page not in cover_pages:
                strong = (bold and size >= body * h.unnumbered_size_ratio) or \
                         size >= body * (h.unnumbered_size_ratio + 0.2)
                accept = strong and len(title.split()) <= h.unnumbered_max_words
                level = 1
        if accept:
            b.type = "heading"
            b.level = level
            b.number = number
            b.text = title
            if warn:
                doc.issues.append(_issue(
                    "info" if warn == "gap" else "warning", "heading_number_gap",
                    f"제목 번호 '{number}'가 직전 제목 번호에서 바로 이어지지 않습니다. 누락된 절이 있는지 확인하세요.",
                    b.page, b.id, number=number))
        else:
            b.type = "paragraph"
            b.level = None
            b.number = None
            b.text = hc.get("text") or b.text


def merge_continued_tables(doc: CanonicalDocument, profile: Profile) -> None:
    if not profile.parsing.tables.merge_continued:
        return
    by_number: dict[str, Table] = {}
    merged_into: dict[str, Table] = {}
    removed_blocks: set[str] = set()
    blocks = doc.blocks
    for i, b in enumerate(blocks):
        if b.type != "table" or b.ref is None:
            continue
        t = doc.table(b.ref)
        if t is None:
            continue
        base: Table | None = None
        if b.hints.get("continued") and t.number and t.number in by_number:
            base = by_number[t.number]
        elif b.hints.get("uncaptioned") and i > 0 and blocks[i - 1].page == b.page - 1:
            prev = blocks[i - 1]
            pt = doc.table(prev.ref) if prev.type == "table" and prev.ref else None
            if pt is not None:
                base = merged_into.get(pt.id, pt)
        if base is t:
            base = None
        if base is not None and base.n_cols == t.n_cols:
            _append_table(base, t)
            removed_blocks.add(b.id)
            merged_into[t.id] = base
            label = f"Table {base.number}" if base.number else base.id
            doc.issues.append(_issue("info", "table_merged",
                                     f"{label}: {t.page}쪽의 연속 표를 병합했습니다.", t.page, base.id))
            continue
        if base is not None:
            doc.issues.append(_issue("warning", "table_continuation_mismatch",
                                     f"Table {t.number or t.id}: 연속 표의 열 수({t.n_cols})가 원래 표({base.n_cols})와 달라 병합하지 않았습니다.",
                                     t.page, t.id))
        if t.number:
            by_number.setdefault(t.number, t)
    doc.blocks = [b for b in doc.blocks if b.id not in removed_blocks]
    doc.tables = [t for t in doc.tables if t.id not in merged_into]


def _row_texts(t: Table, n: int) -> list[list[str]]:
    g = t.grid()
    return [[(c.text.strip().lower() if c else "") for c in row] for row in g[:n]]


def _append_table(base: Table, cont: Table) -> None:
    if base is cont:
        return
    skip = 0
    if cont.header_rows and base.header_rows and cont.n_rows > cont.header_rows:
        if _row_texts(cont, cont.header_rows) == _row_texts(base, base.header_rows)[:cont.header_rows] and \
                cont.header_rows <= base.header_rows:
            skip = cont.header_rows
    offset = base.n_rows
    for c in cont.cells:
        if c.row < skip:
            continue
        nc = Cell(**c.model_dump())
        nc.row = c.row - skip + offset
        nc.header = False
        base.cells.append(nc)
    base.n_rows += cont.n_rows - skip
    for part in cont.parts:
        part = part.model_copy()
        part.rows = cont.n_rows - skip
        base.parts.append(part)
    base.confidence = min(base.confidence, cont.confidence)
    base.cells.sort(key=lambda c: (c.row, c.col))


def merge_page_break_paragraphs(doc: CanonicalDocument, profile: Profile) -> None:
    if not profile.parsing.paragraphs.merge_across_pages:
        return
    out: list[Block] = []
    for b in doc.blocks:
        if out:
            a = out[-1]
            if a.type == "paragraph" and b.type == "paragraph" and b.page == a.page + 1 \
                    and not a.text.rstrip().endswith(TERMINAL_PUNCT) and b.text[:1].islower() \
                    and a.origin == b.origin == "text_layer":
                a.hints = dict(a.hints)
                a.hints["merged_from"] = b.id
                if a.text.endswith("-") and not a.text.endswith(" -"):
                    a.text = a.text + b.text
                else:
                    a.text = a.text + " " + b.text
                a.pages = sorted(set((a.pages or [a.page]) + [b.page]))
                b.continued = True
                continue
        out.append(b)
    doc.blocks = out


def ensure_unique_ids(doc: CanonicalDocument) -> None:
    for items, kind in ((doc.tables, "table"), (doc.figures, "figure")):
        seen: set[str] = set()
        for it in items:
            if it.id in seen:
                old = it.id
                new = f"{old}-p{it.page:04d}"
                n = 2
                while new in seen:
                    new = f"{old}-p{it.page:04d}-{n}"
                    n += 1
                it.id = new
                for b in doc.blocks:
                    if b.type == kind and b.ref == old and b.page == it.page:
                        b.ref = new
                        break
                doc.issues.append(_issue("warning", f"duplicate_{kind}_number",
                                         f"{kind.capitalize()} {it.number}: 번호가 중복되어 ID를 '{new}'로 변경했습니다.",
                                         it.page, new))
            seen.add(it.id)


TITLE_SKIP_DEFAULT = r"(?i)^((jedec|jedec-style)\s+)?(sample\s+)?(standard|publication|specification|data ?sheet|customer requirement specification)$"


def extract_metadata(profile: Profile, meta_lines: list[tuple[str, float, bool]], pdf_meta: dict[str, str],
                     filename: str) -> DocMetadata:
    m = profile.parsing.metadata
    md = DocMetadata(publisher=m.publisher, tags=list(m.tags))
    text = "\n".join(t for t, _, _ in meta_lines)
    if m.doc_number_pattern:
        mm = re.search(m.doc_number_pattern, text) or re.search(m.doc_number_pattern, pdf_meta.get("Title", ""))
        if mm:
            md.doc_number = (mm.group(1) if mm.groups() else mm.group(0)).rstrip(".,;")
    if m.revision_pattern:
        mm = re.search(m.revision_pattern, text)
        if mm:
            md.revision = (mm.group(1) if mm.groups() else mm.group(0)).rstrip(".,;")
    skip = re.compile(TITLE_SKIP_DEFAULT)
    num_re = re.compile(profile.parsing.headings.numbered_pattern)
    cands = [(size, t) for t, size, _ in meta_lines if len(t.split()) >= 2 and not skip.match(t.strip())
             and not num_re.match(t.strip()) and (not md.doc_number or md.doc_number not in t)
             and len(t) <= 160]
    if cands:
        cands.sort(key=lambda x: -x[0])
        md.title = cands[0][1].strip()
    if not md.title and pdf_meta.get("Title"):
        md.title = pdf_meta["Title"].strip()
    if not md.title:
        md.title = re.sub(r"\.pdf$", "", filename, flags=re.I)
    return md


def demote_title_block(doc: CanonicalDocument, body: float) -> None:
    """Large unnumbered lines on page 1 before the first numbered heading are the document title."""
    for b in doc.blocks:
        if b.page != 1:
            break
        hc = b.hints.get("hc") or {}
        if hc.get("kind") in ("numbered", "annex"):
            break
        if hc.get("kind") == "unnumbered" and float(hc.get("size") or 0) >= 1.6 * body:
            b.hints = {k: v for k, v in b.hints.items() if k != "hc"} | {"title_block": True}
            b.type = "paragraph"


def detect_cover_pages(doc: CanonicalDocument, body: float) -> set[int]:
    cover: set[int] = set()
    first = [b for b in doc.blocks if b.page == 1]
    if first:
        max_size = max((b.font_size or 0) for b in first)
        numbered = any(b.hints.get("hc", {}).get("kind") == "numbered" and b.hints["hc"].get("bold") for b in first)
        if max_size >= 1.8 * body and len(first) <= 25 and not numbered:
            cover.add(1)
            p = doc.page(1)
            if p is not None:
                p.kind = "cover"
    return cover
