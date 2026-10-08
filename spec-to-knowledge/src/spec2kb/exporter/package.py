"""Knowledge-base packaging: file layout, frontmatter, index pages, source map, mkdocs.yml, ZIP.

Layouts
  mkdocs : <kb>/mkdocs.yml, <kb>/docs/index.md, <kb>/docs/<doc>/index.md, NN-<section>.md, assets/
  wiki   : <kb>/Home.md, <kb>/_Sidebar.md, <kb>/<doc>.md, <doc>--NN-<section>.md, assets/<doc>/
Both use only relative links, so the tree works in MkDocs, GitLab/GitHub/Gitea wikis
and plain Git repository browsers.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from ..profiles.model import Profile
from ..schema import Block, CanonicalDocument, utcnow
from ..util import format_page_list, slugify
from .markdown import MarkdownRenderer, figure_caption, heading_text, table_caption


def yaml_str(s: Any) -> str:
    s = "" if s is None else str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def yaml_value(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(yaml_str(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return yaml_str(v)


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"] + [f"{k}: {yaml_value(v)}" for k, v in fields.items()] + ["---"]
    return "\n".join(lines)


@dataclass
class OutFile:
    path: str          # relative to KB root
    title: str
    section: str
    pages: list[int]
    content: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DocExport:
    slug: str
    doc: CanonicalDocument
    profile: Profile
    files: list[OutFile] = field(default_factory=list)
    assets: dict[str, Path] = field(default_factory=dict)   # kb-relative path -> source file
    source_map: dict[str, Any] = field(default_factory=dict)
    index_path: str = ""
    missing_assets: list[str] = field(default_factory=list)


class DocumentExporter:
    def __init__(self, doc: CanonicalDocument, profile: Profile, assets_src: Path, slug: str,
                 layout: str, generated_at: str):
        self.doc = doc
        self.profile = profile
        self.assets_src = assets_src
        self.slug = slug
        self.layout = layout
        self.generated_at = generated_at
        self.md = profile.markdown
        self.meta = doc.effective_metadata()
        if layout == "wiki":
            self.asset_prefix = f"assets/{slug}"
            self.asset_dir = f"assets/{slug}"
        else:
            self.asset_prefix = "assets"
            self.asset_dir = f"docs/{slug}/assets"
        self.renderer = MarkdownRenderer(doc, profile, lambda name: f"{self.asset_prefix}/{name}")

    # -- paths ---------------------------------------------------------------
    def page_path(self, name: str | None) -> str:
        if self.layout == "wiki":
            return f"{self.slug}.md" if name is None else f"{self.slug}--{name}.md"
        return f"docs/{self.slug}/index.md" if name is None else f"docs/{self.slug}/{name}.md"

    def link(self, name: str | None) -> str:
        """Link from the document index page to a section page."""
        if self.layout == "wiki":
            return self.slug if name is None else f"{self.slug}--{name}"
        return "index.md" if name is None else f"{name}.md"

    # -- build -----------------------------------------------------------------
    def build(self) -> DocExport:
        out = DocExport(slug=self.slug, doc=self.doc, profile=self.profile)
        sections = self._split()
        names: list[tuple[str, Block | None, list[Block]]] = []
        used: set[str] = set()
        for i, (head, blocks) in enumerate(sections, start=1):
            if head is None:
                continue
            label = f"{head.number} {head.text}" if head.number and not head.number[:1].isdigit() else head.text
            base = slugify(label or head.number or "section", 50)
            try:
                name = self.md.file_name_pattern.format(index=len(names) + 1, slug=base,
                                                        number=slugify(head.number or "", 20, fallback=""))
            except (KeyError, ValueError, IndexError):
                name = f"{len(names) + 1:02d}-{base}"
            name = slugify(name, 70)
            while name in used:
                name += "-x"
            used.add(name)
            names.append((name, head, blocks))
        front = sections[0][1] if sections and sections[0][0] is None else []
        min_level = min((b.level or 1 for _, h, _ in names for b in [h] if h is not None), default=1)

        for name, head, blocks in names:
            f = self._render_file(self.page_path(name), head, blocks, base_level=head.level or 1,
                                  title=heading_text(head, self.profile), section=head.number or "")
            out.files.append(f)
        index = self._render_index(names, front, min_level)
        out.files.insert(0, index)
        out.index_path = index.path
        self._collect_assets(out)
        out.source_map = self._source_map(out)
        return out

    def _split(self) -> list[tuple[Block | None, list[Block]]]:
        split = self.md.split_level
        levels = [b.level or 1 for b in self.doc.blocks if b.type == "heading"]
        if split > 0 and levels:
            split = max(split, min(levels))
        sections: list[tuple[Block | None, list[Block]]] = [(None, [])]
        for b in self.doc.blocks:
            if split > 0 and b.type == "heading" and (b.level or 1) <= split:
                sections.append((b, [b]))
            else:
                sections[-1][1].append(b)
        if not sections[0][1] and len(sections) > 1:
            sections = sections[1:]
        return sections

    def _block_pages(self, b: Block) -> list[int]:
        pages = set(b.pages or [b.page])
        if b.type == "table" and b.ref:
            t = self.doc.table(b.ref)
            if t:
                pages |= {p.page for p in t.parts}
        return sorted(pages)

    def _fm(self, title: str, section: str, pages: list[int]) -> str:
        values = {
            "title": title, "doc_id": self.doc.doc_id, "doc_number": self.meta.doc_number,
            "doc_title": self.meta.title, "revision": self.meta.revision, "publisher": self.meta.publisher,
            "date": self.meta.date, "section": section, "source_file": self.doc.source.filename,
            "source_sha256": self.doc.source.sha256, "source_pages": format_page_list(pages) if pages else "",
            "profile": self.profile.id, "generator": f"spec2kb {__version__}", "generated_at": self.generated_at,
            "tags": list(dict.fromkeys(list(self.meta.tags) + list(self.profile.parsing.metadata.tags))),
        }
        fields = {k: values.get(k, "") for k in self.md.frontmatter_fields}
        fields.update(self.md.extra_frontmatter)
        return frontmatter(fields)

    def _render_blocks(self, blocks: list[Block], base_level: int, start_line: int,
                       level_offset: int = 0) -> tuple[list[str], list[dict[str, Any]]]:
        lines: list[str] = []
        smap: list[dict[str, Any]] = []
        last_page = None
        prev_type = None
        for b in blocks:
            level = None
            if b.type == "heading":
                level = (b.level or 1) - base_level + 1 + level_offset
            frag = self.renderer.render_block(b, level)
            if not frag:
                if b.type == "figure" and b.ref:
                    f = self.doc.figure(b.ref)
                    if f and f.description and f.description.status == "failed":
                        lines += [f"<!-- AI description failed for {b.ref} -->", ""]
                continue
            comment = None
            if self.md.source_refs == "comment":
                if b.type in ("table", "figure"):
                    comment = f"<!-- source: p.{format_page_list(self._block_pages(b))} {b.ref} -->"
                elif b.page != last_page:
                    comment = f"<!-- source: p.{b.page} -->"
            tight = prev_type == "list_item" and b.type == "list_item" and comment is None
            if lines and not tight:
                lines.append("")
            if comment:
                lines += [comment, ""]
            start = start_line + len(lines)
            frag_lines = frag.split("\n")
            lines += frag_lines
            smap.append({"id": b.id, "type": b.type, "page": b.page, "pages": self._block_pages(b),
                         "bbox": b.bbox, "ref": b.ref, "line_start": start + 1,
                         "line_end": start + len(frag_lines),
                         "edited": bool(b.md_override is not None or self._ref_edited(b)),
                         "origin": b.origin})
            last_page = b.page
            prev_type = b.type
        return lines, smap

    def _ref_edited(self, b: Block) -> bool:
        if b.type == "table" and b.ref:
            t = self.doc.table(b.ref)
            return bool(t and t.md_override is not None)
        if b.type == "figure" and b.ref:
            f = self.doc.figure(b.ref)
            return bool(f and (f.md_override is not None or f.description_override is not None))
        return False

    def _render_file(self, path: str, head: Block, blocks: list[Block], base_level: int, title: str,
                     section: str) -> OutFile:
        pages = sorted({p for b in blocks for p in self._block_pages(b)})
        head_lines = []
        if self.md.frontmatter:
            head_lines = self._fm(title, section, pages).split("\n") + [""]
        body, smap = self._render_blocks(blocks, base_level, len(head_lines))
        content = "\n".join(head_lines + body).rstrip() + "\n"
        return OutFile(path=path, title=title, section=section, pages=pages, content=content, blocks=smap)

    def _render_index(self, names: list[tuple[str, Block | None, list[Block]]], front: list[Block],
                      min_level: int) -> OutFile:
        L = self.md.labels
        title = self.meta.title or self.doc.source.filename
        all_pages = [p.number for p in self.doc.pages if p.status != "skipped"]
        lines: list[str] = []
        if self.md.frontmatter:
            lines += self._fm(title, "", all_pages).split("\n") + [""]
        lines += [f"# {_esc(title)}", "", f"## {L.document_info}", "", "| | |", "|---|---|"]
        info = [("Document number", self.meta.doc_number), ("Revision", self.meta.revision),
                ("Publisher", self.meta.publisher), ("Date", self.meta.date),
                ("Source file", f"{self.doc.source.filename} ({self.doc.source.page_count} pages)"),
                ("SHA-256", self.doc.source.sha256[:16] + "…"), ("Profile", self.profile.id),
                ("Generated", f"{self.generated_at} · spec2kb {__version__}")]
        lines += [f"| {k} | {_cell(v)} |" for k, v in info if v]
        if names:
            lines += ["", f"## {L.contents}", ""]
        file_of_block: dict[str, str] = {}
        for name, head, blocks in names:
            for b in blocks:
                file_of_block[b.id] = name
            if head is None:
                continue
            indent = "  " * max(0, (head.level or 1) - min_level)
            lines.append(f"{indent}- [{_esc(heading_text(head, self.profile))}]({self.link(name)})")
            for b in blocks[1:]:
                if b.type == "heading" and (b.level or 1) == (head.level or 1) + 1:
                    lines.append(f"{indent}  - {_esc(heading_text(b, self.profile))}")
        figs = [b for b in self.doc.blocks if b.type == "figure" and b.ref]
        fig_lines = []
        for b in figs:
            f = self.doc.figure(b.ref)
            if f is None or f.kind == "page":
                continue
            cap = figure_caption(f) or f.id
            target = file_of_block.get(b.id)
            entry = f"[{_esc(cap)}]({self.link(target)})" if target else _esc(cap)
            fig_lines.append(f"- {entry} — p. {f.page}")
        if fig_lines:
            lines += ["", f"## {L.figures}", ""] + fig_lines
        tbl_lines = []
        for b in self.doc.blocks:
            if b.type != "table" or not b.ref:
                continue
            t = self.doc.table(b.ref)
            if t is None:
                continue
            cap = table_caption(t) or t.id
            target = file_of_block.get(b.id)
            entry = f"[{_esc(cap)}]({self.link(target)})" if target else _esc(cap)
            tbl_lines.append(f"- {entry} — p. {format_page_list(self._block_pages(b))}")
        if tbl_lines:
            lines += ["", f"## {L.tables}", ""] + tbl_lines
        smap: list[dict[str, Any]] = []
        if front:
            lines += ["", f"## {L.front_matter}", ""]
            body, smap = self._render_blocks(front, base_level=1, start_line=len(lines), level_offset=2)
            lines += body
        content = "\n".join(lines).rstrip() + "\n"
        return OutFile(path=self.page_path(None), title=title, section="", pages=all_pages,
                       content=content, blocks=smap)

    def _collect_assets(self, out: DocExport) -> None:
        for f in self.doc.figures:
            if f.asset:
                src = self.assets_src / f.asset
                dst = f"{self.asset_dir}/{self.renderer.figure_asset_name(f)}"
                if src.exists():
                    out.assets[dst] = src
                else:
                    out.missing_assets.append(f.asset)
        for t in self.doc.tables:
            for i, part in enumerate(t.parts):
                if part.snapshot:
                    src = self.assets_src / part.snapshot
                    if src.exists():
                        out.assets[f"{self.asset_dir}/{self.renderer.table_asset_name(t, i)}"] = src

    def _source_map(self, out: DocExport) -> dict[str, Any]:
        figs = {}
        file_of = {e["id"]: f.path for f in out.files for e in f.blocks}
        for b in self.doc.blocks:
            if b.type == "figure" and b.ref:
                f = self.doc.figure(b.ref)
                if f is None:
                    continue
                d = f.description
                figs[f.id] = {"number": f.number, "caption": figure_caption(f), "page": f.page, "bbox": f.bbox,
                              "kind": f.kind, "image_type": f.image_type, "file": file_of.get(b.id),
                              "asset": f"{self.asset_dir}/{self.renderer.figure_asset_name(f)}" if f.asset else None,
                              "asset_sha256": f.asset_sha256, "embedded_text": f.embedded_text,
                              "description": None if d is None else {
                                  "status": d.status, "provider": d.provider, "model": d.model,
                                  "prompt_hash": d.prompt_hash, "created_at": d.created_at,
                                  "warnings": d.warnings},
                              "description_reviewed": f.description_override is not None}
        tables = {}
        for b in self.doc.blocks:
            if b.type == "table" and b.ref:
                t = self.doc.table(b.ref)
                if t is None:
                    continue
                tables[t.id] = {"number": t.number, "caption": table_caption(t), "file": file_of.get(b.id),
                                "parts": [p.model_dump() for p in t.parts], "rows": t.n_rows, "cols": t.n_cols,
                                "header_rows": t.header_rows, "method": t.method, "confidence": t.confidence}
        return {"schema_version": self.doc.schema_version, "doc_id": self.doc.doc_id, "slug": self.slug,
                "source": self.doc.source.model_dump(), "profile": self.profile.id,
                "generated_at": self.generated_at,
                "files": [{"path": f.path, "title": f.title, "section": f.section,
                           "pages": f.pages, "blocks": f.blocks} for f in out.files],
                "figures": figs, "tables": tables}


def _esc(text: str) -> str:
    from .markdown import escape_inline
    return escape_inline(text)


def _cell(text: str) -> str:
    from .markdown import escape_cell
    return escape_cell(text)


def doc_slug(doc: CanonicalDocument, used: set[str]) -> str:
    meta = doc.effective_metadata()
    base = slugify(meta.doc_number or meta.title or doc.source.filename, 40, fallback="document")
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


@dataclass
class KbItem:
    doc: CanonicalDocument
    profile: Profile
    assets_dir: Path
    validation: dict[str, Any] | None = None
    validation_md: str = ""


def build_kb(items: list[KbItem], out_root: Path, kb_name: str, layout: str | None = None,
             providers_public: list[dict] | None = None) -> list[DocExport]:
    """Write a complete knowledge base tree to out_root (created / replaced)."""
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    layout = layout or (items[0].profile.markdown.layout if items else "mkdocs")
    generated_at = utcnow()
    used: set[str] = set()
    exports: list[DocExport] = []
    for it in items:
        slug = doc_slug(it.doc, used)
        exp = DocumentExporter(it.doc, it.profile, it.assets_dir, slug, layout, generated_at).build()
        exports.append(exp)
        for f in exp.files:
            p = out_root / f.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f.content, encoding="utf-8")
        for rel, src in exp.assets.items():
            dst = out_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        meta_dir = out_root / "_meta" / slug
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "canonical.json").write_text(it.doc.model_dump_json(indent=2), encoding="utf-8")
        (meta_dir / "source_map.json").write_text(json.dumps(exp.source_map, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        (meta_dir / "profile.json").write_text(it.profile.model_dump_json(indent=2), encoding="utf-8")
        if it.validation is not None:
            (meta_dir / "validation_report.json").write_text(json.dumps(it.validation, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
        if it.validation_md:
            (meta_dir / "validation_report.md").write_text(it.validation_md, encoding="utf-8")
    _write_home(out_root, exports, kb_name, layout, generated_at)
    if layout == "mkdocs":
        _write_mkdocs_yml(out_root, exports, kb_name)
    else:
        _write_sidebar(out_root, exports)
    manifest = {"kb_name": kb_name, "layout": layout, "generator": f"spec2kb {__version__}",
                "generated_at": generated_at,
                "documents": [{"slug": e.slug, "doc_id": e.doc.doc_id, "title": e.doc.effective_metadata().title,
                               "doc_number": e.doc.effective_metadata().doc_number,
                               "source_file": e.doc.source.filename, "source_sha256": e.doc.source.sha256,
                               "profile": e.profile.id, "index": e.index_path,
                               "files": [f.path for f in e.files]} for e in exports]}
    (out_root / "_meta").mkdir(exist_ok=True)
    (out_root / "_meta" / "kb.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if providers_public is not None:
        (out_root / "_meta" / "providers.json").write_text(
            json.dumps(providers_public, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "README.md").write_text(_readme(kb_name, layout, exports), encoding="utf-8")
    return exports


def _write_home(root: Path, exports: list[DocExport], kb_name: str, layout: str, generated_at: str) -> None:
    lines = ["---", f"title: {yaml_str(kb_name)}", f"generated_at: {yaml_str(generated_at)}", "---", "",
             f"# {_esc(kb_name)}", "", "| Document | Number | Revision | Source | Profile |", "|---|---|---|---|---|"]
    for e in exports:
        m = e.doc.effective_metadata()
        link = f"{e.slug}/index.md" if layout == "mkdocs" else e.slug
        lines.append(f"| [{_esc(m.title or e.slug)}]({link}) | {_cell(m.doc_number)} | {_cell(m.revision)} | "
                     f"{_cell(e.doc.source.filename)} | {_cell(e.profile.id)} |")
    path = root / ("docs/index.md" if layout == "mkdocs" else "Home.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mkdocs_yml(root: Path, exports: list[DocExport], kb_name: str) -> None:
    lines = [f"site_name: {yaml_str(kb_name)}", "docs_dir: docs", "use_directory_urls: false",
             "markdown_extensions:", "  - tables", "  - toc:", "      permalink: true", "  - admonition",
             "  - md_in_html", "  - attr_list", "nav:", "  - Home: index.md"]
    for e in exports:
        title = e.doc.effective_metadata().title or e.slug
        lines.append(f"  - {yaml_str(title)}:")
        for f in e.files:
            rel = f.path[len("docs/"):]
            label = "Overview" if rel.endswith("/index.md") else f.title
            lines.append(f"      - {yaml_str(label)}: {yaml_str(rel)}")
    (root / "mkdocs.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sidebar(root: Path, exports: list[DocExport]) -> None:
    lines = ["- [Home](Home)"]
    for e in exports:
        lines.append(f"- [{_esc(e.doc.effective_metadata().title or e.slug)}]({e.slug})")
    (root / "_Sidebar.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _readme(kb_name: str, layout: str, exports: list[DocExport]) -> str:
    view = ("mkdocs serve  # http://127.0.0.1:8000  (or: mkdocs build)" if layout == "mkdocs" else
            "push this folder to the wiki repository (GitLab/GitHub/Gitea wiki): git clone <repo>.wiki.git")
    docs = "\n".join(f"- `{e.slug}` — {e.doc.effective_metadata().title} ({e.doc.source.filename})" for e in exports)
    return (f"# {kb_name}\n\nGenerated by spec2kb {__version__} (layout: `{layout}`).\n\n"
            f"## View\n\n```\n{view}\n```\n\n## Documents\n\n{docs}\n\n"
            "## Structure\n\n"
            "- Markdown pages use relative links only; images live in `assets/` next to the pages.\n"
            "- `_meta/<doc>/canonical.json` — canonical intermediate data (all extracted structure).\n"
            "- `_meta/<doc>/source_map.json` — page / bounding box / line mapping for every Markdown block.\n"
            "- `_meta/<doc>/validation_report.md|json` — fidelity checks (values, units, signals, tables).\n"
            "- `_meta/<doc>/profile.json` — resolved settings used for the conversion.\n"
            "- AI figure descriptions are marked as auto-generated; verify them against the images.\n")


def zip_tree(root: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                arc = Path(root.name) / p.relative_to(root)
                zf.write(p, arc.as_posix())
    return zip_path
