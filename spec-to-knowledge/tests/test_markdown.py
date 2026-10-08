from __future__ import annotations

import re

import markdown as md_lib

from spec2kb.exporter import build_kb, KbItem
from spec2kb.exporter.markdown import (MarkdownRenderer, escape_inline, escape_text, render_gfm_table,
                                       render_html_table)
from spec2kb.schema import Cell, Table
from spec2kb.validator.tokens import markdown_to_plain


def _table(rows, header_rows=1, merges=()):
    cells = []
    covered = set()
    for r0, c0, r1, c1 in merges:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                covered.add((r, c))
        cells.append(Cell(row=r0, col=c0, rowspan=r1 - r0 + 1, colspan=c1 - c0 + 1, text=rows[r0][c0],
                          header=r0 < header_rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if (r, c) not in covered:
                cells.append(Cell(row=r, col=c, text=v, header=r < header_rows))
    return Table(id="t", page=1, bbox=[0, 0, 1, 1], n_rows=len(rows), n_cols=len(rows[0]), header_rows=header_rows,
                 cells=cells)


def test_escaping_keeps_signal_names_greppable():
    s = "Signals CK_t, DQS_c and CA[13:0]; suffix _n means *active low* <CK> 2.5 < 3"
    e = escape_inline(s)
    assert "CK_t" in e and "DQS_c" in e and "CA[13:0]" in e
    assert "\\_n" in e and "\\*active low\\*" in e and "&lt;CK>" in e and "< 3" in e
    html = md_lib.markdown(escape_text(s))
    assert "<em>" not in html and "CK_t" in html and "_n means" in html
    assert markdown_to_plain(escape_text(s)).strip() == s.replace("<CK>", "<CK>")
    assert escape_text("1. Overview") == "1\\. Overview"
    assert escape_text("# not a heading").startswith("\\#")


def test_gfm_table_fill_and_escape():
    t = _table([["Name", "Value"], ["A|B", "1.1 V"], ["C_t", "*"]])
    out = render_gfm_table(t)
    assert out.splitlines()[0] == "| Name | Value |"
    assert "A\\|B" in out and "\\*" in out
    html = md_lib.markdown(out, extensions=["tables"])
    assert html.count("<tr>") == 3 and "A|B" in html


def test_html_table_spans_roundtrip():
    rows = [["Symbol", "Rating", "", "Unit"], ["", "Min", "Max", ""], ["VDD", "1.0", "1.2", "V"]]
    t = _table(rows, header_rows=2, merges=[(0, 1, 0, 2), (0, 0, 1, 0), (0, 3, 1, 3)])
    out = render_html_table(t)
    assert '<th colspan="2">Rating</th>' in out and '<th rowspan="2">Symbol</th>' in out
    from spec2kb.validator.checks import table_shape_from_markdown
    assert table_shape_from_markdown(out) == (3, 4, False)
    gfm = render_gfm_table(t)
    assert gfm.splitlines()[0] == "| Symbol | Rating / Min | Rating / Max | Unit |"


def test_kb_layouts_and_frontmatter_consistency(parse_sample, tmp_path):
    items = []
    for name, prof in (("jedec_like_spec", "jedec"), ("customer_spec", "customer")):
        doc, profile, assets, _ = parse_sample(name, prof)
        items.append(KbItem(doc, profile, assets))
    for layout in ("mkdocs", "wiki"):
        root = tmp_path / layout
        exports = build_kb(items, root, "KB", layout=layout)
        keys = set()
        md_files = [p for p in root.rglob("*.md") if "_meta" not in p.parts and p.name not in ("README.md", "_Sidebar.md")]
        for p in md_files:
            text = p.read_text(encoding="utf-8")
            assert text.startswith("---\n"), p
            fm = text.split("\n---", 1)[0]
            if p.name in ("index.md", "Home.md"):
                continue
            keys.add(tuple(re.findall(r"^(\w+):", fm, re.M)))
            assert "](/" not in text  # never absolute links
        assert len(keys) == 1, keys  # every section file of every document has the same frontmatter keys
        if layout == "wiki":
            assert (root / "Home.md").exists() and (root / "_Sidebar.md").exists()
            idx = (root / "jesd-syn-01.md").read_text(encoding="utf-8")
            assert "(jesd-syn-01--02-scope)" in idx
            assert (root / "assets" / "jesd-syn-01" / "fig-2.png").exists()
        else:
            assert (root / "mkdocs.yml").exists()
            idx = (root / "docs" / "jesd-syn-01" / "index.md").read_text(encoding="utf-8")
            assert "(02-scope.md)" in idx
            assert (root / "docs" / "jesd-syn-01" / "assets" / "fig-2.png").exists()
        for e in exports:
            assert e.missing_assets == []
            smap = e.source_map
            assert smap["files"] and all("line_start" in b for f in smap["files"] for b in f["blocks"])


def test_renderer_lists_notes_and_overrides(parse_sample):
    doc, profile, _, _ = parse_sample("jedec_like_spec", "jedec")
    r = MarkdownRenderer(doc, profile)
    li = next(b for b in doc.blocks if b.type == "list_item" and b.label == "–")
    assert r.render_block(li).startswith("- Added tDQSCK")
    note = next(b for b in doc.blocks if b.type == "note")
    assert r.render_block(note).startswith("> **NOTE 1** Unused CA inputs")
    h = next(b for b in doc.blocks if b.type == "heading" and b.number == "4.1")
    assert r.render_block(h, 2) == "## 4.1 Signal Description"
    b2 = h.model_copy(update={"md_override": "## Custom"})
    assert r.render_block(b2) == "## Custom"
