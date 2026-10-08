"""Block-level Markdown rendering with one set of formatting rules for every document.

Conventions (identical for all documents and profiles):
* one block = one Markdown paragraph; no hard wraps inside paragraphs
* headings carry their section number ("4.1 Signal Description")
* list items always use "- "; enumerators such as "a)" are kept as text
* notes become blockquotes starting with the bold label ("> **NOTE 1** ...")
* tables: bold caption line, then a GFM pipe table (simple tables) or an HTML
  table (merged cells / multi-row headers) so that no structure is lost
* figures: image, italic caption, AI description block with provenance,
  then the text found inside the figure (searchable)
* minimal escaping: signal names such as CK_t or CA[13:0] stay greppable
"""

from __future__ import annotations

import html
import re
from typing import Callable

from ..profiles.model import Profile
from ..schema import Block, CanonicalDocument, Figure, Table

LIST_BULLETS = set("•●▪■◦○–—*·-")


def escape_inline(text: str) -> str:
    t = text.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*")
    t = re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", r"\\_", t)
    t = re.sub(r"<(?=[A-Za-z/!?])", "&lt;", t)
    t = re.sub(r"\[(?=[^\]]*\]\s*[(\[])", r"\\[", t)
    return t


def escape_block_start(text: str) -> str:
    m = re.match(r"^(\d+)([.)])(\s)", text)
    if m:
        return f"{m.group(1)}\\{m.group(2)}{text[len(m.group(1)) + 1:]}"
    if re.match(r"^(#{1,6}(\s|$)|>|[-+*](\s|$)|={3,}\s*$|-{3,}\s*$|\||:)", text):
        return "\\" + text
    return text


def escape_text(text: str) -> str:
    return escape_block_start(escape_inline(text.strip()))


def escape_cell(text: str) -> str:
    t = escape_inline(text.strip()).replace("|", "\\|")
    return t.replace("\n", "<br>")


def heading_text(b: Block, profile: Profile) -> str:
    if b.number and profile.markdown.heading_numbers:
        return f"{b.number} {b.text}".strip()
    return b.text.strip()


def table_caption(t: Table, prefix: str = "Table") -> str:
    if t.number:
        return f"{prefix} {t.number} — {t.title}".rstrip(" —") if t.title else f"{prefix} {t.number}"
    return t.caption or ""


def figure_caption(f: Figure, prefix: str = "Figure") -> str:
    if f.kind == "page":
        return f.title
    if f.number:
        return f"{prefix} {f.number} — {f.title}".rstrip(" —") if f.title else f"{prefix} {f.number}"
    return f.caption or f.title or ""


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def table_needs_html(t: Table) -> bool:
    return t.has_spans() or t.header_rows > 1


def render_gfm_table(t: Table) -> str:
    g = t.grid()
    # fill spans by repetition so every row has n_cols cells
    filled: list[list[str]] = [[""] * t.n_cols for _ in range(t.n_rows)]
    for c in t.cells:
        for r in range(c.row, min(t.n_rows, c.row + c.rowspan)):
            for k in range(c.col, min(t.n_cols, c.col + c.colspan)):
                filled[r][k] = c.text
    del g
    h = max(1, t.header_rows)
    header: list[str] = []
    for col in range(t.n_cols):
        parts: list[str] = []
        for r in range(min(h, t.n_rows)):
            v = filled[r][col].strip()
            if v and v not in parts:
                parts.append(v)
        header.append(" / ".join(parts))
    body = filled[h:] if t.n_rows > h else []
    lines = ["| " + " | ".join(escape_cell(x) for x in header) + " |",
             "|" + "|".join(["---"] * t.n_cols) + "|"]
    for row in body:
        lines.append("| " + " | ".join(escape_cell(x) for x in row) + " |")
    return "\n".join(lines)


