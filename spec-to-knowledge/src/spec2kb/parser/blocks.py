"""Text lines -> blocks (paragraphs, list items, notes, heading candidates)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .layout import Line, median

TERMINAL_PUNCT = tuple(".:;!?)")


@dataclass
class TextBlock:
    lines: list[Line]
    type: str = "paragraph"  # paragraph | list_item | note | heading
    label: str | None = None
    hints: dict[str, Any] = field(default_factory=dict)
    col: int = 0

    @property
    def x0(self) -> float:
        return min(ln.x0 for ln in self.lines)

    @property
    def x1(self) -> float:
        return max(ln.x1 for ln in self.lines)

    @property
    def top(self) -> float:
        return min(ln.top for ln in self.lines)

    @property
    def bottom(self) -> float:
        return max(ln.bottom for ln in self.lines)

    @property
    def row_top(self) -> float:
        return min(ln.row_top for ln in self.lines)

    @property
    def bbox(self) -> list[float]:
        return [round(self.x0, 2), round(self.top, 2), round(self.x1, 2), round(self.bottom, 2)]

    @property
    def size(self) -> float:
        c: Counter[float] = Counter()
        for ln in self.lines:
            c[ln.size] += len(ln.text)
        return c.most_common(1)[0][0] if c else 0.0

    @property
    def bold(self) -> bool:
        total = sum(len(ln.text) for ln in self.lines) or 1
        return sum(len(ln.text) for ln in self.lines if ln.bold) / total >= 0.8

    def text(self, dehyphenate: bool = False) -> str:
        return join_lines([ln.text for ln in self.lines], dehyphenate)


def join_lines(texts: list[str], dehyphenate: bool = False) -> str:
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        if out.endswith("-") and not out.endswith(" -") and len(out) > 1 and out[-2].isalpha():
            if dehyphenate and t[:1].islower():
                out = out[:-1] + t
            else:
                out = out + t
        else:
            out = out + " " + t
    return out


class BlockRules:
    def __init__(self, profile: Any, body_size: float):
        p = profile.parsing
        self.p = p
        self.body = body_size or 10.0
        self.num_re = re.compile(p.headings.numbered_pattern)
        self.annex_re = re.compile(p.headings.annex_pattern)
        self.note_re = re.compile(p.paragraphs.note_pattern)
        self.enum_re = re.compile(p.paragraphs.enum_pattern)
        self.leader_re = re.compile(p.toc.leader_pattern)
        self.bullets = set(p.paragraphs.bullet_chars)

    # -- classification -----------------------------------------------------------
    def bullet(self, text: str) -> tuple[str, str] | None:
        if not text:
            return None
        ch = text[0]
        if ch in self.bullets and (len(text) == 1 or text[1] in " \t"):
            # '-' or '–' immediately followed by a number is a negative value, not a bullet
            rest = text[1:].strip()
            if ch in "-–—" and re.match(r"^\d", rest):
                return None
            return ch, rest
        m = self.enum_re.match(text)
        if m:
            return m.group(1), text[m.end():].strip()
        return None

    def note(self, text: str) -> tuple[str, str] | None:
        m = self.note_re.match(text + " ")
        if not m:
            return None
        label = m.group(0).strip().rstrip(":.").strip()
        return label, text[m.end():].strip() if m.end() <= len(text) else ""

    def heading_candidate(self, line: Line) -> dict[str, Any] | None:
        text = line.text.strip()
        h = self.p.headings
        if not text or len(text) > h.max_length or self.leader_re.search(text):
            return None
        base = {"size": line.size, "bold": line.bold, "text": text}
        m = self.annex_re.match(text)
        if m:
            return {**base, "kind": "annex", "num": m.group("num"), "title": m.group("title").strip()}
        m = self.num_re.match(text)
        if m:
            title = m.group("title").strip()
            # reject value-like matches such as "1.2 V" or "3 ns typical"
            if re.match(r"^[A-Za-zµΩ°%/]{1,4}(\s|$)", title) and not line.bold and line.size < self.body * h.emphasis_size_ratio:
                return None
            if not re.search(r"[A-Za-z]{2}", title):
                return None
            return {**base, "kind": "numbered", "num": m.group("num").rstrip("."), "title": title}
        if h.unnumbered and text[:1].isupper() and not text.endswith((".", ",", ";")):
            words = text.split()
            emph = (line.bold and line.size >= self.body * h.unnumbered_size_ratio) or \
                   line.size >= self.body * (h.unnumbered_size_ratio + 0.2)
            if emph and len(words) <= h.unnumbered_max_words:
                return {**base, "kind": "unnumbered", "num": None, "title": text}
        return None


def build_text_blocks(lines: list[Line], rules: BlockRules, order_key) -> list[TextBlock]:
    """Group reading-ordered lines into blocks."""
    lines = sorted(lines, key=order_key)
    if not lines:
        return []
    gaps = []
    for a, b in zip(lines, lines[1:]):
        if a.col == b.col and abs(a.row_top - b.row_top) > 1:
            g = b.top - a.bottom
            if -1 <= g <= 1.2 * max(a.size, 1):
                gaps.append(g)
    typical_gap = median(gaps, 2.0)
    col_right: dict[int, float] = {}
    col_left: dict[int, float] = {}
    for ln in lines:
        col_right[ln.col] = max(col_right.get(ln.col, 0.0), ln.x1)
        col_left[ln.col] = min(col_left.get(ln.col, 1e9), ln.x0)

    blocks: list[TextBlock] = []
    cur: TextBlock | None = None
    prev: Line | None = None
    para = rules.p.paragraphs

    def start(line: Line) -> TextBlock:
        hc = rules.heading_candidate(line)
        if hc:
            return TextBlock([line], type="heading", hints={"hc": hc}, col=line.col)
        nt = rules.note(line.text)
        if nt:
            return TextBlock([line], type="note", label=nt[0], col=line.col)
        bl = rules.bullet(line.text)
        if bl:
            return TextBlock([line], type="list_item", label=bl[0], col=line.col)
        return TextBlock([line], type="paragraph", col=line.col)

    for line in lines:
        if cur is None or prev is None:
            cur = start(line)
            blocks.append(cur)
            prev = line
            continue
        same_row = abs(line.row_top - prev.row_top) < 1.0 and line.col == prev.col
        if same_row:
            cur.lines.append(line)
            prev = line
            continue
        size = max(line.size, prev.size, 1.0)
        gap = line.top - prev.bottom
        new = False
        if line.col != prev.col:
            new = True
        elif gap > typical_gap + para.gap_ratio * size:
            new = True
        elif abs(line.size - prev.size) > 0.15 * size:
            new = True
        elif cur.type == "heading":
            # a heading continues only when it wraps (long first line, same style, tight gap)
            width = col_right.get(line.col, line.x1) - col_left.get(line.col, line.x0)
            wraps = prev.width > 0.7 * width and line.bold == prev.bold and gap < 0.5 * size
            new = not wraps or rules.heading_candidate(line) is not None
        elif rules.heading_candidate(line) or rules.note(line.text) or rules.bullet(line.text):
            new = True
        elif cur.type == "list_item":
            text_x = cur.lines[0].x0
            new = line.x0 < text_x - 4 and line.x0 <= col_left.get(line.col, line.x0) + 2 and \
                prev.text.endswith(TERMINAL_PUNCT)
        elif line.x0 > prev.x0 + 8 and line.x0 - col_left.get(line.col, 0) > 8:
            new = True  # first-line indent
        else:
            width = col_right.get(line.col, line.x1) - col_left.get(line.col, line.x0)
            short = prev.x1 < col_right.get(prev.col, prev.x1) - 0.15 * width
            if short and prev.text.endswith((".", ":")) and line.text[:1].isupper():
                new = True
        if new:
            cur = start(line)
            blocks.append(cur)
        else:
            cur.lines.append(line)
        prev = line
    return blocks


def block_text(tb: TextBlock, rules: BlockRules) -> str:
    text = tb.text(rules.p.paragraphs.dehyphenate)
    if tb.type == "list_item":
        bl = rules.bullet(text)
        if bl:
            return bl[1]
    if tb.type == "note":
        nt = rules.note(text)
        if nt:
            return nt[1]
    return text


def merge_column_continuations(blocks: list[TextBlock], rules: BlockRules) -> list[TextBlock]:
    """Join a paragraph split by a column break (left column end -> right column start)."""
    out: list[TextBlock] = []
    for b in blocks:
        if out and b.type == "paragraph" and out[-1].type == "paragraph" and out[-1].col == 1 \
                and b.col == 2 and b.top <= out[-1].top:
            prev_text = out[-1].text()
            if not prev_text.endswith(TERMINAL_PUNCT) and b.text()[:1].islower():
                out[-1].lines.extend(b.lines)
                continue
        out.append(b)
    return out
