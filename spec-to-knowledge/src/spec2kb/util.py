"""Small shared helpers (file IO, slugs, page ranges, hashing)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(text: str, max_len: int = 60, fallback: str = "section") -> str:
    norm = unicodedata.normalize("NFKD", text)
    norm = norm.encode("ascii", "ignore").decode("ascii").lower()
    norm = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
    if len(norm) > max_len:
        norm = norm[:max_len].rstrip("-")
    return norm or fallback


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """'1-3, 7, 10-' -> [1, 2, 3, 7, 10, ..., page_count]. Empty spec = all pages."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(1, page_count + 1))
    pages: set[int] = set()
    for part in re.split(r"[,\s]+", spec):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)", part)
        if m:
            start = int(m.group(1)) if m.group(1) else 1
            end = int(m.group(2)) if m.group(2) else page_count
        elif part.isdigit():
            start = end = int(part)
        else:
            raise ValueError(f"페이지 범위 형식이 올바르지 않습니다: '{part}' (예: 1-5, 8, 10-)")
        if start > end:
            start, end = end, start
        for p in range(max(1, start), min(page_count, end) + 1):
            pages.add(p)
    if not pages:
        raise ValueError(f"페이지 범위 '{spec}'에 해당하는 페이지가 없습니다 (총 {page_count}쪽).")
    return sorted(pages)


def format_page_list(pages: list[int]) -> str:
    """[1,2,3,5] -> '1-3, 5'."""
    pages = sorted(set(pages))
    out: list[str] = []
    i = 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        out.append(str(pages[i]) if i == j else f"{pages[i]}-{pages[j]}")
        i = j + 1
    return ", ".join(out)


def safe_join(base: Path, rel: str) -> Path:
    """Join a user-supplied relative path below base, refusing traversal."""
    rel = rel.replace("\\", "/").lstrip("/")
    target = (base / rel).resolve()
    base_r = base.resolve()
    if target != base_r and base_r not in target.parents:
        raise ValueError("invalid path")
    return target


def short_hash(*parts: Any, length: int = 10) -> str:
    h = hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return h[:length]
