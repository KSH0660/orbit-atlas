"""Canonical document schema.

The canonical JSON is the single intermediate representation between the PDF
parser and every consumer (validator, Markdown exporter, web UI). It keeps:

* the reading-order block stream (headings, paragraphs, lists, notes, and
  references to tables / figures),
* fully structured tables (cells with row/col spans),
* figures with their rendered image asset, the text found inside the figure
  region, and the AI (vision) description with provenance,
* source provenance for everything (page number + bounding box + method),
* user edits as *overrides* next to the original extraction, so edits survive
  re-exports and can be validated against the source.

Coordinates are PDF points with a top-left origin: ``[x0, top, x1, bottom]``.
Page numbers are 1-based.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import SCHEMA_VERSION

BBox = list[float]

BlockType = Literal["heading", "paragraph", "list_item", "note", "table", "figure"]
Origin = Literal["text_layer", "ocr", "vision", "user"]
Severity = Literal["error", "warning", "info"]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Block(BaseModel):
    id: str
    type: BlockType
    page: int
    bbox: BBox | None = None
    text: str = ""
    level: int | None = Field(None, description="heading level (1 = top)")
    number: str | None = Field(None, description="heading number such as '4.1.2' or 'A.1'")
    label: str | None = Field(None, description="list marker such as '•', 'a)' or note label")
    ref: str | None = Field(None, description="table/figure id for table and figure blocks")
    font_size: float | None = None
    bold: bool = False
    origin: Origin = "text_layer"
    confidence: float = 1.0
    continued: bool = Field(False, description="paragraph continues a block from the previous page")
    pages: list[int] = Field(default_factory=list, description="all pages the block spans when merged across pages")
    hints: dict[str, Any] = Field(default_factory=dict, description="parser hints (heading candidate info) used by document-level passes")
    md_override: str | None = Field(None, description="user-edited Markdown that replaces the generated output")
    edited_at: str | None = None


class Cell(BaseModel):
    row: int
    col: int
    text: str = ""
    rowspan: int = 1
    colspan: int = 1
    header: bool = False
    bbox: BBox | None = None


class TablePart(BaseModel):
    page: int
    bbox: BBox
    rows: int
    snapshot: str | None = None


class Table(BaseModel):
    id: str
    number: str | None = None
    caption: str = ""
    title: str = ""
    page: int
    bbox: BBox
    parts: list[TablePart] = Field(default_factory=list, description="one entry per page for continued tables")
    n_rows: int
    n_cols: int
    header_rows: int = 1
    cells: list[Cell] = Field(default_factory=list)
    method: Literal["lines", "text", "vision", "user"] = "lines"
    confidence: float = 1.0
    snapshot: str | None = Field(None, description="relative asset path of the rendered table image")
    md_override: str | None = None
    edited_at: str | None = None

    def grid(self) -> list[list[Cell | None]]:
        """Dense grid where spanned positions point to None (covered) and anchors to the cell."""
        g: list[list[Cell | None]] = [[None] * self.n_cols for _ in range(self.n_rows)]
        for c in self.cells:
            if 0 <= c.row < self.n_rows and 0 <= c.col < self.n_cols:
                g[c.row][c.col] = c
        return g

    def has_spans(self) -> bool:
        return any(c.rowspan > 1 or c.colspan > 1 for c in self.cells)


class DescriptionSection(BaseModel):
    key: str
    title: str
    items: list[str] = Field(default_factory=list)


class VisionResult(BaseModel):
    status: Literal["ok", "uncertain", "failed", "skipped", "pending"] = "pending"
    image_type: str = "generic"
    summary: str = ""
    sections: list[DescriptionSection] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list, description="items the model marked as unclear")
    raw: str = ""
    structured: bool = True
    provider: str = ""
    model: str = ""
    prompt_hash: str = ""
    created_at: str = ""
    duration_ms: int = 0
    cached: bool = False
    error: str = ""
    warnings: list[str] = Field(default_factory=list)


class Figure(BaseModel):
    id: str
    number: str | None = None
    caption: str = ""
    title: str = ""
    page: int
    bbox: BBox
    kind: Literal["raster", "vector", "mixed", "inferred", "page"] = "vector"
    image_type: str = "generic"
    image_type_source: Literal["rule", "llm", "user", "default"] = "default"
    asset: str = Field("", description="relative path of the PNG inside the document asset folder")
    asset_sha256: str = ""
    width_px: int = 0
    height_px: int = 0
    embedded_text: list[str] = Field(default_factory=list, description="text-layer lines inside the figure region")
    description: VisionResult | None = None
    description_override: str | None = Field(None, description="user-written Markdown replacing the AI description")
    prompt_extra: str = Field("", description="reviewer instructions appended to the vision prompt for this figure")
    md_override: str | None = None
    edited_at: str | None = None


class Issue(BaseModel):
    id: str
    severity: Severity
    code: str
    message: str
    page: int | None = None
    ref: str | None = Field(None, description="block / table / figure id")
    file: str | None = None
    source: Literal["parser", "vision", "validator", "export"] = "validator"
    details: dict[str, Any] = Field(default_factory=dict)
    status: Literal["open", "ignored", "resolved"] = "open"


class PageInfo(BaseModel):
    number: int
    width: float
    height: float
    kind: Literal["text", "scanned", "toc", "blank", "cover"] = "text"
    status: Literal["ok", "warning", "error", "skipped", "pending"] = "pending"
    char_count: int = 0
    removed_lines: list[str] = Field(default_factory=list, description="header/footer lines removed from this page")
    source_text: str = Field("", description="raw text-layer content (after header/footer removal) used for validation")
    processed_at: str = ""
    messages: list[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    filename: str
    sha256: str
    size_bytes: int
    page_count: int
    pdf_metadata: dict[str, str] = Field(default_factory=dict)


class DocMetadata(BaseModel):
    title: str = ""
    doc_number: str = ""
    revision: str = ""
    date: str = ""
    publisher: str = ""
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)


class ProcessingInfo(BaseModel):
    generator: str = ""
    profile_id: str = ""
    profile_hash: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    pages_processed: list[int] = Field(default_factory=list)
    vision_provider: str = ""
    vision_model: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)


class CanonicalDocument(BaseModel):
    schema_version: str = SCHEMA_VERSION
    doc_id: str
    slug: str
    source: SourceInfo
    metadata: DocMetadata = Field(default_factory=DocMetadata)
    metadata_override: dict[str, Any] = Field(default_factory=dict, description="user edits of metadata fields")
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    processing: ProcessingInfo = Field(default_factory=ProcessingInfo)

    # -- helpers ------------------------------------------------------------
    def effective_metadata(self) -> DocMetadata:
        data = self.metadata.model_dump()
        for k, v in self.metadata_override.items():
            if k in data and v not in (None, ""):
                data[k] = v
        return DocMetadata(**data)

    def table(self, table_id: str) -> Table | None:
        return next((t for t in self.tables if t.id == table_id), None)

    def figure(self, figure_id: str) -> Figure | None:
        return next((f for f in self.figures if f.id == figure_id), None)

    def block(self, block_id: str) -> Block | None:
        return next((b for b in self.blocks if b.id == block_id), None)

    def page(self, number: int) -> PageInfo | None:
        return next((p for p in self.pages if p.number == number), None)

    def outline(self) -> list[dict[str, Any]]:
        return [
            {"id": b.id, "number": b.number, "title": b.text, "level": b.level, "page": b.page}
            for b in self.blocks
            if b.type == "heading"
        ]
