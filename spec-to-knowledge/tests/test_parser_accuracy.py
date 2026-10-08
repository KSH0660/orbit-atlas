"""Parsing accuracy against the ground truth of the synthetic samples."""

from __future__ import annotations

import re


def _filled(table) -> list[list[str]]:
    grid = [[""] * table.n_cols for _ in range(table.n_rows)]
    for c in table.cells:
        for r in range(c.row, c.row + c.rowspan):
            for k in range(c.col, c.col + c.colspan):
                grid[r][k] = c.text
    return grid


def _truth_filled(t: dict) -> list[list[str]]:
    rows = [list(r) for r in t["rows"]]
    for r0, c0, r1, c1 in t.get("merges", []):
        v = rows[r0][c0]
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                rows[r][c] = v
    return rows


def test_jedec_headings_exact(parse_sample, truth):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    t = truth("jedec_like_spec")
    got = [(b.number or "", b.text, b.level) for b in doc.blocks if b.type == "heading"]
    exp = []
    for hd in t["headings"]:
        num = hd["number"]
        exp.append((num, hd["title"], hd["level"]))
    assert got == exp


def test_jedec_toc_and_furniture_removed(parse_sample):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    assert doc.page(2).kind == "toc"
    assert doc.page(1).kind == "cover"
    all_text = "\n".join(b.text for b in doc.blocks)
    assert "JEDEC-Style Sample Standard No. SYN-01" not in all_text
    assert not re.search(r"^Page \d+$", all_text, re.M)
    assert "........" not in all_text  # TOC leaders never reach the body
    for p in doc.pages[2:]:
        assert any("Page" in r for r in p.removed_lines)


def test_jedec_tables_cell_exact(parse_sample, truth):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    t = truth("jedec_like_spec")
    expected: dict[str, dict] = {}
    for tt in t["tables"]:
        if tt.get("continued"):
            base = expected[tt["number"]]
            base["rows"] = base["rows"] + tt["rows"][tt["header_rows"]:]
            continue
        expected[tt["number"]] = {**tt, "rows": [list(r) for r in tt["rows"]]}
    assert sorted(x.number for x in doc.tables) == sorted(expected)
    for table in doc.tables:
        exp = expected[table.number]
        assert table.title == exp["title"]
        assert table.header_rows == exp["header_rows"]
        assert _filled(table) == _truth_filled(exp), table.number
    t2 = next(x for x in doc.tables if x.number == "2")
    spans = {(c.row, c.col, c.rowspan, c.colspan) for c in t2.cells if c.rowspan > 1 or c.colspan > 1}
    assert (0, 2, 1, 3) in spans and (0, 0, 2, 1) in spans
    t3 = next(x for x in doc.tables if x.number == "3")
    assert [p.page for p in t3.parts] == [6, 7]


def test_jedec_figures(parse_sample, truth):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    t = truth("jedec_like_spec")
    figs = {f.number: f for f in doc.figures}
    assert sorted(figs) == sorted(x["number"] for x in t["figures"])
    for exp in t["figures"]:
        f = figs[exp["number"]]
        assert f.title == exp["title"]
        assert f.page == exp["page"]
        assert f.kind == exp["kind"]
        assert f.asset and f.width_px > 100
        embedded = " ".join(f.embedded_text)
        for label in exp["labels"]:
            assert label in embedded, (exp["number"], label)
        # captions never leak into the drawing text
        assert not any(x.startswith("Figure") for x in f.embedded_text)


def test_jedec_body_keeps_values_and_lists(parse_sample, truth):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    text = " ".join([b.text for b in doc.blocks] + [c.text for t in doc.tables for c in t.cells]
                    + [x for f in doc.figures for x in f.embedded_text])
    for v in truth("jedec_like_spec")["values"]:
        assert v in text, v
    notes = [b for b in doc.blocks if b.type == "note"]
    assert [n.label for n in notes][:1] == ["NOTE 1"]
    bullets = [b for b in doc.blocks if b.type == "list_item"]
    assert len(bullets) == 7
    assert doc.metadata.doc_number == "JESD-SYN-01"
    assert doc.metadata.revision == "1.0"
    assert doc.metadata.title == "Synthetic DDR6 SDRAM Specification"


def test_customer_layout_variants(parse_sample, truth):
    doc, *_ = parse_sample("customer_spec", "customer")
    t = truth("customer_spec")
    heads = [(b.number, b.text, b.level) for b in doc.blocks if b.type == "heading"]
    assert heads == [(h["number"].rstrip("."), h["title"], h["level"]) for h in t["headings"]]
    t1 = next(x for x in doc.tables if x.number == "1")
    assert _filled(t1) == _truth_filled(t["tables"][0])
    t2 = next(x for x in doc.tables if x.number == "2")
    assert t2.method == "text"
    assert _filled(t2) == [list(r) for r in t["tables"][1]["rows"]]
    fig = doc.figures[0]
    assert fig.number == "1" and fig.title == "System Block Diagram"
    assert "Application SoC" in fig.embedded_text
    # two-column glossary is read left column first, then right column
    glossary = [b.text.split(":")[0] for b in doc.blocks if b.page == 3 and b.type == "paragraph" and ":" in b.text[:6]]
    assert glossary == t["two_column_terms"]
    assert doc.metadata.doc_number == "CRS-ACME-0042"
    assert doc.metadata.revision == "B"


def test_scanned_page_detected(parse_sample):
    doc, *_ = parse_sample("scanned_addendum", "general")
    assert doc.pages[0].kind == "scanned"
    assert doc.figures[0].kind == "page"
    assert any(i.code == "scanned_page" for i in doc.issues)


def test_reading_order_and_ids_stable(parse_sample):
    doc, *_ = parse_sample("jedec_like_spec", "jedec")
    ids = [b.id for b in doc.blocks]
    assert len(ids) == len(set(ids))
    pages = [b.page for b in doc.blocks]
    assert pages == sorted(pages)
    table_refs = [b.ref for b in doc.blocks if b.type == "table"]
    assert table_refs == ["tbl-1", "tbl-2", "tbl-3"]
