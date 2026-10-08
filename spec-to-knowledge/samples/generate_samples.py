"""Generate synthetic sample PDFs (and their ground truth) for testing.

The samples imitate the layout conventions of real specifications (JEDEC-style
standards, customer requirement specs, scanned documents) without reproducing
any copyrighted content. All values are invented.

Requires the dev dependency ``reportlab`` (not needed at runtime):

    python samples/generate_samples.py            # writes samples/*.pdf + *.truth.json
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
PIL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def register_fonts() -> tuple[str, str]:
    for regular, bold in FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            return "Body", "Body-Bold"
    print("WARNING: no TTF font found, falling back to Helvetica (non-ASCII glyphs missing)")
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = register_fonts()


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class SpecWriter:
    """Tiny flowing-layout writer on top of a reportlab canvas."""

    def __init__(self, path: Path, pagesize, header: str, footer_fmt: str,
                 margins=(72, 72, 72, 72), body_size=10.0):
        self.path = path
        self.c = canvas.Canvas(str(path), pagesize=pagesize, invariant=1)
        self.W, self.H = pagesize
        self.ml, self.mr, self.mt, self.mb = margins
        self.header = header
        self.footer_fmt = footer_fmt
        self.page = 0
        self.body_size = body_size
        self.y = 0.0
        self.truth: dict = {"headings": [], "tables": [], "figures": [], "values": [], "signals": []}
        self.decorate = True
        self.new_page()

    # -- page furniture -------------------------------------------------
    @property
    def text_width(self) -> float:
        return self.W - self.ml - self.mr

    def new_page(self) -> None:
        if self.page:
            self.c.showPage()
        self.page += 1
        self.y = self.H - self.mt
        if self.decorate and self.header:
            c = self.c
            c.setFont(FONT, 8.5)
            c.drawString(self.ml, self.H - 40, self.header)
            c.drawRightString(self.W - self.mr, self.H - 40, self.header_right())
            c.setLineWidth(0.5)
            c.line(self.ml, self.H - 45, self.W - self.mr, self.H - 45)
            c.setFont(FONT, 8.5)
            c.drawCentredString(self.W / 2, 36, self.footer_fmt.format(page=self.page))

    def header_right(self) -> str:
        return ""

    def ensure(self, h: float) -> None:
        if self.y - h < self.mb:
            self.new_page()

    def space(self, h: float) -> None:
        self.y -= h

    # -- text -----------------------------------------------------------
    def heading(self, number: str, title: str, level: int, size: float | None = None,
                record: bool = True) -> None:
        size = size or {1: 13, 2: 11.5, 3: 10.5}.get(level, 10.5)
        self.ensure(size * 3.5)
        self.space(size * 0.9)
        text = f"{number} {title}" if number else title
        self.c.setFont(FONT_B, size)
        self.c.drawString(self.ml, self.y - size, text)
        self.y -= size * 1.6
        if record:
            self.truth["headings"].append({"number": number, "title": title, "level": level,
                                           "page": self.page})

    def para(self, text: str, size: float | None = None, font: str | None = None,
             indent: float = 0.0, gap_after: float = 6.0, x: float | None = None,
             width: float | None = None) -> None:
        size = size or self.body_size
        font = font or FONT
        x0 = (x if x is not None else self.ml) + indent
        width = (width if width is not None else self.text_width) - indent
        lines = wrap(text, font, size, width)
        lead = size * 1.25
        for ln in lines:
            self.ensure(lead)
            self.c.setFont(font, size)
            self.c.drawString(x0, self.y - size, ln)
            self.y -= lead
        self.y -= gap_after

    def bullets(self, items: list[str], marker: str = "•") -> None:
        for it in items:
            lines = wrap(it, FONT, self.body_size, self.text_width - 18)
            for i, ln in enumerate(lines):
                self.ensure(self.body_size * 1.3)
                self.c.setFont(FONT, self.body_size)
                if i == 0:
                    self.c.drawString(self.ml + 4, self.y - self.body_size, marker)
                self.c.drawString(self.ml + 18, self.y - self.body_size, ln)
                self.y -= self.body_size * 1.25
            self.y -= 2
        self.y -= 4

    def caption(self, text: str) -> None:
        size = self.body_size
        self.ensure(size * 2)
        self.c.setFont(FONT_B, size)
        self.c.drawCentredString(self.W / 2, self.y - size, text)
        self.y -= size * 1.9

    # -- tables -----------------------------------------------------------
    def table(self, number: str, title: str, rows: list[list[str]], col_widths: list[float],
              header_rows: int = 1, merges: list[tuple[int, int, int, int]] | None = None,
              size: float = 8.5, caption_suffix: str = "", record: bool = True,
              continued: bool = False, shade_header: bool = True) -> None:
        """Draw a ruled table. ``merges`` are (row0, col0, row1, col1) inclusive spans."""
        merges = merges or []
        cap = f"Table {number} — {title}{caption_suffix}"
        pad = 3.0
        lead = size * 1.2
        covered: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        for m in merges:
            r0, c0, r1, c1 = m
            for r in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    covered[(r, cc)] = m
        # row heights
        heights = []
        for r, row in enumerate(rows):
            h = lead + 2 * pad
            for ci, txt in enumerate(row):
                m = covered.get((r, ci))
                if m and (m[0], m[1]) != (r, ci):
                    continue
                w = sum(col_widths[m[1]:m[3] + 1]) if m else col_widths[ci]
                n = max(1, len(wrap(txt, FONT, size, w - 2 * pad))) if txt else 1
                if m and m[2] > m[0]:
                    continue  # vertical merges: content spread over rows
                h = max(h, n * lead + 2 * pad)
            heights.append(h)
        total_w = sum(col_widths)
        x_left = (self.W - total_w) / 2
        self.ensure(size * 3 + sum(heights[: header_rows + 2]))
        self.caption(cap)
        if record:
            self.truth["tables"].append({"number": number, "title": title, "page": self.page,
                                         "rows": rows, "header_rows": header_rows,
                                         "merges": merges, "continued": continued})
        c = self.c
        c.setLineWidth(0.6)
        y_top = self.y
        row_tops = [y_top]
        for h in heights:
            row_tops.append(row_tops[-1] - h)
        if row_tops[-1] < self.mb:
            raise RuntimeError(f"table {number} does not fit on page; split it")
        xs = [x_left]
        for w in col_widths:
            xs.append(xs[-1] + w)
        for r, row in enumerate(rows):
            for ci, txt in enumerate(row):
                m = covered.get((r, ci))
                if m and (m[0], m[1]) != (r, ci):
                    continue
                r1, c1 = (m[2], m[3]) if m else (r, ci)
                x0, x1 = xs[ci], xs[c1 + 1]
                yt, yb = row_tops[r], row_tops[r1 + 1]
                if r < header_rows and shade_header:
                    c.setFillGray(0.88)
                    c.rect(x0, yb, x1 - x0, yt - yb, stroke=1, fill=1)
                    c.setFillGray(0)
                else:
                    c.rect(x0, yb, x1 - x0, yt - yb, stroke=1, fill=0)
                font = FONT_B if r < header_rows else FONT
                lines = wrap(txt, font, size, x1 - x0 - 2 * pad) if txt else []
                block_h = len(lines) * lead
                ty = yt - ((yt - yb) - block_h) / 2 - size
                c.setFont(font, size)
                for ln in lines:
                    if r < header_rows or ci > 0:
                        c.drawCentredString((x0 + x1) / 2, ty, ln)
                    else:
                        c.drawString(x0 + pad, ty, ln)
                    ty -= lead
        self.y = row_tops[-1] - 8

    # -- figures ----------------------------------------------------------
    def figure_box(self, height: float) -> tuple[float, float]:
        """Reserve vertical space for a figure; returns (x_left, y_bottom)."""
        self.ensure(height + 40)
        self.space(6)
        y_bottom = self.y - height
        self.y = y_bottom - 6
        return self.ml, y_bottom

    def record_figure(self, number: str, title: str, kind: str, labels: list[str]) -> None:
        self.truth["figures"].append({"number": number, "title": title, "page": self.page,
                                      "kind": kind, "labels": labels})

    def save(self) -> None:
        self.c.showPage()
        self.c.save()
        truth_path = self.path.with_suffix(".truth.json")
        self.truth["page_count"] = self.page
        truth_path.write_text(json.dumps(self.truth, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")


# ---------------------------------------------------------------------------
# vector drawings
# ---------------------------------------------------------------------------

def arrow(c, x0, y0, x1, y1, head=4.0):
    c.line(x0, y0, x1, y1)
    ang = math.atan2(y1 - y0, x1 - x0)
    for s in (-1, 1):
        a = ang + math.pi + s * math.radians(25)
        c.line(x1, y1, x1 + head * math.cos(a), y1 + head * math.sin(a))


def draw_read_timing(c, x, y, w, h) -> list[str]:
    """JEDEC-style read timing diagram. Returns the text labels used."""
    labels = []
    sigs = ["CK_t", "CK_c", "CMD", "DQS_t", "DQ[7:0]"]
    label_w = 56
    gx0 = x + label_w
    cyc = (w - label_w) / 12.0
    row_h = h / (len(sigs) + 1.2)
    c.setLineWidth(0.8)
    c.setFont(FONT, 7.5)
    # time markers
    for i in range(0, 12, 2):
        tx = gx0 + i * cyc
        c.drawCentredString(tx + cyc / 2, y + h - 8, f"T{i}")
        labels.append(f"T{i}")
    c.setDash(1, 2)
    for i in range(0, 12, 2):
        tx = gx0 + i * cyc
        c.line(tx, y + 4, tx, y + h - 12)
    c.setDash()
    for si, s in enumerate(sigs):
        base = y + h - 16 - (si + 1) * row_h
        hi = base + row_h * 0.55
        c.setFont(FONT, 8)
        c.drawString(x + 2, base + row_h * 0.2, s)
        labels.append(s)
        if s in ("CK_t", "CK_c"):
            level = (si == 0)
            px = gx0
            for i in range(24):
                nx = gx0 + (i + 1) * cyc / 2
                yy = hi if level else base
                c.line(px, yy, nx, yy)
                c.line(nx, base, nx, hi)
                px = nx
                level = not level
        elif s == "CMD":
            for i in range(12):
                x0 = gx0 + i * cyc + 2
                x1 = gx0 + (i + 1) * cyc - 2
                mid = (base + hi) / 2
                p = c.beginPath()
                p.moveTo(x0, mid)
                p.lineTo(x0 + 3, hi)
                p.lineTo(x1 - 3, hi)
                p.lineTo(x1, mid)
                p.lineTo(x1 - 3, base)
                p.lineTo(x0 + 3, base)
                p.close()
                c.drawPath(p, stroke=1, fill=0)
                txt = "RD" if i == 1 else "DES"
                c.setFont(FONT, 6.5)
                c.drawCentredString((x0 + x1) / 2, mid - 2.3, txt)
            labels += ["RD", "DES"]
        elif s == "DQS_t":
            start = gx0 + 7 * cyc
            c.line(gx0, (base + hi) / 2, start - cyc, (base + hi) / 2)
            c.line(start - cyc, base, start, base)
            level = True
            px = start
            for i in range(8):
                nx = px + cyc / 2
                yy = hi if level else base
                c.line(px, yy, nx, yy)
                c.line(nx, base, nx, hi)
                px = nx
                level = not level
            c.line(px, (base + hi) / 2, gx0 + 12 * cyc, (base + hi) / 2)
        else:  # DQ
            start = gx0 + 7 * cyc + cyc * 0.25
            c.line(gx0, (base + hi) / 2, start, (base + hi) / 2)
            for i in range(8):
                x0 = start + i * cyc / 2
                x1 = x0 + cyc / 2
                mid = (base + hi) / 2
                c.line(x0, mid, x0 + 2, hi)
                c.line(x0 + 2, hi, x1 - 2, hi)
                c.line(x1 - 2, hi, x1, mid)
                c.line(x0, mid, x0 + 2, base)
                c.line(x0 + 2, base, x1 - 2, base)
                c.line(x1 - 2, base, x1, mid)
                c.setFont(FONT, 6)
                c.drawCentredString((x0 + x1) / 2, mid - 2, f"D{i}")
                labels.append(f"D{i}")
            c.line(start + 4 * cyc, (base + hi) / 2, gx0 + 12 * cyc, (base + hi) / 2)
    # RL annotation
    ay = y + 6
    arrow(c, gx0 + 1.5 * cyc, ay, gx0 + 7.25 * cyc, ay)
    arrow(c, gx0 + 7.25 * cyc, ay, gx0 + 1.5 * cyc, ay)
    c.setFont(FONT, 7.5)
    c.drawCentredString(gx0 + 4.4 * cyc, ay + 3, "RL = 22 nCK")
    labels.append("RL = 22 nCK")
    c.drawString(gx0 + 9.3 * cyc, ay + 3, "tDQSCK")
    labels.append("tDQSCK")
    return labels


def draw_state_diagram(c, x, y, w, h) -> list[str]:
    labels = []
    states = {
        "IDLE": (x + w * 0.5, y + h * 0.78),
        "ACTIVE": (x + w * 0.18, y + h * 0.40),
        "PRECHARGE": (x + w * 0.50, y + h * 0.15),
        "POWER DOWN": (x + w * 0.82, y + h * 0.48),
        "SELF REFRESH": (x + w * 0.84, y + h * 0.86),
    }
    rx, ry = 46, 15
    c.setLineWidth(0.9)
    for name, (cx, cy) in states.items():
        c.ellipse(cx - rx, cy - ry, cx + rx, cy + ry)
        c.setFont(FONT_B, 7.5)
        c.drawCentredString(cx, cy - 2.5, name)
        labels.append(name)

    def edge(a, b, label, off=(0, 0)):
        (ax, ay), (bx, by) = states[a], states[b]
        ang = math.atan2(by - ay, bx - ax)
        sx, sy = ax + rx * math.cos(ang), ay + ry * math.sin(ang)
        ex, ey = bx - rx * math.cos(ang), by - ry * math.sin(ang)
        arrow(c, sx + off[0], sy + off[1], ex + off[0], ey + off[1], head=5)
        c.setFont(FONT, 7)
        c.drawCentredString((sx + ex) / 2 + off[0] + 8, (sy + ey) / 2 + off[1] + 3, label)
        labels.append(label)

    edge("IDLE", "ACTIVE", "ACT")
    edge("ACTIVE", "PRECHARGE", "PRE")
    edge("PRECHARGE", "IDLE", "tRP", off=(10, 0))
    edge("IDLE", "POWER DOWN", "PDE")
    edge("POWER DOWN", "IDLE", "PDX", off=(0, -10))
    edge("IDLE", "SELF REFRESH", "SRE")
    edge("SELF REFRESH", "IDLE", "SRX", off=(0, 10))
    return labels


def draw_block_diagram(c, x, y, w, h) -> list[str]:
    labels = []
    boxes = {
        "Application SoC": (x + 10, y + h * 0.35, 120, 50),
        "LPDDR5X x16": (x + w - 140, y + h * 0.55, 130, 40),
        "PMIC": (x + w * 0.42, y + 8, 90, 34),
        "Thermal Sensor": (x + w - 140, y + 8, 130, 34),
    }
    c.setLineWidth(0.9)
    for name, (bx, by, bw, bh) in boxes.items():
        c.rect(bx, by, bw, bh)
        c.setFont(FONT_B, 8)
        c.drawCentredString(bx + bw / 2, by + bh / 2 - 3, name)
        labels.append(name)
    soc = boxes["Application SoC"]
    mem = boxes["LPDDR5X x16"]
    pm = boxes["PMIC"]
    ts = boxes["Thermal Sensor"]
    arrow(c, soc[0] + soc[2], soc[1] + soc[3] - 10, mem[0], mem[1] + mem[3] / 2, head=5)
    c.setFont(FONT, 7)
    c.drawString(soc[0] + soc[2] + 10, soc[1] + soc[3] + 2, "CA[6:0], CK_t/CK_c")
    labels.append("CA[6:0], CK_t/CK_c")
    arrow(c, pm[0] + pm[2] / 2, pm[1] + pm[3], soc[0] + soc[2] / 2, soc[1], head=5)
    c.drawString(pm[0] + pm[2] / 2 + 4, pm[1] + pm[3] + 10, "VDD2H 1.05 V")
    labels.append("VDD2H 1.05 V")
    arrow(c, ts[0], ts[1] + ts[3] / 2, pm[0] + pm[2], pm[1] + pm[3] / 2, head=5)
    c.drawString(ts[0] - 70, ts[1] + ts[3] / 2 + 4, "I2C 400 kHz")
    labels.append("I2C 400 kHz")
    return labels


def ball_map_image() -> Image.Image:
    """Raster 'ball assignment' image (text exists only as pixels)."""
    cols = list("123456789")
    rows = list("ABCDEFGH")
    names = {
        ("A", "1"): "VDD", ("A", "9"): "VSS", ("B", "2"): "DQ0", ("B", "8"): "DQ7",
        ("C", "3"): "DQS_t", ("C", "7"): "DQS_c", ("D", "5"): "ZQ", ("E", "2"): "CK_t",
        ("E", "3"): "CK_c", ("F", "4"): "CS_n", ("G", "6"): "CA0", ("H", "1"): "VDDQ",
        ("H", "9"): "RESET_n",
    }
    cell = 70
    img = Image.new("RGB", (cell * (len(cols) + 1), cell * (len(rows) + 1)), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(PIL_FONT, 15)
        fs = ImageFont.truetype(PIL_FONT, 12)
    except OSError:
        f = fs = ImageFont.load_default()
    for ci, col in enumerate(cols):
        d.text((cell * (ci + 1) + cell // 2 - 5, 20), col, fill="black", font=f)
    for ri, row in enumerate(rows):
        d.text((25, cell * (ri + 1) + cell // 2 - 9), row, fill="black", font=f)
        for ci, col in enumerate(cols):
            cx, cy = cell * (ci + 1) + cell // 2, cell * (ri + 1) + cell // 2
            name = names.get((row, col))
            fill = (200, 220, 255) if name else (235, 235, 235)
            d.ellipse((cx - 26, cy - 26, cx + 26, cy + 26), outline="black", fill=fill, width=2)
            if name:
                tw = d.textlength(name, font=fs)
                d.text((cx - tw / 2, cy - 7), name, fill="black", font=fs)
    return img


# ---------------------------------------------------------------------------
# sample 1: JEDEC-style standard
# ---------------------------------------------------------------------------

class JedecWriter(SpecWriter):
    def header_right(self) -> str:
        return "Synthetic Sample — Not a JEDEC Publication"


def build_jedec_like(out: Path) -> None:
    w = JedecWriter(out, LETTER, header="JEDEC-Style Sample Standard No. SYN-01",
                    footer_fmt="Page {page}")
    c = w.c
    tr = w.truth
    tr["doc_number"] = "JESD-SYN-01"
    tr["revision"] = "1.0"

    # cover page (no header/footer furniture on the cover)
    c.setFont(FONT_B, 26)
    c.drawCentredString(w.W / 2, w.H - 200, "JEDEC-STYLE SAMPLE STANDARD")
    c.setFont(FONT_B, 16)
    c.drawCentredString(w.W / 2, w.H - 250, "Synthetic DDR6 SDRAM Specification")
    c.setFont(FONT, 12)
    c.drawCentredString(w.W / 2, w.H - 280, "JESD-SYN-01")
    c.drawCentredString(w.W / 2, w.H - 300, "Revision 1.0, October 2026")
    c.setFont(FONT, 9)
    c.drawCentredString(w.W / 2, 160, "This document is synthetic. It imitates the layout of an industry")
    c.drawCentredString(w.W / 2, 147, "standard for software testing only and contains invented values.")

    # TOC
    w.new_page()
    w.heading("", "Contents", 1, size=13, record=False)
    toc = [("1 Scope", 3), ("2 Normative References", 3), ("3 Terms and Definitions", 3),
           ("4 Pinout and Signal Description", 4), ("4.1 Signal Description", 4),
           ("4.2 Ball Assignment", 5), ("5 Electrical Characteristics", 6),
           ("5.1 DC Operating Conditions", 6), ("5.2 AC Timing Parameters", 6),
           ("6 Command and Timing", 8), ("6.1 Read Operation", 8), ("6.2 Power-Down State Machine", 9),
           ("Annex A (informative) Differences Between Revisions", 10)]
    for title, pg in toc:
        c.setFont(FONT, 10)
        c.drawString(w.ml, w.y - 10, title)
        tw = pdfmetrics.stringWidth(title, FONT, 10)
        dots = "." * int((w.text_width - tw - 30) / pdfmetrics.stringWidth(".", FONT, 10))
        c.drawString(w.ml + tw + 4, w.y - 10, dots)
        c.drawRightString(w.W - w.mr, w.y - 10, str(pg))
        w.y -= 16

    # page 3
    w.new_page()
    w.heading("", "Foreword", 1, size=13)
    w.para("This synthetic standard was prepared to exercise document conversion tools. "
           "It defines a fictional DDR6 SDRAM device with a 16-bit data bus, a data rate of "
           "up to 9600 MT/s and a core supply of 1.1 V. All numbers are invented and must not "
           "be used for any design.")
    w.heading("1", "Scope", 1)
    w.para("This document defines the minimum set of requirements for a synthetic x16 DDR6 "
           "SDRAM device operating from VDD = 1.1 V and VDDQ = 0.5 V. The device supports "
           "densities from 16 Gb to 64 Gb and a refresh interval tREFI of 3.9 µs at "
           "temperatures up to 85 °C.")
    w.heading("2", "Normative References", 1)
    w.para("The following documents are referenced in this standard:")
    w.bullets(["JESD-SYN-00, Synthetic Terms and Definitions (invented reference).",
               "JESD-SYN-02, Synthetic Package Outline Drawings, Revision 2.1.",
               "ISO-like Test Method TM-17 for ±5% supply tolerance measurement."])
    w.heading("3", "Terms and Definitions", 1)
    w.para("For the purposes of this standard, the following terms apply.")
    w.heading("3.1", "tCK(avg)", 2)
    w.para("Average clock period, measured over 200 consecutive cycles. The minimum "
           "tCK(avg) is 0.208 ns at 9600 MT/s.")
    w.heading("3.2", "nCK", 2)
    w.para("Number of clock cycles of CK_t/CK_c, used to express latencies such as RL and WL.")

    # page 4: signal table with vertical merge
    w.new_page()
    w.heading("4", "Pinout and Signal Description", 1)
    w.heading("4.1", "Signal Description", 2)
    w.para("Table 1 lists the external signals of the device. Signals with suffix _t and _c "
           "form differential pairs; signals with suffix _n are active low.")
    rows = [
        ["Symbol", "Type", "Function"],
        ["CK_t, CK_c", "Input", "Differential clock inputs. All address and command inputs are sampled on the crossing of CK_t rising and CK_c falling."],
        ["CS_n", "Input", "Chip select. The command decoder is disabled when CS_n is HIGH."],
        ["CA[13:0]", "Input", "Command/address inputs, sampled at the rising edge of CK_t."],
        ["DQ[15:0]", "I/O", "Bidirectional data bus."],
        ["DQS_t, DQS_c", "I/O", "Data strobe, edge-aligned with read data and centered with write data."],
        ["RESET_n", "Input", "Active-low asynchronous reset; VDD must be stable for 200 µs before RESET_n is released."],
        ["VDD", "Supply", "Core power supply: 1.1 V ± 0.033 V."],
        ["VDDQ", "Supply", "I/O power supply: 0.5 V ± 0.025 V."],
        ["VSS", "Supply", "Ground."],
    ]
    w.table("1", "Signal Description", rows, [90, 60, 290], header_rows=1,
            merges=[])
    tr["signals"] = ["CK_t", "CK_c", "CS_n", "CA[13:0]", "DQ[15:0]", "DQS_t", "DQS_c", "RESET_n",
                     "VDD", "VDDQ", "VSS"]
    w.para("NOTE 1 Unused CA inputs shall be tied to VDDQ through a 240 Ω resistor.", size=8.5)

    # page 5: raster figure
    w.new_page()
    w.heading("4.2", "Ball Assignment", 2)
    w.para("Figure 1 shows the ball assignment as seen from the top of the package. Balls not "
           "shown are reserved and shall not be connected.")
    img = ball_map_image()
    fig_h = 300
    fig_w = fig_h * img.width / img.height
    x0, yb = w.figure_box(fig_h)
    c.drawImage(ImageReader(img), (w.W - fig_w) / 2, yb, fig_w, fig_h)
    w.caption("Figure 1 — Ball Assignment (Top View)")
    w.record_figure("1", "Ball Assignment (Top View)", "raster", [])
    w.para("The ball pitch is 0.8 mm in both directions; package outline dimensions are "
           "defined in JESD-SYN-02.")

    # page 6: DC table with horizontal merge in header
    w.new_page()
    w.heading("5", "Electrical Characteristics", 1)
    w.heading("5.1", "DC Operating Conditions", 2)
    w.para("All voltages are referenced to VSS. Operation outside the limits of Table 2 is not "
           "guaranteed.")
    rows = [
        ["Symbol", "Parameter", "Rating", "", "", "Unit", "Note"],
        ["", "", "Min", "Typ", "Max", "", ""],
        ["VDD", "Core supply voltage", "1.067", "1.100", "1.133", "V", "1"],
        ["VDDQ", "I/O supply voltage", "0.475", "0.500", "0.525", "V", "1"],
        ["VPP", "Wordline supply voltage", "1.710", "1.800", "1.890", "V", "2"],
        ["IDD2N", "Precharge standby current", "-", "42", "55", "mA", ""],
        ["TOPER", "Operating case temperature", "0", "-", "85", "°C", "3"],
    ]
    w.table("2", "Recommended DC Operating Conditions", rows, [55, 150, 45, 45, 45, 40, 40],
            header_rows=2, merges=[(0, 2, 0, 4), (0, 0, 1, 0), (0, 1, 1, 1), (0, 5, 1, 5),
                                   (0, 6, 1, 6)])
    w.para("NOTE 1 DC bandwidth is limited to 20 MHz.", size=8.5, gap_after=2)
    w.para("NOTE 2 VPP must be equal to or greater than VDD at all times.", size=8.5, gap_after=2)
    w.para("NOTE 3 Refresh rate doubles (tREFI = 1.95 µs) above 85 °C.", size=8.5)

    w.heading("5.2", "AC Timing Parameters", 2)
    w.para("Timing parameters are specified for all supported speed bins. Values in nCK are "
           "rounded up to the next integer clock.")
    timing_rows = [
        ["Parameter", "Symbol", "DDR6-6400", "DDR6-9600", "Unit"],
        ["Average clock period", "tCK(avg)", "0.312", "0.208", "ns"],
        ["ACT to internal read or write delay", "tRCD", "14.375", "14.000", "ns"],
        ["Row precharge time", "tRP", "14.375", "14.000", "ns"],
        ["ACT to PRE command period", "tRAS", "32", "32", "ns"],
        ["ACT to ACT or REF command period", "tRC", "46.375", "46.000", "ns"],
        ["Write recovery time", "tWR", "30", "30", "ns"],
        ["Refresh cycle time (16 Gb)", "tRFC1", "295", "295", "ns"],
        ["Average periodic refresh interval", "tREFI", "3.9", "3.9", "µs"],
    ]
    w.table("3", "Timing Parameters", timing_rows, [170, 70, 70, 70, 40], header_rows=1)
    # continued on next page
    w.new_page()
    cont_rows = [
        ["Parameter", "Symbol", "DDR6-6400", "DDR6-9600", "Unit"],
        ["CAS to CAS delay, same bank group", "tCCD_L", "8", "12", "nCK"],
        ["CAS to CAS delay, different bank group", "tCCD_S", "8", "8", "nCK"],
        ["Read latency", "RL", "22", "32", "nCK"],
        ["DQS output access time from CK_t/CK_c", "tDQSCK", "-0.15", "-0.10", "tCK(avg)"],
    ]
    w.table("3", "Timing Parameters", cont_rows, [170, 70, 70, 70, 40], header_rows=1,
            caption_suffix=" (Cont'd)", continued=True)

    # page 8: timing diagram
    w.new_page()
    w.heading("6", "Command and Timing", 1)
    w.heading("6.1", "Read Operation", 2)
    w.para("A read burst is initiated by a RD command. The first data is driven RL = 22 nCK "
           "after the RD command for DDR6-6400, and the burst length is BL16. The data strobe "
           "DQS_t toggles with a preamble of 2 nCK.")
    x0, yb = w.figure_box(200)
    labels = draw_read_timing(c, x0, yb, w.text_width, 200)
    w.caption("Figure 2 — Read Burst Timing (BL16, RL = 22)")
    w.record_figure("2", "Read Burst Timing (BL16, RL = 22)", "vector", labels)
    w.para("NOTE 1 DES commands are shown for clarity; NOP is not supported.", size=8.5)

    # page 9: state diagram
    w.new_page()
    w.heading("6.2", "Power-Down State Machine", 2)
    w.para("The simplified state diagram in Figure 3 shows transitions between the IDLE, "
           "ACTIVE, PRECHARGE, POWER DOWN and SELF REFRESH states. Power-down entry (PDE) "
           "requires tCKE = 5 nCK.")
    x0, yb = w.figure_box(230)
    labels = draw_state_diagram(c, x0, yb, w.text_width, 230)
    w.caption("Figure 3 — Simplified Power-Down State Diagram")
    w.record_figure("3", "Simplified Power-Down State Diagram", "vector", labels)
    w.bullets(["Self refresh entry (SRE) is allowed only from IDLE.",
               "Exit from POWER DOWN (PDX) requires tXP = 7.5 ns."])

    # page 10: annex
    w.new_page()
    w.heading("Annex A", "(informative) Differences Between Revisions", 1)
    w.para("This annex briefly describes the changes made to this synthetic standard.")
    w.heading("A.1", "Changes from Revision 0.9", 2)
    w.bullets(["Added tDQSCK limits for DDR6-9600.", "Corrected VPP maximum to 1.890 V."],
              marker="–")
    tr["values"] = ["1.1 V", "0.5 V", "3.9 µs", "85 °C", "0.208 ns", "240 Ω", "200 µs",
                    "0.8 mm", "20 MHz", "1.95 µs", "22 nCK", "2 nCK", "5 nCK", "7.5 ns", "1.890 V"]
    w.save()


# ---------------------------------------------------------------------------
# sample 2: customer requirement specification (different conventions)
# ---------------------------------------------------------------------------

class CustomerWriter(SpecWriter):
    def header_right(self) -> str:
        return "ACME Confidential"


def build_customer(out: Path) -> None:
    w = CustomerWriter(out, A4, header="CRS-ACME-0042 Rev. B", footer_fmt="- {page} -",
                       margins=(64, 64, 70, 70), body_size=10)
    c = w.c
    tr = w.truth
    tr["doc_number"] = "CRS-ACME-0042"
    tr["revision"] = "B"

    c.setFont(FONT_B, 20)
    c.drawString(w.ml, w.H - 130, "Customer Requirement Specification")
    c.setFont(FONT, 13)
    c.drawString(w.ml, w.H - 155, "ACME Mobile LPDDR5X Memory Subsystem")
    c.setFont(FONT, 10)
    c.drawString(w.ml, w.H - 175, "Document No. CRS-ACME-0042, Rev. B — Synthetic sample")
    w.y = w.H - 210

    w.heading("1.", "Overview", 1, size=14)
    w.para("This specification lists the requirements of a fictional customer for an "
           "LPDDR5X x16 memory subsystem used in a handheld product. Requirement IDs of the "
           "form REQ-XXX-nnn are mandatory unless stated otherwise.")
    w.heading("1.1", "Purpose", 2, size=12)
    w.para("The memory vendor shall confirm each requirement in the compliance matrix "
           "(Table 1) within 10 business days.")
    w.heading("2.", "Requirements", 1, size=14)
    w.heading("2.1", "Power Requirements", 2, size=12)
    rows = [
        ["Req. ID", "Requirement", "Target", "Priority"],
        ["REQ-PWR-001", "Self refresh current at 25 °C", "≤ 0.8 mA", "High"],
        ["REQ-PWR-002", "Deep sleep power", "≤ 5 mW", "High"],
        ["REQ-PWR-003", "VDD2H supply range", "1.01 V to 1.12 V", "Medium"],
        ["REQ-TMP-001", "Operating temperature", "-40 °C to 95 °C", "High"],
        ["REQ-SIG-001", "Max data rate", "8533 Mbps", "Medium"],
    ]
    w.table("1", "Compliance Matrix", rows, [80, 200, 110, 60], header_rows=1)
    w.para("Requirements marked High shall be verified by test reports. REQ-SIG-001 applies "
           "to every DQ[15:0] lane.")
    w.heading("2.2", "System Integration", 2, size=12)
    w.para("Figure 1 shows the integration of the memory in the application platform. The "
           "PMIC supplies VDD2H = 1.05 V and the thermal sensor reports over I2C at 400 kHz.")
    x0, yb = w.figure_box(150)
    labels = draw_block_diagram(c, x0, yb, w.text_width, 150)
    w.caption("Figure 1 — System Block Diagram")
    w.record_figure("1", "System Block Diagram", "vector", labels)

    # borderless (text-aligned) table
    w.new_page()
    w.heading("2.3", "Qualification Schedule", 2, size=12)
    w.para("The qualification milestones are listed in Table 2.")
    w.caption("Table 2 — Qualification Milestones")
    sched = [("Milestone", "Date", "Owner"), ("Engineering samples", "2026-11-15", "Vendor"),
             ("Reliability report", "2027-01-31", "Vendor"),
             ("Customer qualification", "2027-03-15", "ACME")]
    tr["tables"].append({"number": "2", "title": "Qualification Milestones", "page": w.page,
                         "rows": [list(r) for r in sched], "header_rows": 1, "merges": [],
                         "borderless": True})
    xs = [w.ml + 20, w.ml + 200, w.ml + 320]
    for ri, r in enumerate(sched):
        c.setFont(FONT_B if ri == 0 else FONT, 9.5)
        for xi, txt in zip(xs, r):
            c.drawString(xi, w.y - 10, txt)
        w.y -= 16
        if ri == 0:
            c.setLineWidth(0.5)
            c.line(xs[0], w.y + 2, w.W - w.mr - 20, w.y + 2)
    w.y -= 10
    w.heading("3.", "Glossary", 1, size=14)
    # two-column glossary
    left = [("CRS", "Customer Requirement Specification, this document."),
            ("PMIC", "Power management integrated circuit supplying VDD1, VDD2H and VDDQ."),
            ("ES", "Engineering sample, built on a pre-production process.")]
    right = [("Rev.", "Document revision; Rev. B supersedes Rev. A."),
             ("Mbps", "Megabits per second per pin."),
             ("TBD", "To be defined in the next revision.")]
    col_w = (w.text_width - 24) / 2
    y_start = w.y
    for col_items, cx in ((left, w.ml), (right, w.ml + col_w + 24)):
        w.y = y_start
        for term, desc in col_items:
            w.para(f"{term}: {desc}", x=cx, width=col_w, gap_after=4)
    tr["two_column_terms"] = [t for t, _ in left] + [t for t, _ in right]
    w.save()


# ---------------------------------------------------------------------------
# sample 3: scanned page (no text layer)
# ---------------------------------------------------------------------------

def build_scanned(out: Path) -> None:
    W, H = LETTER
    scale = 150 / 72
    img = Image.new("L", (int(W * scale), int(H * scale)), 255)
    d = ImageDraw.Draw(img)
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        f = ImageFont.truetype(PIL_FONT, 21)
    except OSError:
        fb = f = ImageFont.load_default()
    y = 140
    d.text((150, y), "7 Legacy Timing Addendum (scanned)", font=fb, fill=0)
    y += 60
    for line in ["This page was scanned from a printed addendum and has no text layer.",
                 "tRCD shall be 18 ns minimum for legacy DDR4-2400 devices.",
                 "VDD = 1.2 V nominal, tolerance 60 mV."]:
        d.text((150, y), line, font=f, fill=0)
        y += 40
    # slight noise like a scan
    for i in range(0, img.width, 37):
        d.point((i, (i * 7) % img.height), fill=180)
    c = canvas.Canvas(str(out), pagesize=LETTER, invariant=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(ImageReader(buf), 0, 0, W, H)
    c.showPage()
    c.save()
    out.with_suffix(".truth.json").write_text(json.dumps({
        "page_count": 1, "scanned_pages": [1], "headings": [], "tables": [], "figures": [],
        "values": [], "signals": []}, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# sample 4: Korean customer spec with a page frame and an OCR'd scan page
# ---------------------------------------------------------------------------

KO_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def build_korean(out: Path) -> bool:
    if not os.path.exists(KO_FONT):
        print("WARNING: Korean font not found, skipping korean_spec.pdf")
        return False
    pdfmetrics.registerFont(TTFont("KO", KO_FONT, subfontIndex=0))
    W, H = A4
    c = canvas.Canvas(str(out), pagesize=A4, invariant=1)
    truth = {"headings": [], "tables": [], "figures": [], "page_count": 3}
    ml = 64

    def text(x, y, s, size=10.0, font="KO", invisible=False):
        t = c.beginText(x, y)
        t.setFont(font, size)
        if invisible:
            t.setTextRenderMode(3)
        t.textLine(s)
        c.drawText(t)

    def header_footer(n):
        c.setFont("KO", 8)
        c.drawString(ml, H - 40, "사양서 번호 KCS-2026-007")
        c.drawRightString(W - ml, H - 40, "대외비")
        c.drawCentredString(W / 2, 30, f"- {n} -")

    # page 1: frame + headings + ruled table
    header_footer(1)
    c.setLineWidth(1)
    c.rect(40, 50, W - 80, H - 110)                     # frame around the body
    text(ml, H - 100, "고객 요구 사양서 — 메모리 모듈", 20)
    y = H - 150
    text(ml, y, "1. 개요", 14); truth["headings"].append(["1", "개요", 1]); y -= 26
    for ln in ["본 문서는 고객사 메모리 모듈의 전기적 요구사항을 정의한다. 공급 전압 VDD는 1.1 V이며",
               "동작 온도 범위는 -40 °C 에서 95 °C 까지로 한다. 모든 수치는 예시 값이다."]:
        text(ml, y, ln); y -= 14
    y -= 12
    text(ml, y, "1.1 적용 범위", 12); truth["headings"].append(["1.1", "적용 범위", 2]); y -= 22
    text(ml, y, "본 요구사항은 모든 양산 제품에 적용하며, 시료 평가 결과는 30 일 이내에 제출한다."); y -= 30
    c.setFont("KO", 10)
    c.drawCentredString(W / 2, y, "표 1. 전원 요구사항"); y -= 10
    rows = [["항목", "요구값", "비고"], ["VDD", "1.1 V ± 3%", "코어 전원"], ["VDDQ", "0.5 V", "I/O 전원"],
            ["대기 전류", "≤ 5 mA", "25 °C 기준"]]
    widths = [120, 140, 140]
    x0 = (W - sum(widths)) / 2
    for r, row in enumerate(rows):
        x = x0
        for wd, val in zip(widths, row):
            c.rect(x, y - 20, wd, 20)
            c.setFont("KO", 9)
            c.drawCentredString(x + wd / 2, y - 14, val)
            x += wd
        y -= 20
    truth["tables"].append({"number": "1", "title": "전원 요구사항", "rows": rows, "header_rows": 1, "merges": []})
    c.showPage()

    # page 2: figure with Korean caption
    header_footer(2)
    y = H - 100
    text(ml, y, "2. 시스템 구성", 14); truth["headings"].append(["2", "시스템 구성", 1]); y -= 26
    text(ml, y, "그림 1은 모듈과 호스트의 연결 구성을 나타낸다. 전원은 PMIC에서 공급된다."); y -= 30
    boxes = [("호스트 SoC", ml + 10, y - 90), ("메모리 모듈", ml + 300, y - 90), ("PMIC", ml + 160, y - 170)]
    for label, bx, by in boxes:
        c.rect(bx, by, 120, 44)
        c.setFont("KO", 9)
        c.drawCentredString(bx + 60, by + 18, label)
    arrow(c, ml + 130, y - 68, ml + 300, y - 68)
    arrow(c, ml + 220, y - 126, ml + 70, y - 90)
    c.setFont("KO", 8)
    c.drawString(ml + 170, y - 62, "CA[6:0], CK_t")
    c.setFont("KO", 10)
    c.drawCentredString(W / 2, y - 190, "그림 1. 시스템 블록도")
    truth["figures"].append({"number": "1", "title": "시스템 블록도", "page": 2,
                             "labels": ["호스트 SoC", "메모리 모듈", "PMIC", "CA[6:0], CK_t"]})
    c.showPage()

    # page 3: scanned page image with an invisible OCR text layer (typical "searchable PDF")
    scale = 110 / 72
    img = Image.new("L", (int(W * scale), int(H * scale)), 250)
    d = ImageDraw.Draw(img)
    for i in range(0, img.height, 9):
        d.line([(0, i), (img.width, i)], fill=244)        # scanner noise
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(ImageReader(buf), 0, 0, W, H)
    text(ml, H - 100, "3. 신뢰성 시험", 14, invisible=True)
    truth["headings"].append(["3", "신뢰성 시험", 1])
    text(ml, H - 130, "고온 동작 수명 시험은 125 °C 에서 1000 시간 동안 수행하며 불량률은 0.1 % 이하로 한다.",
         invisible=True)
    text(ml, H - 144, "시험 결과 보고서는 시험 종료 후 14 일 이내에 제출한다.", invisible=True)
    truth["scan_text_layer_page"] = 3
    truth["values"] = ["1.1 V", "125 °C", "1000 시간", "5 mA"]
    c.showPage()
    c.save()
    out.with_suffix(".truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else HERE
    out_dir.mkdir(parents=True, exist_ok=True)
    build_jedec_like(out_dir / "jedec_like_spec.pdf")
    build_customer(out_dir / "customer_spec.pdf")
    build_scanned(out_dir / "scanned_addendum.pdf")
    build_korean(out_dir / "korean_spec.pdf")
    selftest = HERE.parent / "src" / "spec2kb" / "selftest" / "sample.pdf"
    if out_dir == HERE and selftest.parent.exists():
        selftest.write_bytes((out_dir / "jedec_like_spec.pdf").read_bytes())
    for p in sorted(out_dir.glob("*.pdf")):
        print(f"wrote {p} ({p.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
