"""Markdown -> safe HTML for in-app previews (Python-Markdown, the same engine MkDocs uses)."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Callable

import markdown as md_lib

EXTENSIONS = ["tables", "toc", "md_in_html", "admonition", "attr_list", "fenced_code"]

ALLOWED = {
    "p": set(), "h1": {"id"}, "h2": {"id"}, "h3": {"id"}, "h4": {"id"}, "h5": {"id"}, "h6": {"id"},
    "ul": set(), "ol": {"start"}, "li": set(), "table": set(), "thead": set(), "tbody": set(), "tr": set(),
    "th": {"rowspan", "colspan", "align", "style"}, "td": {"rowspan", "colspan", "align", "style"},
    "blockquote": set(), "strong": set(), "em": set(), "code": set(), "pre": set(), "img": {"src", "alt", "title"},
    "a": {"href", "title", "class"}, "br": set(), "hr": set(), "details": {"open"}, "summary": set(),
    "div": {"class"}, "span": {"class"}, "sup": set(), "sub": set(), "del": set(), "b": set(), "i": set(),
}
VOID = {"br", "hr", "img"}
DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript", "template"}
STYLE_RE = re.compile(r"^\s*text-align:\s*(left|right|center);?\s*$")


class _Sanitizer(HTMLParser):
    def __init__(self, url_rewrite: Callable[[str, str], str] | None):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip = 0
        self.rewrite = url_rewrite

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        kept = []
        for k, v in attrs:
            if k not in ALLOWED[tag] or v is None:
                continue
            if k in ("href", "src"):
                v = v.strip()
                if re.match(r"(?i)^\s*(javascript|vbscript|data):", v) and not (tag == "img" and v.startswith("data:image/")):
                    continue
                if self.rewrite:
                    v = self.rewrite(tag, v)
            if k == "style" and not STYLE_RE.match(v):
                continue
            kept.append(f' {k}="{html.escape(v, quote=True)}"')
        self.out.append(f"<{tag}{''.join(kept)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in ALLOWED or tag in VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(f"&#{name};")


def sanitize(html_text: str, url_rewrite: Callable[[str, str], str] | None = None) -> str:
    s = _Sanitizer(url_rewrite)
    s.feed(html_text)
    s.close()
    return "".join(s.out)


def strip_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            return text[4:end], text[end + 4:].lstrip("\n")
    return "", text


def render_markdown(text: str, url_rewrite: Callable[[str, str], str] | None = None) -> str:
    _, body = strip_frontmatter(text)
    raw = md_lib.markdown(body, extensions=EXTENSIONS, output_format="html")
    return sanitize(raw, url_rewrite)
