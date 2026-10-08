from __future__ import annotations

from spec2kb.profiles.model import Profile
from spec2kb.validator import apply_validation, check_export
from spec2kb.validator.tokens import extract_tokens, markdown_to_plain, similar_values

P = Profile(id="t", name="t")
V = P.validation


def test_token_extraction_units_signals():
    ts = extract_tokens("VDD = 1.1 V, tREFI 3.9 µs (3.9 μs), 240 Ω, 85 °C, CK_t/CK_c CA[13:0] tCK(avg) 0.208 ns, 9600 MT/s",
                        V.units, V.signal_patterns, [r"\bREQ-[A-Z]+-\d+\b"])
    assert ts.values["3.9 us"] == 2       # µ (micro sign) and μ (Greek mu) normalize together
    assert {"1.1 V", "240 Ω", "85 °C", "0.208 ns", "9600 MT/s"} <= set(ts.values)
    assert {"CK_t", "CK_c", "CA[13:0]", "tCK(avg)", "VDD", "tREFI"} <= set(ts.signals)
    assert similar_values("1.067 V", ["1.07 V", "2 V"]) == ["1.07 V"]
    assert similar_values("0.625 ns", ["0.625 us"]) == ["0.625 us"]


def test_markdown_to_plain_tables_and_escapes():
    md = "**Table 1 — X**\n\n| A | B |\n|---|---|\n| CK\\_t | 1\\*2 |\n\n<table><tr><td>VDD</td><td>1.1</td></tr></table>\n\n<!-- p.3 -->\n> **NOTE 1** text"
    plain = markdown_to_plain(md)
    assert "CK_t 1*2" in plain and "VDD 1.1" in plain and "p.3" not in plain and "NOTE 1 text" in plain


def _doc(parse_sample):
    doc, profile, assets, _ = parse_sample("jedec_like_spec", "jedec")
    return doc.model_copy(deep=True), profile, assets


def test_clean_document_has_no_fidelity_errors(parse_sample):
    doc, profile, assets = _doc(parse_sample)
    apply_validation(doc, profile, assets)
    bad = [i for i in doc.issues if i.code in ("value_missing", "number_missing", "number_distorted", "signal_missing",
                                               "table_ragged", "table_rows_changed", "table_cols_changed")]
    assert bad == []


def test_detects_dropped_value_and_distorted_table_number(parse_sample):
    doc, profile, assets = _doc(parse_sample)
    para = next(b for b in doc.blocks if "3.9 µs" in b.text)
    para.md_override = para.text.replace("3.9 µs", "3.9 ms")
    t2 = doc.table("tbl-2")
    from spec2kb.exporter.markdown import MarkdownRenderer
    t2.md_override = MarkdownRenderer(doc, profile).render_table(t2).replace("<td>1.067</td>", "<td>1.07</td>")
    apply_validation(doc, profile, assets)
    v = next(i for i in doc.issues if i.code == "value_missing" and i.page == para.page)
    assert "3.9 µs" in v.message and "3.9 ms" in v.message   # unit change shown as distortion
    d = next(i for i in doc.issues if i.code == "number_distorted" and i.page == 6)
    assert "1.067 → 1.07" in d.message
    assert doc.page(6).status == "error"


def test_table_structure_change_detected(parse_sample):
    doc, profile, assets = _doc(parse_sample)
    t1 = doc.table("tbl-1")
    from spec2kb.exporter.markdown import MarkdownRenderer
    md = MarkdownRenderer(doc, profile).render_table(t1)
    lines = md.splitlines()
    lines[-1] = lines[-1] + " extra |"          # ragged last row
    t1.md_override = "\n".join(lines)
    apply_validation(doc, profile, assets)
    assert any(i.code == "table_ragged" and i.ref == "tbl-1" for i in doc.issues)


def test_signal_dropped(parse_sample):
    doc, profile, assets = _doc(parse_sample)
    b = next(b for b in doc.blocks if "RESET_n" not in b.text and "DQS_t toggles" in b.text)
    b.md_override = b.text.replace("DQS_t", "DQS")
    apply_validation(doc, profile, assets)
    # DQS_t still appears in the figure labels on the same page: occurrence counts catch the loss
    assert any(i.code == "signal_missing" and "DQS_t" in i.message and i.page == b.page for i in doc.issues)


def test_issue_status_survives_revalidation(parse_sample):
    doc, profile, assets = _doc(parse_sample)
    b = next(b for b in doc.blocks if "0.8 mm" in b.text)
    b.md_override = "The ball pitch is defined elsewhere."
    apply_validation(doc, profile, assets)
    issue = next(i for i in doc.issues if i.code == "value_missing")
    apply_validation(doc, profile, assets, {issue.id: "ignored"})
    assert next(i for i in doc.issues if i.id == issue.id).status == "ignored"


def test_export_link_checker():
    files = {"docs/a/index.md": "---\ntitle: x\n---\n[ok](01-x.md) ![img](assets/f.png) [bad](02-missing.md) [abs](/etc/x)",
             "docs/a/01-x.md": "---\ntitle: y\n---\n"}
    issues = check_export(files, set(files) | {"docs/a/assets/f.png"}, "mkdocs", ["title"])
    codes = sorted(i.code for i in issues)
    assert codes == ["absolute_link", "broken_link"]
    wiki = {"Home.md": "---\ntitle: x\n---\n[d](doc) [b](nope)", "doc.md": "---\ntitle: d\n---\n"}
    issues = check_export(wiki, set(wiki), "wiki", ["title"])
    assert [i.message.split("→ ")[-1] for i in issues] == ["nope"]
