"""Table extraction: ruled tables (with row/col spans) and borderless fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..schema import Cell
from .layout import Line, Word, build_lines

RULED_SETTINGS = dict(vertical_strategy="lines", horizontal_strategy="lines", snap_tolerance=3,
                      join_tolerance=3, intersection_tolerance=3, edge_min_length=3)


@dataclass
class TableCandidate:
    bbox: list[float]
    n_rows: int
    n_cols: int
    cells: list[Cell]
    header_rows: int = 1
    method: str = "lines"
    confidence: float = 1.0
    caption: Line | None = None
    caption_lines: list[Line] = field(default_factory=list)
    number: str | None = None
    title: str = ""
    continued: bool = False
    words: list[Word] = field(default_factory=list)
    col: int = 0
    absorbed: bool = False

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def x1(self) -> float:
        return self.bbox[2]

    @property
    def bottom(self) -> float:
        return self.bbox[3]

    @property
    def row_top(self) -> float:
        return self.caption.top if self.caption is not None and self.caption.top < self.top else self.top

    @property
    def weak(self) -> bool:
        return self.caption is None

    def text_fill(self) -> float:
        if not self.cells:
            return 0.0
        return sum(1 for c in self.cells if c.text.strip()) / len(self.cells)

    def area(self) -> float:
        return max(0.0, (self.x1 - self.x0) * (self.bottom - self.top))


def _cluster(values: Sequence[float], tol: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if out and v - out[-1] <= tol:
            continue
        out.append(v)
    return out


def _index(coords: list[float], v: float, tol: float = 2.5) -> int:
    best = min(range(len(coords)), key=lambda i: abs(coords[i] - v))
    return best if abs(coords[best] - v) <= tol else -1


def _cell_text(words: list[Word]) -> str:
    if not words:
        return ""
    lines = build_lines(words, split_gap_ratio=3.0)
    parts: list[str] = []
    for ln in lines:
        t = ln.text
        if parts and parts[-1].endswith("-") and not parts[-1].endswith(" -"):
            parts[-1] = parts[-1] + t
        else:
            parts.append(t)
    return " ".join(parts).strip()


def _inside(w: Word, bbox: Sequence[float], pad: float = 0.5) -> bool:
    cx, cy = (w.x0 + w.x1) / 2, (w.top + w.bottom) / 2
    return bbox[0] - pad <= cx <= bbox[2] + pad and bbox[1] - pad <= cy <= bbox[3] + pad


def detect_header_rows(cells: list[Cell], words_by_cell: dict[tuple[int, int], list[Word]],
                       n_rows: int, mode: str, max_rows: int) -> int:
    if mode == "none" or n_rows < 2:
        return 0 if mode == "none" else min(1, n_rows)
    if mode == "first_row":
        return 1
    count = 0
    for r in range(min(max_rows, n_rows - 1)):
        anchored = [c for c in cells if c.row == r]
        texts = [(c, words_by_cell.get((c.row, c.col), [])) for c in anchored if c.text.strip()]
        if not texts:
            # a row fully covered by header cells spanning from above stays header
            covering = [c for c in cells if c.row < r < c.row + c.rowspan and c.row < count]
            if covering:
                count += 1
                continue
            break
        bold_chars = sum(len(w.text) for _, ws in texts for w in ws if w.bold)
        all_chars = sum(len(w.text) for _, ws in texts for w in ws) or 1
        if bold_chars / all_chars >= 0.8:
            count += 1
        else:
            break
    if count == 0:
        return 1  # GFM needs a header; the first row is the most likely header
    # extend header to cover rowspans that start in the header
    for c in cells:
        if c.row < count and c.row + c.rowspan > count:
            count = min(max_rows, c.row + c.rowspan)
    return count


def find_ruled_tables(page: Any, words: list[Word], cfg: Any) -> list[TableCandidate]:
    try:
        found = page.find_tables(table_settings=RULED_SETTINGS)
    except Exception:  # pragma: no cover - pdfplumber edge cases
        return []
    out: list[TableCandidate] = []
    for t in found:
        boxes = [tuple(float(v) for v in c) for c in t.cells if c]
        if not boxes:
            continue
        xs = _cluster([b[0] for b in boxes] + [b[2] for b in boxes], 2.0)
        ys = _cluster([b[1] for b in boxes] + [b[3] for b in boxes], 2.0)
        n_cols, n_rows = len(xs) - 1, len(ys) - 1
        if n_cols < 1 or n_rows < 1:
            continue
        bbox = [float(v) for v in t.bbox]
        table_words = [w for w in words if _inside(w, bbox, pad=1.0)]
        occupied: set[tuple[int, int]] = set()
        cells: list[Cell] = []
        words_by_cell: dict[tuple[int, int], list[Word]] = {}
        remaining = list(table_words)
        for b in sorted(boxes, key=lambda b: (b[1], b[0])):
            c0, c1 = _index(xs, b[0]), _index(xs, b[2])
            r0, r1 = _index(ys, b[1]), _index(ys, b[3])
            if min(c0, c1, r0, r1) < 0 or c1 <= c0 or r1 <= r0:
                continue
            span = {(r, c) for r in range(r0, r1) for c in range(c0, c1)}
            if span & occupied:
                continue
            occupied |= span
            cw = [w for w in remaining if _inside(w, b)]
            if cw:
                ids = {id(w) for w in cw}
                remaining = [w for w in remaining if id(w) not in ids]
            words_by_cell[(r0, c0)] = cw
            cells.append(Cell(row=r0, col=c0, rowspan=r1 - r0, colspan=c1 - c0,
                              text=_cell_text(cw), bbox=[round(v, 2) for v in b]))
        for r in range(n_rows):
            for c in range(n_cols):
                if (r, c) not in occupied:
                    cells.append(Cell(row=r, col=c, text=""))
        cells.sort(key=lambda c: (c.row, c.col))
        header = detect_header_rows(cells, words_by_cell, n_rows, cfg.header_detection,
                                    cfg.max_header_rows)
        for c in cells:
            c.header = c.row < header
        cand = TableCandidate(bbox=[round(v, 2) for v in bbox], n_rows=n_rows, n_cols=n_cols,
                              cells=cells, header_rows=header, words=table_words)
        if remaining and len(remaining) > 0.2 * max(1, len(table_words)):
            cand.confidence = 0.8
        out.append(cand)
    return out


def table_from_text_lines(lines: list[Line], min_rows: int, min_cols: int) -> TableCandidate | None:
    """Rebuild a borderless table from aligned line fragments (rows = visual rows)."""
    if not lines:
        return None
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda l: (l.row_top, l.x0)):
        if rows and abs(rows[-1][0].row_top - ln.row_top) < 1.0:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    rows = [sorted(r, key=lambda l: l.x0) for r in rows]
    multi = [r for r in rows if len(r) >= 2]
    if len(multi) < min_rows:
        return None
    starts = _cluster([ln.x0 for r in multi for ln in r], 10.0)
    # keep column starts used by at least half of the multi-fragment rows
    usage = {s: sum(1 for r in multi if any(abs(ln.x0 - s) <= 10 for ln in r)) for s in starts}
    cols = [s for s in starts if usage[s] >= max(2, len(multi) // 2)]
    if len(cols) < min_cols:
        return None
    n_cols = len(cols)
    cells: list[Cell] = []
    words: list[Word] = []
    for r_i, row in enumerate(rows):
        texts = [""] * n_cols
        for ln in row:
            ci = max((i for i, s in enumerate(cols) if ln.x0 >= s - 10), default=0)
            texts[ci] = (texts[ci] + " " + ln.text).strip()
            words.extend(ln.words)
        for ci, t in enumerate(texts):
            cells.append(Cell(row=r_i, col=ci, text=t))
    header = 1 if rows and all(ln.bold for ln in rows[0]) else 1
    for c in cells:
        c.header = c.row < header
    x0 = min(ln.x0 for r in rows for ln in r)
    x1 = max(ln.x1 for r in rows for ln in r)
    top = min(ln.top for r in rows for ln in r)
    bottom = max(ln.bottom for r in rows for ln in r)
    return TableCandidate(bbox=[round(x0, 2), round(top, 2), round(x1, 2), round(bottom, 2)],
                          n_rows=len(rows), n_cols=n_cols, cells=cells, header_rows=header,
                          method="text", confidence=0.7, words=words)


def collect_text_table_lines(lines: list[Line], start_y: float, max_y: float,
                             stop_res: list[re.Pattern], body_width: float) -> list[Line]:
    """Lines below a caption that look tabular (several fragments per visual row)."""
    cand = sorted([ln for ln in lines if ln.top >= start_y - 1 and ln.bottom <= max_y],
                  key=lambda l: (l.row_top, l.x0))
    rows: list[list[Line]] = []
    for ln in cand:
        if rows and abs(rows[-1][0].row_top - ln.row_top) < 1.0:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    picked: list[Line] = []
    prev_bottom = start_y
    for row in rows:
        size = max(ln.size for ln in row) or 10
        if row[0].top - prev_bottom > 2.2 * size and picked:
            break
        if len(row) < 2:
            # a single wide fragment is prose, not a table row
            if row[0].width > 0.55 * body_width or any(rx.search(row[0].text) for rx in stop_res):
                break
            if not picked:
                break
        if any(rx.search(row[0].text) for rx in stop_res):
            break
        picked.extend(row)
        prev_bottom = max(ln.bottom for ln in row)
    return picked
