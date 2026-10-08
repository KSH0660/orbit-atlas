"""PDF access: pdfplumber for layout objects, pypdfium2 for fast rendering and band text.

pdfium is not thread-safe, so every pdfium call is serialized with a process
wide lock. pdfplumber objects are per-thread (each job opens its own file).
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

PDFIUM_LOCK = threading.RLock()


class PdfOpenError(RuntimeError):
    pass


def validate_pdf_bytes(head: bytes) -> bool:
    return head[:1024].lstrip().startswith(b"%PDF-") or b"%PDF-" in head[:1024]


class PdfDoc:
    """Wraps one PDF opened with both libraries."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.plumber = pdfplumber.open(str(self.path))
        except Exception as exc:  # pdfminer raises a variety of exceptions
            raise PdfOpenError(f"PDF를 열 수 없습니다 ({type(exc).__name__}: {exc})") from exc
        try:
            with PDFIUM_LOCK:
                self.pdfium = pdfium.PdfDocument(str(self.path))
        except Exception as exc:
            self.plumber.close()
            raise PdfOpenError(f"PDF 렌더러가 파일을 열 수 없습니다: {exc}") from exc
        self.page_count = len(self.plumber.pages)

    def close(self) -> None:
        try:
            self.plumber.close()
        finally:
            with PDFIUM_LOCK:
                self.pdfium.close()

    def __enter__(self) -> "PdfDoc":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- metadata ---------------------------------------------------------------
    def metadata(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in (self.plumber.metadata or {}).items():
            if isinstance(v, bytes):
                try:
                    v = v.decode("utf-8", "ignore")
                except Exception:  # pragma: no cover
                    continue
            if isinstance(v, (str, int, float)):
                out[str(k)] = str(v)[:500]
        return out

    # -- plumber pages ----------------------------------------------------------
    @contextmanager
    def page(self, number: int) -> Iterator["pdfplumber.page.Page"]:
        """Yield a pdfplumber page (1-based); caches are released afterwards."""
        page = self.plumber.pages[number - 1]
        try:
            cb = page.cropbox
            if tuple(round(v, 1) for v in cb) != tuple(round(v, 1) for v in page.bbox):
                yield page.crop(cb, relative=False, strict=False)
            else:
                yield page
        finally:
            page.close()

    def page_size(self, number: int) -> tuple[float, float]:
        page = self.plumber.pages[number - 1]
        return float(page.width), float(page.height)

    # -- pdfium -----------------------------------------------------------------
    def band_text(self, number: int, top_ratio: float, bottom_ratio: float) -> tuple[list[str], list[str], int]:
        """Fast text of the header/footer bands plus total char count (pdfium)."""
        with PDFIUM_LOCK:
            page = self.pdfium[number - 1]
            try:
                w, h = page.get_size()
                tp = page.get_textpage()
                try:
                    count = tp.count_chars()
                    top = tp.get_text_bounded(0, h * (1 - top_ratio), w, h) if top_ratio > 0 else ""
                    bottom = tp.get_text_bounded(0, 0, w, h * bottom_ratio) if bottom_ratio > 0 else ""
                finally:
                    tp.close()
            finally:
                page.close()
        split = lambda s: [ln.strip() for ln in s.replace("\r", "\n").split("\n") if ln.strip()]
        return split(top), split(bottom), count

    def render(self, number: int, bbox: list[float] | None = None, dpi: float = 150,
               max_px: int | None = None, cropbox: list[float] | None = None) -> Image.Image:
        """Render a page or a region (pdfplumber coordinates: x0, top, x1, bottom)."""
        scale = dpi / 72.0
        with PDFIUM_LOCK:
            page = self.pdfium[number - 1]
            try:
                pw, ph = page.get_size()
                if bbox is None:
                    if max_px:
                        scale = min(scale, max_px / max(pw, ph))
                    bitmap = page.render(scale=scale)
                else:
                    ox, oy = (cropbox[0], cropbox[1]) if cropbox else (0.0, 0.0)
                    x0 = max(0.0, min(pw, bbox[0] - ox))
                    x1 = max(0.0, min(pw, bbox[2] - ox))
                    top = max(0.0, min(ph, bbox[1] - oy))
                    bottom = max(0.0, min(ph, bbox[3] - oy))
                    if x1 - x0 < 1 or bottom - top < 1:
                        raise ValueError("empty render region")
                    if max_px:
                        scale = min(scale, max_px / max(x1 - x0, bottom - top))
                    bitmap = page.render(scale=scale, crop=(x0, ph - bottom, pw - x1, top))
                img = bitmap.to_pil()
                bitmap.close()
            finally:
                page.close()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return img
