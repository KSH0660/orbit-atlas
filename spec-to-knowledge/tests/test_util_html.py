from __future__ import annotations

import pytest

from spec2kb.htmlrender import render_markdown, sanitize
from spec2kb.util import format_page_list, parse_page_range, safe_join, slugify


def test_page_ranges():
    assert parse_page_range("", 5) == [1, 2, 3, 4, 5]
    assert parse_page_range("1-3, 5", 10) == [1, 2, 3, 5]
    assert parse_page_range("8-", 10) == [8, 9, 10]
    assert parse_page_range("-2", 10) == [1, 2]
    assert parse_page_range("5-3", 10) == [3, 4, 5]
    with pytest.raises(ValueError):
        parse_page_range("abc", 10)
    with pytest.raises(ValueError):
        parse_page_range("20-30", 10)
    assert format_page_list([1, 2, 3, 5, 7, 8]) == "1-3, 5, 7-8"


def test_slug_and_safe_join(tmp_path):
    assert slugify("Annex A (informative) Differences") == "annex-a-informative-differences"
    assert slugify("한글 제목") == "section"
    assert safe_join(tmp_path, "a/b.png") == (tmp_path / "a/b.png").resolve()
    for bad in ("../x", "a/../../x", "/etc/passwd/../../.."):
        with pytest.raises(ValueError):
            safe_join(tmp_path / "sub", bad)


def test_preview_sanitizer_blocks_scripts():
    dirty = ('<p onclick="x()">hi</p><script>alert(1)</script><img src="javascript:alert(1)" onerror="y()">'
             '<a href="javascript:evil()">l</a><table><tr><td rowspan="2" style="color:red">c</td></tr></table>'
             '<iframe src="http://x"></iframe><img src="data:image/png;base64,AAA">')
    clean = sanitize(dirty)
    assert "script" not in clean and "onclick" not in clean and "onerror" not in clean
    assert "javascript:" not in clean and "iframe" not in clean and "style" not in clean
    assert 'rowspan="2"' in clean and "<p>hi</p>" in clean and "data:image/png" in clean


def test_render_markdown_tables_and_frontmatter():
    md = "---\ntitle: \"x\"\n---\n\n# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n![f](assets/f.png)\n"
    html = render_markdown(md, lambda tag, url: "/api/x/" + url if tag == "img" else url)
    assert "title:" not in html and "<table>" in html and 'src="/api/x/assets/f.png"' in html
