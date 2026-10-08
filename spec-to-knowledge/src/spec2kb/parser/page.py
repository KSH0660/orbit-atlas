"""Single-page parser: words -> tables, figures, captions, text blocks (reading order)."""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..profiles.model import Profile
from ..schema import Block, Cell, Figure, Issue, PageInfo, Table, TablePart, utcnow
from ..util import atomic_write_bytes, sha256_bytes, short_hash, slugify
from .blocks import BlockRules, TextBlock, block_text, build_text_blocks, merge_column_continuations
from .figures import (FigureCandidate, attach_labels, cluster_graphics, collect_graphics, is_prose,
                      merge_overlapping)
from .layout import (Line, assign_columns, build_lines, find_gutter, is_furniture, looks_like_toc,
                     reading_order_key_factory, words_from_page)
from .pdfdoc import PdfDoc
from .tables import (TableCandidate, collect_text_table_lines, find_ruled_tables,
                     table_from_text_lines)


@dataclass
class DocContext:
    pdf: PdfDoc
    profile: Profile
    furniture: list[str]
    assets_dir: Path
    body_size_hint: float = 10.0
    render: bool = True


@dataclass
class Caption:
    kind: str  # table | figure
    lines: list[Line]
    number: str
    title: str
    continued: bool

    @property
    def line(self) -> Line:
        return self.lines[0]

    @property
    def top(self) -> float:
        return self.lines[0].top

    @property
    def bottom(self) -> float:
        return max(ln.bottom for ln in self.lines)

    @property
    def x0(self) -> float:
        return min(ln.x0 for ln in self.lines)

    @property
    def x1(self) -> float:
        return max(ln.x1 for ln in self.lines)

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines).strip()


@dataclass
class PageResult:
    info: PageInfo
    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    meta_lines: list[tuple[str, float, bool]] = field(default_factory=list)
    body_size: float = 0.0


def _issue(severity: str, code: str, message: str, page: int, ref: str | None = None,
           **details: Any) -> Issue:
    return Issue(id=f"parser-{code}-{page}-{short_hash(ref, message, length=8)}", severity=severity,
                 code=code, message=message, page=page, ref=ref, source="parser", details=details)


def page_body_size(lines: list[Line]) -> float:
    c: Counter[float] = Counter()
    for ln in lines:
        if len(ln.text) >= 15:
            c[ln.size] += len(ln.text)
    return c.most_common(1)[0][0] if c else 0.0


def _h_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def find_captions(lines: list[Line], pattern: str, cont_pattern: str, kind: str,
                  body_x0: float, body_x1: float) -> list[Caption]:
    rx = re.compile(pattern)
    cont_rx = re.compile(cont_pattern) if cont_pattern else None
    body_c = (body_x0 + body_x1) / 2
    body_w = max(1.0, body_x1 - body_x0)
    ordered = sorted(lines, key=lambda l: (l.row_top, l.x0))
    out: list[Caption] = []
    used: set[int] = set()
    for i, ln in enumerate(ordered):
        if id(ln) in used or "caption" in ln.tags:
            continue
        m = rx.match(ln.text.strip())
        if not m:
            continue
        raw_rest = ln.text.strip()[m.end("num"):]
        rest = raw_rest.lstrip()
        if raw_rest[:1].isalpha():
            continue  # text glued to the number is an in-text reference ("그림 1은 ...", "표 2에서 ...")
        has_sep = rest[:1] in ("—", "–", ":", "-", ".", "|") or rest == ""
        left_gap, right_gap = ln.x0 - body_x0, body_x1 - ln.x1
        centered = (abs(ln.center_x - body_c) < 0.06 * body_w and ln.width < 0.9 * body_w
                    and left_gap > 0.04 * body_w and right_gap > 0.04 * body_w)
        if not (has_sep or ln.bold or centered):
            continue  # an in-text reference such as "Table 1 lists ..."
        cap_lines = [ln]
        # continuation lines of a wrapped caption
        for nxt in ordered[i + 1:i + 3]:
            gap = nxt.top - cap_lines[-1].bottom
            if gap < -1 or gap > 0.6 * max(ln.size, 1):
                break
            if nxt.bold != ln.bold or abs(nxt.size - ln.size) > 0.5 or rx.match(nxt.text):
                break
            aligned = abs(nxt.center_x - ln.center_x) < 25 or abs(nxt.x0 - ln.x0) < 3
            if not aligned:
                break
            cap_lines.append(nxt)
        for c in cap_lines:
            used.add(id(c))
            c.tags.add("caption")
        full = " ".join(c.text for c in cap_lines)
        title = m.group("title").strip()
        if len(cap_lines) > 1:
            title = (title + " " + " ".join(c.text for c in cap_lines[1:])).strip()
        continued = bool(cont_rx.search(full)) if cont_rx else False
        if cont_rx:
            title = cont_rx.sub("", title).strip(" —–-:")
        out.append(Caption(kind=kind, lines=cap_lines, number=m.group("num"), title=title,
                           continued=continued))
    return out


