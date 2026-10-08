"""Low-level layout: words -> lines, header/footer patterns, TOC pages, column order."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

BOLD_RE = re.compile(r"(?i)(bold|black|heavy|semibold|demibold|demi\b|,b$|-b$|\.b$|bd$)")
PAGE_NUM_RE = re.compile(
    r"(?i)^(?:[-–—]\s*)?(?:page\s*)?(?:\d{1,4}|[ivxlc]{1,6})(?:\s*(?:of|/)\s*\d{1,4})?(?:\s*[-–—])?$")


def is_bold_font(fontname: str) -> bool:
    name = fontname.split("+", 1)[-1]
    return bool(BOLD_RE.search(name))


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool

    @property
    def mid_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> float:
        return max(0.1, self.bottom - self.top)


@dataclass
class Line:
    words: list[Word]
    x0: float = 0.0
    x1: float = 0.0
    top: float = 0.0
    bottom: float = 0.0
    text: str = ""
    size: float = 0.0
    bold: bool = False
    col: int = 0  # 0 = spanning / single column, 1 = left, 2 = right
    row_top: float = 0.0  # top of the visual row this fragment belongs to
    tags: set[str] = field(default_factory=set)

    def finish(self) -> "Line":
        self.words.sort(key=lambda w: w.x0)
        self.x0 = min(w.x0 for w in self.words)
        self.x1 = max(w.x1 for w in self.words)
        self.top = min(w.top for w in self.words)
        self.bottom = max(w.bottom for w in self.words)
        parts: list[str] = []
        prev: Word | None = None
        for w in self.words:
            if prev is not None:
                gap = w.x0 - prev.x1
                parts.append("" if gap < 0.12 * max(w.size, prev.size) else " ")
            parts.append(w.text)
            prev = w
        self.text = "".join(parts).strip()
        n_chars = sum(len(w.text) for w in self.words) or 1
        sizes = Counter()
        for w in self.words:
            sizes[round(w.size, 1)] += len(w.text)
        self.size = sizes.most_common(1)[0][0] if sizes else 0.0
        self.bold = sum(len(w.text) for w in self.words if w.bold) / n_chars >= 0.8
        return self

    @property
    def bbox(self) -> list[float]:
        return [round(self.x0, 2), round(self.top, 2), round(self.x1, 2), round(self.bottom, 2)]

    @property
    def mid_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0


def words_from_page(page: Any) -> list[Word]:
    raw = page.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False,
                             use_text_flow=False, extra_attrs=["fontname", "size"],
                             split_at_punctuation=False)
    out: list[Word] = []
    for w in raw:
        if not w.get("upright", True):
            continue  # rotated text (e.g. vertical axis labels) is rendered with figures
        text = w["text"].replace(" ", " ").strip()
        if not text:
            continue
        out.append(Word(text=text, x0=float(w["x0"]), x1=float(w["x1"]), top=float(w["top"]),
                        bottom=float(w["bottom"]), size=float(w.get("size") or 0),
                        bold=is_bold_font(str(w.get("fontname", "")))))
    return out


def build_lines(words: Sequence[Word], split_gap_ratio: float = 1.5) -> list[Line]:
    """Group words into visual lines, then split lines at wide horizontal gaps.

    The split produces *fragments* so that two-column text and borderless table
    columns become separate lines; ordinary (even justified) word spacing never
    exceeds ~0.7 em, so 1.5 em is a safe split threshold.
    """
    rows: list[list[Word]] = []
    row_bounds: list[tuple[float, float]] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        placed = False
        # only the last few rows can overlap since words are sorted by top
        for i in range(len(rows) - 1, max(-1, len(rows) - 6), -1):
            top, bottom = row_bounds[i]
            overlap = min(bottom, w.bottom) - max(top, w.top)
            if overlap > 0.5 * min(bottom - top, w.height):
                rows[i].append(w)
                row_bounds[i] = (min(top, w.top), max(bottom, w.bottom))
                placed = True
                break
        if not placed:
            rows.append([w])
            row_bounds.append((w.top, w.bottom))
    lines: list[Line] = []
    for row, (row_top, _) in zip(rows, row_bounds):
        row.sort(key=lambda w: w.x0)
        cur: list[Word] = [row[0]]
        for w in row[1:]:
            prev = cur[-1]
            size = max(w.size, prev.size, 1.0)
            if w.x0 - prev.x1 > split_gap_ratio * size:
                lines.append(Line(cur, row_top=row_top).finish())
                cur = [w]
            else:
                cur.append(w)
        lines.append(Line(cur, row_top=row_top).finish())
    lines.sort(key=lambda ln: (ln.row_top, ln.x0))
    return lines


# ---------------------------------------------------------------------------
# header / footer
# ---------------------------------------------------------------------------

def normalize_furniture(text: str) -> str:
    t = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", t).strip()


def furniture_patterns(band_lines: dict[int, tuple[list[str], list[str]]], min_repeat_ratio: float) -> list[str]:
    """Normalized header/footer lines that repeat on enough pages."""
    n = len(band_lines)
    if n < 2:
        return []
    counter: Counter[str] = Counter()
    for top, bottom in band_lines.values():
        for t in set(normalize_furniture(x) for x in top + bottom):
            if t:
                counter[t] += 1
    threshold = max(2, int(round(min_repeat_ratio * n)))
    return sorted(t for t, c in counter.items() if c >= threshold)


def is_furniture(line: Line, page_h: float, cfg: Any, patterns: Iterable[str],
                 extra_res: list[re.Pattern]) -> bool:
    for rx in extra_res:
        if rx.search(line.text):
            return True
    if not cfg.enabled:
        return False
    in_top = line.bottom <= page_h * cfg.top_ratio + 2
    in_bottom = line.top >= page_h * (1 - cfg.bottom_ratio) - 2
    if not (in_top or in_bottom):
        return False
    norm = normalize_furniture(line.text)
    pats = set(patterns)
    if norm in pats:
        return True
    # pdfium joins band text per visual line; a fragment may be a part of it
    if any(norm and norm in p for p in pats):
        return True
    if cfg.remove_page_numbers and PAGE_NUM_RE.match(line.text.strip()):
        return True
    return False


# ---------------------------------------------------------------------------
# TOC
# ---------------------------------------------------------------------------

def looks_like_toc(lines: Sequence[Line], cfg: Any) -> bool:
    if not lines:
        return False
    title_re = re.compile(cfg.title_pattern)
    leader_re = re.compile(cfg.leader_pattern)
    texts = [ln.text for ln in lines]
    has_title = any(title_re.search(t.strip()) for t in texts[:6])
    leaders = sum(1 for t in texts if leader_re.search(t))
    ratio = leaders / max(1, len(texts))
    return ratio >= cfg.min_line_ratio or (has_title and leaders >= 3)


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------

def find_gutter(lines: Sequence[Line], page_w: float) -> float | None:
    """Detect a two-column gutter x position, or None for single-column pages."""
    body = [ln for ln in lines if ln.width > 8]
    if len(body) < 6:
        return None
    best: tuple[int, float, float] | None = None  # (crossings, -gap_width, x)
    lo, hi = int(page_w * 0.3), int(page_w * 0.7)
    for x in range(lo, hi + 1, 2):
        crossing = sum(1 for ln in body if ln.x0 < x - 1 and ln.x1 > x + 1)
        if crossing > max(1, 0.06 * len(body)):
            continue
        left = [ln for ln in body if ln.x1 <= x + 1]
        right = [ln for ln in body if ln.x0 >= x - 1]
        if len(left) < 3 or len(right) < 3:
            continue
        # both columns must contain wrapped prose (lines that reach the gutter / right edge)
        lmin = min(ln.x0 for ln in left)
        lmax = max(ln.x1 for ln in left)
        rmin = min(ln.x0 for ln in right)
        rmax = max(ln.x1 for ln in right)
        lw, rw = lmax - lmin, rmax - rmin
        if lw < 80 or rw < 80:
            continue
        l_full = sum(1 for ln in left if ln.x1 >= lmax - 0.2 * lw and ln.x0 <= lmin + 0.1 * lw)
        r_full = sum(1 for ln in right if ln.x1 >= rmax - 0.2 * rw and ln.x0 <= rmin + 0.1 * rw)
        if l_full < 2 or r_full < 2:
            continue
        # columns must sit side by side vertically
        l_top, l_bot = min(ln.top for ln in left), max(ln.bottom for ln in left)
        r_top, r_bot = min(ln.top for ln in right), max(ln.bottom for ln in right)
        if min(l_bot, r_bot) - max(l_top, r_top) < 20:
            continue
        gap = rmin - lmax
        cand = (crossing, -gap, float(x))
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    return best[2]


def assign_columns(items: list[Any], gutter: float | None) -> None:
    """Set ``col`` on items (objects with x0/x1/top) given a gutter."""
    for it in items:
        if gutter is None:
            it.col = 0
        elif it.x1 <= gutter + 1:
            it.col = 1
        elif it.x0 >= gutter - 1:
            it.col = 2
        else:
            it.col = 0


def _row_top(it: Any) -> float:
    return getattr(it, "row_top", None) or it.top


def reading_order_key_factory(items: Sequence[Any]):
    """Sort key: spanning items split the page into bands; left column before right."""
    spanning_tops = sorted({_row_top(it) for it in items if it.col == 0})

    def key(it: Any) -> tuple:
        t = _row_top(it)
        if it.col == 0:
            return (2 * spanning_tops.index(t) + 1, 0, t, it.x0)
        band = sum(1 for s in spanning_tops if s <= t)
        return (2 * band, it.col, t, it.x0)

    if not any(it.col for it in items):
        return lambda it: (0, 0, _row_top(it), it.x0)
    return key


def median(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    return statistics.median(vals) if vals else default