def render_html_table(t: Table) -> str:
    g = t.grid()
    covered: set[tuple[int, int]] = set()
    for c in t.cells:
        for r in range(c.row, c.row + c.rowspan):
            for k in range(c.col, c.col + c.colspan):
                if (r, k) != (c.row, c.col):
                    covered.add((r, k))
    out = ["<table>"]
    h = t.header_rows
    for section, rows in (("thead", range(0, min(h, t.n_rows))), ("tbody", range(h, t.n_rows))):
        if not len(rows):
            continue
        out.append(f"<{section}>")
        for r in rows:
            cells = []
            for k in range(t.n_cols):
                if (r, k) in covered:
                    continue
                c = g[r][k]
                tag = "th" if r < h else "td"
                attrs = ""
                text = ""
                if c is not None:
                    if c.rowspan > 1:
                        attrs += f' rowspan="{c.rowspan}"'
                    if c.colspan > 1:
                        attrs += f' colspan="{c.colspan}"'
                    text = html.escape(c.text.strip(), quote=False).replace("\n", "<br>")
                cells.append(f"<{tag}{attrs}>{text}</{tag}>")
            out.append("<tr>" + "".join(cells) + "</tr>")
        out.append(f"</{section}>")
    out.append("</table>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# renderer
# ---------------------------------------------------------------------------

class MarkdownRenderer:
    """Renders canonical blocks to Markdown fragments (one fragment per block)."""

    def __init__(self, doc: CanonicalDocument, profile: Profile,
                 asset_path: Callable[[str], str] | None = None):
        self.doc = doc
        self.profile = profile
        self.md = profile.markdown
        self.labels = profile.markdown.labels
        self.asset_path = asset_path or (lambda name: f"assets/{name}")
        self._tables = {t.id: t for t in doc.tables}
        self._figures = {f.id: f for f in doc.figures}

    # -- public ------------------------------------------------------------------
    def render_block(self, b: Block, heading_level: int | None = None) -> str:
        if b.type == "table":
            t = self._tables.get(b.ref or "")
            return self.render_table(t) if t else ""
        if b.type == "figure":
            f = self._figures.get(b.ref or "")
            return self.render_figure(f) if f else ""
        if b.md_override is not None:
            return b.md_override.strip()
        if b.type == "heading":
            level = max(1, min(6, heading_level or b.level or 1))
            return "#" * level + " " + escape_inline(heading_text(b, self.profile))
        if b.type == "list_item":
            label = (b.label or "").strip()
            text = escape_inline(b.text.strip())
            if label and label not in LIST_BULLETS:
                return f"- {escape_inline(label)} {text}"
            return f"- {text}"
        if b.type == "note":
            label = (b.label or "NOTE").strip()
            return f"> **{escape_inline(label)}** {escape_inline(b.text.strip())}"
        return escape_text(b.text)

    def render_table(self, t: Table) -> str:
        if t.md_override is not None:
            return t.md_override.strip()
        parts: list[str] = []
        cap = table_caption(t, self.labels.table_prefix)
        if cap:
            if self.md.source_refs == "inline":
                cap = f"{cap} ({self.labels.page} {self._pages_label(t)})"
            parts.append(f"**{escape_inline(cap)}**")
        fmt = self.md.table_format
        use_html = fmt == "html" or (fmt == "auto" and table_needs_html(t))
        parts.append(render_html_table(t) if use_html else render_gfm_table(t))
        if self.md.include_table_snapshot_link and t.snapshot:
            parts.append(f"[{escape_inline(self.labels.table_snapshot)}]({self.asset_path(self.table_asset_name(t))})")
        return "\n\n".join(parts)

    def render_figure(self, f: Figure) -> str:
        if f.md_override is not None:
            return f.md_override.strip()
        parts: list[str] = []
        cap = figure_caption(f, self.labels.figure_prefix)
        alt = cap.replace("[", "(").replace("]", ")").replace("\n", " ") or f.id
        if f.asset:
            parts.append(f"![{alt}]({self.asset_path(self.figure_asset_name(f))})")
        if f.kind == "page":
            cap = f"{cap} ({self.labels.scanned_note})"
        if cap:
            cap_line = cap
            if self.md.source_refs == "inline":
                cap_line = f"{cap} ({self.labels.page} {f.page})"
            parts.append(f"*{escape_inline(cap_line)}*")
        desc = self.render_description(f)
        if desc:
            parts.append(desc)
        if self.md.include_embedded_text and f.embedded_text and f.kind != "page":
            joined = " · ".join(escape_inline(t) for t in f.embedded_text)
            parts.append(f"**{escape_inline(self.labels.figure_text)}:** {joined}")
        return "\n\n".join(parts)

    def render_description(self, f: Figure) -> str:
        if f.description_override is not None and f.description_override.strip():
            title = self.labels.reviewed_description
            return self._wrap(title, f.description_override.strip().splitlines())
        d = f.description
        if d is None or d.status in ("failed", "skipped", "pending") or not (d.summary or d.sections):
            return ""
        meta = [d.image_type]
        if d.model:
            meta.append(d.model)
        meta.append(self.labels.unverified)
        title = f"{self.labels.ai_description} ({' · '.join(meta)})"
        lines: list[str] = []
        if d.summary:
            lines.append(escape_text(d.summary))
        for s in d.sections:
            if not s.items:
                continue
            lines += ["", f"**{escape_inline(s.title)}**", ""]
            lines += [f"- {escape_inline(i)}" for i in s.items]
        if d.uncertain:
            lines += ["", f"**{escape_inline(self.labels.uncertain)}**", ""]
            lines += [f"- {escape_inline(i)}" for i in d.uncertain]
        return self._wrap(title, lines)

    def _wrap(self, title: str, lines: list[str]) -> str:
        style = self.md.figure_description_style
        if style == "admonition":
            body = "\n".join(("    " + ln) if ln else "" for ln in lines)
            return f'!!! note "{title.replace(chr(34), chr(39))}"\n\n{body}'
        if style == "details":
            body = "\n".join(lines)
            return f'<details markdown="1">\n<summary>{html.escape(title)}</summary>\n\n{body}\n\n</details>'
        out = [f"> **{escape_inline(title)}**", ">"]
        out += [f"> {ln}" if ln else ">" for ln in lines]
        return "\n".join(out)

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def figure_asset_name(f: Figure) -> str:
        return f"{f.id}.png"

    @staticmethod
    def table_asset_name(t: Table, part: int = 0) -> str:
        return f"{t.id}.png" if part == 0 else f"{t.id}-part{part + 1}.png"

    def _pages_label(self, t: Table) -> str:
        pages = sorted({p.page for p in t.parts} or {t.page})
        return f"{pages[0]}–{pages[-1]}" if len(pages) > 1 else str(pages[0])
