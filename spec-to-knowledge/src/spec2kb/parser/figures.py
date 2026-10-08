"""Figure detection: cluster vector graphics and images, attach labels and captions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .layout import Line


@dataclass
class Graphic:
    x0: float
    top: float
    x1: float
    bottom: float
    kind: str  # rect | line | curve | image | table


@dataclass
class FigureCandidate:
    x0: float
    top: float
    x1: float
    bottom: float
    objects: int = 0
    has_image: bool = False
    has_vector: bool = False
    labels: list[Line] = field(default_factory=list)
    caption: Line | None = None
    caption_lines: list[Line] = field(default_factory=list)
    number: str | None = None
    title: str = ""
    inferred: bool = False
    absorbed_tables: list[Any] = field(default_factory=list)
    col: int = 0

    @property
    def bbox(self) -> list[float]:
        return [round(self.x0, 2), round(self.top, 2), round(self.x1, 2), round(self.bottom, 2)]

    @property
    def row_top(self) -> float:
        tops = [self.top] + ([self.caption.top] if self.caption is not None else [])
        return min(tops)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def extend(self, x0: float, top: float, x1: float, bottom: float) -> None:
        self.x0, self.top = min(self.x0, x0), min(self.top, top)
        self.x1, self.bottom = max(self.x1, x1), max(self.bottom, bottom)

    @property
    def kind(self) -> str:
        if self.inferred and not self.objects:
            return "inferred"
        if self.has_image and self.has_vector:
            return "mixed"
        return "raster" if self.has_image else "vector"


def _is_white(color: Any) -> bool:
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return color >= 0.98
    if isinstance(color, (list, tuple)):
        vals = [v for v in color if isinstance(v, (int, float))]
        if len(vals) == 1:
            return vals[0] >= 0.98
        if len(vals) == 3:
            return all(v >= 0.98 for v in vals)
        if len(vals) == 4:  # CMYK
            return all(v <= 0.02 for v in vals)
    return False


def collect_graphics(page: Any, page_w: float, page_h: float, top_band: float, bottom_band: float,
                     exclude: Sequence[list[float]], text_heavy: bool = False) -> tuple[list[Graphic], list[str]]:
    """Graphics that can form figures. Page frames, backgrounds and (on text pages) full-page images
    behind the text are ignored; their kinds are returned as notes."""
    out: list[Graphic] = []
    notes: list[str] = []

    def excluded(x0, top, x1, bottom) -> bool:
        for b in exclude:
            if x0 >= b[0] - 2 and x1 <= b[2] + 2 and top >= b[1] - 2 and bottom <= b[3] + 2:
                return True
        return False

    def add(obj: dict, kind: str) -> None:
        x0, top, x1, bottom = (float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"]))
        if x1 < 0 or x0 > page_w or bottom < 0 or top > page_h:
            return
        w, h = x1 - x0, bottom - top
        if w >= 0.9 * page_w and h >= 0.9 * page_h:
            notes.append("page_background")
            return  # page background / border
        if kind == "rect" and w >= 0.75 * page_w and h >= 0.5 * page_h:
            notes.append("page_frame")
            return  # frame drawn around the text body
        if kind == "image" and text_heavy and w * h >= 0.6 * page_w * page_h:
            notes.append("background_image")
            return  # scanned page image behind an OCR text layer, or a full-page background
        if kind != "image" and (bottom <= top_band or top >= bottom_band):
            return  # header / footer rules
        if excluded(x0, top, x1, bottom):
            return
        out.append(Graphic(x0, top, x1, bottom, kind))

    for r in page.rects:
        if r.get("fill") and not r.get("stroke") and _is_white(r.get("non_stroking_color")):
            continue
        add(r, "rect")
    for ln in page.lines:
        add(ln, "line")
    for c in page.curves:
        add(c, "curve")
    for im in page.images:
        if float(im["x1"]) - float(im["x0"]) < 3 or float(im["bottom"]) - float(im["top"]) < 3:
            continue
        add(im, "image")
    return out, sorted(set(notes))


def cluster_graphics(objs: list[Graphic], gap: float) -> list[FigureCandidate]:
    """Union-find clustering of objects whose gap-expanded boxes touch (sweep on y)."""
    n = len(objs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: objs[i].top)
    active: list[int] = []
    for i in order:
        o = objs[i]
        active = [j for j in active if objs[j].bottom + gap >= o.top]
        for j in active:
            p = objs[j]
            if p.x0 - gap <= o.x1 and o.x0 - gap <= p.x1:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
        active.append(i)
    groups: dict[int, list[Graphic]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(objs[i])
    out: list[FigureCandidate] = []
    for g in groups.values():
        fc = FigureCandidate(min(o.x0 for o in g), min(o.top for o in g), max(o.x1 for o in g),
                             max(o.bottom for o in g))
        fc.objects = len(g)
        fc.has_image = any(o.kind == "image" for o in g)
        fc.has_vector = any(o.kind != "image" for o in g)
        out.append(fc)
    return out


def merge_overlapping(cands: list[FigureCandidate], gap: float) -> list[FigureCandidate]:
    changed = True
    while changed:
        changed = False
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                a, b = cands[i], cands[j]
                if a.x0 - gap <= b.x1 and b.x0 - gap <= a.x1 and a.top - gap <= b.bottom and b.top - gap <= a.bottom:
                    a.extend(b.x0, b.top, b.x1, b.bottom)
                    a.objects += b.objects
                    a.has_image |= b.has_image
                    a.has_vector |= b.has_vector
                    a.labels.extend(b.labels)
                    cands.pop(j)
                    changed = True
                    break
            if changed:
                break
    return cands


def is_prose(ln: Line, body_width: float) -> bool:
    """A full-width sentence line: never part of a drawing's labels."""
    return ln.width > 0.7 * body_width and len(ln.text.split()) >= 8


def attach_labels(cand: FigureCandidate, lines: list[Line], body_width: float, taken: set[int]) -> None:
    """Assign text lines that belong to the drawing (labels, markers, signal names)."""
    for _ in range(2):
        for ln in lines:
            if id(ln) in taken or is_prose(ln, body_width):
                continue
            inside = (ln.x0 >= cand.x0 - 4 and ln.x1 <= cand.x1 + 4 and
                      ln.top >= cand.top - 4 and ln.bottom <= cand.bottom + 4)
            overlaps = (ln.x0 < cand.x1 and ln.x1 > cand.x0 and ln.top < cand.bottom and ln.bottom > cand.top)
            v_inside = ln.mid_y >= cand.top - 2 and ln.mid_y <= cand.bottom + 2
            side = v_inside and ln.width < 0.45 * body_width and (
                0 <= cand.x0 - ln.x1 <= 70 or 0 <= ln.x0 - cand.x1 <= 70)
            near_v = (ln.x0 >= cand.x0 - 4 and ln.x1 <= cand.x1 + 4 and ln.width < 0.6 * max(cand.width, 1)
                      and (0 <= cand.top - ln.bottom <= 0.45 * max(ln.size, 1) or
                           0 <= ln.top - cand.bottom <= 0.45 * max(ln.size, 1)))
            if (inside or (overlaps and ln.width < 0.8 * body_width) or side or near_v) and \
                    "caption" not in ln.tags:
                cand.labels.append(ln)
                taken.add(id(ln))
                cand.extend(ln.x0, ln.top, ln.x1, ln.bottom)