def _center_in(ln: Line, bbox: list[float], pad: float = 1.0) -> bool:
    cx, cy = ln.center_x, ln.mid_y
    return bbox[0] - pad <= cx <= bbox[2] + pad and bbox[1] - pad <= cy <= bbox[3] + pad


def _overlap_ratio(inner: list[float], outer: list[float]) -> float:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return ix * iy / area


def parse_page(ctx: DocContext, number: int) -> PageResult:
    prof = ctx.profile
    pcfg = prof.parsing
    with ctx.pdf.page(number) as page:
        page_w, page_h = float(page.width), float(page.height)
        cropbox = [float(v) for v in page.cropbox]
        info = PageInfo(number=number, width=round(page_w, 2), height=round(page_h, 2))
        result = PageResult(info=info)
        words = words_from_page(page)
        info.char_count = sum(len(w.text) for w in words)
        all_lines = build_lines(words)

        # -- header / footer ------------------------------------------------------
        extra_res = [re.compile(p) for p in pcfg.header_footer.extra_patterns]
        content_lines: list[Line] = []
        for ln in all_lines:
            if is_furniture(ln, page_h, pcfg.header_footer, ctx.furniture, extra_res):
                info.removed_lines.append(ln.text)
            else:
                content_lines.append(ln)
        info.source_text = "\n".join(ln.text for ln in content_lines)
        body = page_body_size(content_lines)
        result.body_size = body
        if body:
            ctx.body_size_hint = body if ctx.body_size_hint <= 0 else ctx.body_size_hint
        result.meta_lines = [(ln.text, ln.size, ln.bold) for ln in content_lines[:60]]
        content_chars = sum(len(ln.text) for ln in content_lines)

        # -- scanned / blank ----------------------------------------------------------
        images = page.images
        big_image = any((float(im["x1"]) - float(im["x0"])) * (float(im["bottom"]) - float(im["top"]))
                        >= 0.5 * page_w * page_h for im in images)
        if content_chars < pcfg.scanned.min_chars and (big_image or (images and content_chars == 0)):
            info.kind = "scanned"
            info.status = "warning"
            fig = Figure(id=f"page-{number:04d}", page=number, bbox=[0, 0, page_w, page_h], kind="page",
                         caption="", title=f"Scanned page {number}", image_type="scanned_page")
            if ctx.render:
                _render_asset(ctx, fig, number, [0, 0, page_w, page_h], pcfg.scanned.ocr_dpi, cropbox)
            result.figures.append(fig)
            result.blocks.append(Block(id=f"p{number:04d}-b000", type="figure", page=number,
                                       bbox=fig.bbox, ref=fig.id, origin="ocr"))
            result.issues.append(_issue("warning", "scanned_page",
                                        f"{number}쪽은 텍스트 레이어가 없는 스캔 페이지입니다. OCR 결과를 원본과 대조해 검토하세요.",
                                        number, fig.id))
            info.processed_at = utcnow()
            return result
        if not content_lines and not page.rects and not page.lines and not page.curves and not images:
            info.kind = "blank"
            info.status = "ok"
            info.processed_at = utcnow()
            return result

        # -- table of contents ----------------------------------------------------------
        if pcfg.toc.skip and looks_like_toc(content_lines, pcfg.toc):
            info.kind = "toc"
            info.status = "skipped"
            info.messages.append("목차 페이지로 판단되어 본문에서 제외했습니다.")
            info.processed_at = utcnow()
            return result

        if content_lines:
            body_x0 = sorted(ln.x0 for ln in content_lines)[len(content_lines) // 10]
            body_x1 = sorted(ln.x1 for ln in content_lines)[-1 - len(content_lines) // 10]
        else:
            body_x0, body_x1 = page_w * 0.1, page_w * 0.9
        body_w = max(50.0, body_x1 - body_x0)

        # -- tables -----------------------------------------------------------------------
        content_words = [w for ln in content_lines for w in ln.words]
        tables: list[TableCandidate] = []
        if pcfg.tables.enabled:
            tables = find_ruled_tables(page, content_words, pcfg.tables)

        def in_any_table(ln: Line, tbls: list[TableCandidate]) -> bool:
            return any(_center_in(ln, t.bbox) for t in tbls)

        outside_tables = [ln for ln in content_lines if not in_any_table(ln, tables)]
        table_caps = find_captions(outside_tables, pcfg.tables.caption_pattern,
                                   pcfg.tables.continued_pattern, "table", body_x0, body_x1) \
            if pcfg.tables.enabled else []
        fig_caps = find_captions(outside_tables, pcfg.figures.caption_pattern, "", "figure",
                                 body_x0, body_x1) if pcfg.figures.enabled else []

        # table caption association
        pos = pcfg.tables.caption_position
        unmatched_table_caps: list[Caption] = []
        for cap in sorted(table_caps, key=lambda c: c.top):
            best: tuple[float, TableCandidate] | None = None
            for t in tables:
                if t.caption is not None:
                    continue
                if _h_overlap(t.x0, t.x1, cap.x0, cap.x1) <= 0:
                    continue
                cands = []
                if pos in ("above", "auto"):
                    cands.append(t.top - cap.bottom)
                if pos in ("below", "auto"):
                    cands.append(cap.top - t.bottom)
                for d in cands:
                    if -3 <= d <= pcfg.tables.caption_max_distance and (best is None or d < best[0]):
                        best = (d, t)
            if best:
                t = best[1]
                t.caption, t.caption_lines = cap.line, cap.lines
                t.number, t.title, t.continued = cap.number, cap.title, cap.continued
            else:
                unmatched_table_caps.append(cap)

        # borderless table fallback below/above unmatched captions
        if unmatched_table_caps and (pcfg.tables.text_fallback or pcfg.tables.strategy == "lines+text"):
            stop_res = [re.compile(pcfg.tables.caption_pattern), re.compile(pcfg.figures.caption_pattern),
                        re.compile(pcfg.headings.numbered_pattern), re.compile(pcfg.paragraphs.note_pattern)]
            for cap in list(unmatched_table_caps):
                free = [ln for ln in outside_tables if "caption" not in ln.tags]
                region_lines = collect_text_table_lines(free, cap.bottom, page_h * (1 - pcfg.header_footer.bottom_ratio),
                                                        stop_res, body_w)
                tt = table_from_text_lines(region_lines, pcfg.tables.min_rows, pcfg.tables.min_cols)
                if tt is not None:
                    tt.caption, tt.caption_lines = cap.line, cap.lines
                    tt.number, tt.title, tt.continued = cap.number, cap.title, cap.continued
                    for ln in region_lines:
                        ln.tags.add("text_table")
                    tables.append(tt)
                    unmatched_table_caps.remove(cap)
                    result.issues.append(_issue(
                        "warning", "table_text_fallback",
                        f"Table {cap.number}: 괘선이 없어 텍스트 정렬로 표를 재구성했습니다. 열 구분을 원본과 확인하세요.",
                        number, None, number_str=cap.number))

        # -- figures ---------------------------------------------------------------------------
        figures: list[FigureCandidate] = []
        if pcfg.figures.enabled:
            strong = [t.bbox for t in tables if t.caption is not None]
            graphics, gnotes = collect_graphics(page, page_w, page_h, page_h * pcfg.header_footer.top_ratio,
                                                page_h * (1 - pcfg.header_footer.bottom_ratio), strong,
                                                text_heavy=content_chars >= 200)
            if "background_image" in gnotes:
                info.messages.append("본문 뒤의 전면 이미지(스캔 원본 등)는 그림에서 제외하고 텍스트 레이어를 사용했습니다.")
            if "page_frame" in gnotes:
                info.messages.append("페이지 테두리 사각형은 그림에서 제외했습니다.")
            figures = merge_overlapping(cluster_graphics(graphics, pcfg.figures.cluster_gap), 2.0)
            label_pool = [ln for ln in content_lines
                          if not any(_center_in(ln, b) for b in strong) and "caption" not in ln.tags
                          and "text_table" not in ln.tags]
            taken: set[int] = set()
            for fc in sorted(figures, key=lambda f: -f.area):
                if fc.has_image or (fc.width >= 8 and fc.height >= 8):
                    attach_labels(fc, label_pool, body_w, taken)
            figures = merge_overlapping(figures, 2.0)

            fpos = pcfg.figures.caption_position
            unmatched_fig_caps: list[Caption] = []
            for cap in sorted(fig_caps, key=lambda c: c.top):
                best_f: tuple[float, FigureCandidate] | None = None
                for fc in figures:
                    if fc.caption is not None or (fc.width < 8 and fc.height < 8 and not fc.has_image):
                        continue
                    if _h_overlap(fc.x0, fc.x1, cap.x0 - 40, cap.x1 + 40) <= 0:
                        continue
                    ds = []
                    if fpos in ("below", "auto"):
                        ds.append(cap.top - fc.bottom)
                    if fpos in ("above", "auto"):
                        ds.append(fc.top - cap.bottom)
                    for d in ds:
                        if -4 <= d <= pcfg.figures.caption_max_distance and (best_f is None or d < best_f[0]):
                            best_f = (d, fc)
                if best_f is None:
                    unmatched_fig_caps.append(cap)
                    continue
                fc = best_f[1]
                fc.caption, fc.caption_lines, fc.number, fc.title = cap.line, cap.lines, cap.number, cap.title
                below = cap.top >= fc.bottom - 4
                # merge other uncaptioned parts of the same figure (vertically adjacent)
                changed = True
                while changed:
                    changed = False
                    for other in figures:
                        if other is fc or other.caption is not None:
                            continue
                        if not (other.has_image or other.objects >= 1):
                            continue
                        on_side = other.bottom <= cap.top + 2 if below else other.top >= cap.bottom - 2
                        v_gap = max(fc.top - other.bottom, other.top - fc.bottom)
                        if on_side and v_gap <= 2.5 * pcfg.figures.cluster_gap and \
                                _h_overlap(other.x0, other.x1, body_x0 - 20, body_x1 + 20) > 0:
                            fc.extend(other.x0, other.top, other.x1, other.bottom)
                            fc.objects += other.objects
                            fc.has_image |= other.has_image
                            fc.has_vector |= other.has_vector
                            fc.labels.extend(other.labels)
                            figures.remove(other)
                            changed = True
                            break

            # captions without detected graphics: infer region
            for cap in unmatched_fig_caps:
                inferred = None
                if pcfg.figures.infer_from_caption:
                    inferred = _infer_region(cap, content_lines, tables, figures, fpos, page_h, pcfg,
                                             body_x0, body_x1, body_w)
                if inferred is not None:
                    for ln in inferred.labels:
                        taken.add(id(ln))
                    figures.append(inferred)
                    result.issues.append(_issue(
                        "warning", "figure_region_inferred",
                        f"Figure {cap.number}: 도형이 감지되지 않아 캡션 주변 영역을 그림으로 저장했습니다. 영역을 확인하세요.",
                        number, None))
                else:
                    cap.line.tags.discard("caption")
                    result.issues.append(_issue(
                        "warning", "caption_without_figure",
                        f"Figure {cap.number} 캡션에 해당하는 그림을 찾지 못했습니다.", number, None))
                    for ln in cap.lines:
                        ln.tags.discard("caption")

            # weak (uncaptioned) tables vs figures
            kept_figs: list[FigureCandidate] = []
            for fc in figures:
                if fc.caption is not None or fc.inferred:
                    kept_figs.append(fc)
                    continue
                big_enough = fc.width >= pcfg.figures.min_width and fc.height >= pcfg.figures.min_height
                keep = pcfg.figures.keep_uncaptioned and big_enough and (
                    (fc.has_image and fc.area >= 2500) or
                    (fc.objects >= pcfg.figures.min_objects and fc.area >= pcfg.figures.min_uncaptioned_area))
                dominated = any(t.caption is None and _overlap_ratio(fc.bbox, t.bbox) >= 0.8 and
                                t.n_rows >= pcfg.tables.min_rows and t.n_cols >= pcfg.tables.min_cols
                                for t in tables)
                # decoration (watermark, shading, frame) spanning running text is not a figure
                prose_inside = sum(1 for ln in content_lines if is_prose(ln, body_w) and
                                   _overlap_ratio(ln.bbox, fc.bbox) >= 0.5)
                if keep and not dominated and prose_inside < 3:
                    kept_figs.append(fc)
                else:
                    for ln in fc.labels:
                        taken.discard(id(ln))
                    fc.labels = []
            figures = kept_figs
            for t in tables:
                if t.caption is not None:
                    continue
                for fc in figures:
                    if _overlap_ratio(t.bbox, fc.bbox) >= 0.6:
                        t.absorbed = True
                        fc.absorbed_tables.append(t)
                        break
        else:
            unmatched_fig_caps = []

        kept_tables: list[TableCandidate] = []
        for t in tables:
            if t.absorbed:
                continue
            if t.caption is None and not (t.n_rows >= pcfg.tables.min_rows and t.n_cols >= pcfg.tables.min_cols
                                          and t.text_fill() >= 0.3):
                continue
            kept_tables.append(t)

        # -- text blocks -------------------------------------------------------------------------
        consumed: set[int] = set()
        for t in kept_tables:
            for ln in content_lines:
                if t.method == "lines" and _center_in(ln, t.bbox):
                    consumed.add(id(ln))
            for ln in t.caption_lines:
                consumed.add(id(ln))
            if t.method == "text":
                for ln in content_lines:
                    if "text_table" in ln.tags and _center_in(ln, t.bbox, pad=2):
                        consumed.add(id(ln))
        for fc in figures:
            for ln in fc.labels + fc.caption_lines:
                consumed.add(id(ln))
            for t in fc.absorbed_tables:
                for ln in content_lines:
                    if _center_in(ln, t.bbox):
                        consumed.add(id(ln))
                        if ln not in fc.labels:
                            fc.labels.append(ln)
        free_lines = [ln for ln in content_lines if id(ln) not in consumed]
        for ln in free_lines:
            ln.tags.discard("caption")

        gutter = find_gutter(free_lines, page_w) if pcfg.paragraphs.columns == "auto" else None
        if gutter is not None:
            info.messages.append(f"2단 레이아웃 감지 (x={gutter:.0f}pt)")
        assign_columns(free_lines, gutter)
        assign_columns(kept_tables, gutter)
        assign_columns(figures, gutter)
        rules = BlockRules(prof, max(body, ctx.body_size_hint) if body else ctx.body_size_hint)
        tblocks = build_text_blocks(free_lines, rules, reading_order_key_factory(free_lines))
        if gutter is not None:
            tblocks = merge_column_continuations(tblocks, rules)

        elements: list[Any] = list(tblocks) + kept_tables + figures
        key = reading_order_key_factory(elements)
        elements.sort(key=key)

        # -- emit schema objects ---------------------------------------------------------------
        t_i = f_i = 0
        for idx, el in enumerate(elements):
            bid = f"p{number:04d}-b{idx:03d}"
            if isinstance(el, TextBlock):
                text = block_text(el, rules)
                if not text:
                    continue
                blk = Block(id=bid, type=el.type if el.type != "heading" else "heading", page=number,
                            bbox=el.bbox, text=text, label=el.label, font_size=el.size, bold=el.bold,
                            hints=el.hints)
                if el.type == "heading":
                    hc = el.hints["hc"]
                    if len(el.lines) > 1:
                        hc = dict(hc)
                        hc["title"] = (hc["title"] + " " + " ".join(l.text for l in el.lines[1:])).strip()
                        blk.hints = {"hc": hc}
                    blk.number = hc.get("num")
                    blk.text = hc.get("title") or text
                result.blocks.append(blk)
            elif isinstance(el, TableCandidate):
                t_i += 1
                table = _to_table(el, number, t_i)
                if ctx.render and pcfg.tables.snapshot:
                    region = _pad(el.bbox, 3, page_w, page_h)
                    try:
                        img = ctx.pdf.render(number, region, pcfg.tables.snapshot_dpi, 3000, cropbox)
                        name = f"{table.id}-p{number:04d}.png"
                        data = _png_bytes(img)
                        atomic_write_bytes(ctx.assets_dir / name, data)
                        table.snapshot = name
                        table.parts[0].snapshot = name
                    except Exception as exc:  # rendering is best effort for snapshots
                        result.issues.append(_issue("info", "snapshot_failed", f"표 이미지 저장 실패: {exc}", number, table.id))
                if el.confidence < 1.0 and el.method == "lines":
                    result.issues.append(_issue("warning", "table_unassigned_text",
                                                f"{_label('Table', table.number)}: 일부 텍스트가 셀에 배정되지 않았습니다.",
                                                number, table.id))
                result.tables.append(table)
                result.blocks.append(Block(id=bid, type="table", page=number, bbox=table.bbox, ref=table.id,
                                           hints={"continued": el.continued, "n_cols": el.n_cols,
                                                  "uncaptioned": el.caption is None}))
            elif isinstance(el, FigureCandidate):
                f_i += 1
                fig = _to_figure(el, number, f_i, rules)
                if ctx.render:
                    region = _pad(el.bbox, pcfg.figures.padding, page_w, page_h)
                    try:
                        _render_asset(ctx, fig, number, region, pcfg.figures.render_dpi, cropbox,
                                      pcfg.figures.max_pixels)
                    except Exception as exc:
                        result.issues.append(_issue("error", "figure_render_failed",
                                                    f"{_label('Figure', fig.number)} 이미지 렌더링 실패: {exc}",
                                                    number, fig.id))
                result.figures.append(fig)
                result.blocks.append(Block(id=bid, type="figure", page=number, bbox=fig.bbox, ref=fig.id))

        for cap in unmatched_table_caps:
            result.issues.append(_issue("warning", "caption_without_table",
                                        f"Table {cap.number} 캡션에 해당하는 표를 찾지 못했습니다. 캡션은 본문으로 남겼습니다.",
                                        number, None))
        info.status = "warning" if any(i.severity != "info" for i in result.issues) else "ok"
        info.processed_at = utcnow()
        return result


def _label(kind: str, number: str | None) -> str:
    return f"{kind} {number}" if number else f"{kind} (번호 없음)"


def _pad(b: list[float], pad: float, w: float, h: float) -> list[float]:
    return [max(0.0, b[0] - pad), max(0.0, b[1] - pad), min(w, b[2] + pad), min(h, b[3] + pad)]


def _png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_asset(ctx: DocContext, fig: Figure, page_no: int, region: list[float], dpi: int,
                  cropbox: list[float], max_px: int = 4000) -> None:
    img = ctx.pdf.render(page_no, region, dpi, max_px, cropbox)
    data = _png_bytes(img)
    name = f"{fig.id}-p{page_no:04d}.png" if not fig.id.startswith("page-") else f"{fig.id}.png"
    atomic_write_bytes(ctx.assets_dir / name, data)
    fig.asset = name
    fig.asset_sha256 = sha256_bytes(data)
    fig.width_px, fig.height_px = img.size


def _to_table(el: TableCandidate, page: int, idx: int) -> Table:
    tid = f"tbl-{slugify(el.number, 20)}" if el.number else f"tbl-p{page:04d}-{idx}"
    if el.continued:
        tid = f"{tid}-cont-p{page:04d}"
    caption = " ".join(ln.text for ln in el.caption_lines) if el.caption_lines else ""
    bbox = el.bbox
    if el.caption is not None:
        cb = [min(ln.x0 for ln in el.caption_lines), min(ln.top for ln in el.caption_lines),
              max(ln.x1 for ln in el.caption_lines), max(ln.bottom for ln in el.caption_lines)]
        bbox_full = [min(bbox[0], cb[0]), min(bbox[1], cb[1]), max(bbox[2], cb[2]), max(bbox[3], cb[3])]
    else:
        bbox_full = bbox
    cells = [Cell(**c.model_dump()) for c in el.cells]
    return Table(id=tid, number=el.number, caption=caption, title=el.title, page=page,
                 bbox=[round(v, 2) for v in bbox_full],
                 parts=[TablePart(page=page, bbox=bbox, rows=el.n_rows)], n_rows=el.n_rows,
                 n_cols=el.n_cols, header_rows=el.header_rows, cells=cells, method=el.method,
                 confidence=el.confidence)


def _to_figure(el: FigureCandidate, page: int, idx: int, rules: BlockRules) -> Figure:
    fid = f"fig-{slugify(el.number, 20)}" if el.number else f"fig-p{page:04d}-{idx}"
    caption = " ".join(ln.text for ln in el.caption_lines) if el.caption_lines else ""
    labels = sorted(el.labels, key=lambda l: (l.row_top, l.x0))
    embedded: list[str] = []
    for ln in labels:
        if ln.text and ln.text not in embedded:
            embedded.append(ln.text)
    return Figure(id=fid, number=el.number, caption=caption, title=el.title, page=page, bbox=el.bbox,
                  kind=el.kind if not el.inferred else "inferred", embedded_text=embedded)


def _infer_region(cap: Caption, lines: list[Line], tables: list[TableCandidate],
                  figures: list[FigureCandidate], pos: str, page_h: float, pcfg: Any,
                  body_x0: float, body_x1: float, body_w: float) -> FigureCandidate | None:
    """Region between the nearest prose/table above (or below) the caption and the caption."""
    min_h = 20.0
    prose = [ln for ln in lines if "caption" not in ln.tags and ln.width > 0.6 * body_w]
    barriers_above = [ln.bottom for ln in prose if ln.bottom <= cap.top - 1]
    barriers_above += [t.bottom for t in tables if t.bottom <= cap.top - 1]
    barriers_above += [f.bottom for f in figures if f.bottom <= cap.top - 1]
    top_limit = page_h * pcfg.header_footer.top_ratio
    if pos in ("below", "auto"):
        top = max(barriers_above + [top_limit]) + 2
        bottom = cap.top - 2
        if bottom - top >= min_h:
            fc = FigureCandidate(body_x0, top, body_x1, bottom, inferred=True)
            fc.labels = [ln for ln in lines if ln.top >= top - 1 and ln.bottom <= bottom + 1 and
                         "caption" not in ln.tags]
            fc.caption, fc.caption_lines, fc.number, fc.title = cap.line, cap.lines, cap.number, cap.title
            return fc
    if pos in ("above", "auto"):
        barriers_below = [ln.top for ln in prose if ln.top >= cap.bottom + 1]
        barriers_below += [t.top for t in tables if t.top >= cap.bottom + 1]
        bottom = min(barriers_below + [page_h * (1 - pcfg.header_footer.bottom_ratio)]) - 2
        top = cap.bottom + 2
        if bottom - top >= min_h:
            fc = FigureCandidate(body_x0, top, body_x1, bottom, inferred=True)
            fc.labels = [ln for ln in lines if ln.top >= top - 1 and ln.bottom <= bottom + 1 and
                         "caption" not in ln.tags]
            fc.caption, fc.caption_lines, fc.number, fc.title = cap.line, cap.lines, cap.number, cap.title
            return fc
    return None
