"""Document workspace on disk.

<data>/docs/<doc_id>/
    record.json        upload metadata, status, chosen profile, per-document option overrides
    source.pdf         original upload (never modified)
    raw/pNNNN.json     per-page parser output (re-parsing one page replaces one file)
    canonical.json     assembled canonical document (+ edits, AI descriptions, issues)
    overlay.json       user edits keyed by block / table / figure id, issue statuses, metadata edits
    assets/            rendered figures, table snapshots, scanned page images
    previews/          cached page renders for the UI
    preview_kb/        last Markdown preview tree
    jobs/              job history
"""

from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .parser.pipeline import RawPage
from .schema import CanonicalDocument, utcnow
from .util import atomic_write_json, atomic_write_text, read_json

DocStatus = Literal["uploaded", "queued", "processing", "ready", "failed", "cancelled"]


class DocRecord(BaseModel):
    id: str
    filename: str
    title: str = ""
    profile_id: str = "jedec"
    options: dict[str, Any] = Field(default_factory=dict)
    status: DocStatus = "uploaded"
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    processed_at: str = ""
    sha256: str = ""
    size_bytes: int = 0
    page_count: int = 0
    last_job_id: str = ""
    error: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    duplicate_of: str = ""


class DocumentStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def lock(self, doc_id: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(doc_id, threading.RLock())

    def new_id(self) -> str:
        return "d" + uuid.uuid4().hex[:11]

    def dir(self, doc_id: str) -> Path:
        if not doc_id.isalnum():
            raise KeyError(doc_id)
        return self.root / doc_id

    def exists(self, doc_id: str) -> bool:
        try:
            return (self.dir(doc_id) / "record.json").exists()
        except KeyError:
            return False

    # -- record -------------------------------------------------------------------
    def record(self, doc_id: str) -> DocRecord:
        data = read_json(self.dir(doc_id) / "record.json")
        if not data:
            raise KeyError(doc_id)
        return DocRecord(**data)

    def save_record(self, rec: DocRecord) -> None:
        rec.updated_at = utcnow()
        atomic_write_json(self.dir(rec.id) / "record.json", rec.model_dump())

    def list(self) -> list[DocRecord]:
        out = []
        for p in self.root.glob("*/record.json"):
            data = read_json(p)
            if data:
                try:
                    out.append(DocRecord(**data))
                except Exception:
                    continue
        return sorted(out, key=lambda r: r.created_at, reverse=True)

    def delete(self, doc_id: str) -> None:
        shutil.rmtree(self.dir(doc_id), ignore_errors=True)

    # -- files ------------------------------------------------------------------------
    def source_path(self, doc_id: str) -> Path:
        return self.dir(doc_id) / "source.pdf"

    def assets_dir(self, doc_id: str) -> Path:
        return self.dir(doc_id) / "assets"

    def previews_dir(self, doc_id: str) -> Path:
        return self.dir(doc_id) / "previews"

    def preview_kb_dir(self, doc_id: str) -> Path:
        return self.dir(doc_id) / "preview_kb"

    # -- raw pages -----------------------------------------------------------------------
    def raw_dir(self, doc_id: str) -> Path:
        return self.dir(doc_id) / "raw"

    def save_raw(self, doc_id: str, pages: dict[int, RawPage]) -> None:
        for n, rp in pages.items():
            atomic_write_text(self.raw_dir(doc_id) / f"p{n:04d}.json", rp.model_dump_json())

    def load_raw(self, doc_id: str) -> dict[int, RawPage]:
        out: dict[int, RawPage] = {}
        for p in sorted(self.raw_dir(doc_id).glob("p*.json")):
            try:
                out[int(p.stem[1:])] = RawPage.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                continue
        return out

    def clear_raw(self, doc_id: str) -> None:
        shutil.rmtree(self.raw_dir(doc_id), ignore_errors=True)

    # -- canonical / overlay -------------------------------------------------------------
    def canonical(self, doc_id: str) -> CanonicalDocument | None:
        p = self.dir(doc_id) / "canonical.json"
        if not p.exists():
            return None
        return CanonicalDocument.model_validate_json(p.read_text(encoding="utf-8"))

    def save_canonical(self, doc_id: str, doc: CanonicalDocument) -> None:
        atomic_write_text(self.dir(doc_id) / "canonical.json", doc.model_dump_json(indent=1))

    def overlay(self, doc_id: str) -> dict[str, Any]:
        data = read_json(self.dir(doc_id) / "overlay.json") or {}
        for k in ("blocks", "tables", "figures", "metadata", "issues"):
            data.setdefault(k, {})
        return data

    def save_overlay(self, doc_id: str, overlay: dict[str, Any]) -> None:
        atomic_write_json(self.dir(doc_id) / "overlay.json", overlay)
