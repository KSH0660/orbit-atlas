"""Fidelity tokens: numeric values with units, bare numbers, signal names, protected identifiers."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

_TRANS = str.maketrans({"μ": "µ", "Ω": "Ω", "−": "-", "–": "-", "℃": "°C", " ": " ", " ": " ",
                        " ": " "})


def normalize_text(text: str) -> str:
    t = text.translate(_TRANS)
    return re.sub(r"\s+", " ", t).strip()


def _unit_key(unit: str) -> str:
    u = unit.replace("µ", "u")
    if u.lower() in ("ohm", "ohms"):
        return "Ω"
    return u


@lru_cache(maxsize=32)
def _value_re(units: tuple[str, ...]) -> re.Pattern:
    alts = sorted({re.escape(u.translate(_TRANS)) for u in units if u}, key=len, reverse=True)
    if not alts:
        alts = [r"(?!x)x"]
    return re.compile(r"(?<![\w.])([-+±]?\d+(?:\.\d+)?)\s?(" + "|".join(alts) + r")(?![A-Za-z0-9_])")


NUM_PLAIN_RE = re.compile(r"(?<![\w.])([-+±]?\d+(?:\.\d+)?)(?![\d.]*\d)")


@dataclass
class TokenSet:
    values: Counter = field(default_factory=Counter)
    numbers: Counter = field(default_factory=Counter)
    signals: Counter = field(default_factory=Counter)
    extras: Counter = field(default_factory=Counter)

    def all_keys(self) -> set[str]:
        return set(self.values) | set(self.numbers) | set(self.signals) | set(self.extras)


@lru_cache(maxsize=64)
def _compiled(patterns: tuple[str, ...]) -> tuple[re.Pattern, ...]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p))
        except re.error:
            continue
    return tuple(out)


def extract_tokens(text: str, units: Iterable[str], signal_patterns: Iterable[str],
                   extra_patterns: Iterable[str] = ()) -> TokenSet:
    t = normalize_text(text)
    ts = TokenSet()
    for m in _value_re(tuple(units)).finditer(t):
        num = m.group(1).lstrip("+")
        ts.values[f"{num} {_unit_key(m.group(2))}"] += 1
    for m in NUM_PLAIN_RE.finditer(t):
        ts.numbers[m.group(1).lstrip("+")] += 1
    for rx in _compiled(tuple(signal_patterns)):
        for m in rx.finditer(t):
            ts.signals[m.group(0)] += 1
    for rx in _compiled(tuple(extra_patterns)):
        for m in rx.finditer(t):
            ts.extras[m.group(0)] += 1
    return ts


def value_display(key: str) -> str:
    num, _, unit = key.partition(" ")
    return f"{num} {unit.replace('u', 'µ', 1) if unit[:1] == 'u' and len(unit) > 1 else unit}"


def similar_values(missing: str, candidates: Iterable[str]) -> list[str]:
    """Values that look like a distortion of ``missing`` (same unit & close digits, or same number other unit)."""
    num, _, unit = missing.partition(" ")
    out = []
    for c in candidates:
        cn, _, cu = c.partition(" ")
        if c == missing:
            continue
        if cu == unit and digits_close(num, cn):
            out.append(c)
        elif cn == num and cu != unit:
            out.append(c)
    return out[:3]


def digits_close(a: str, b: str) -> bool:
    """True when b looks like a distortion of a: rounding/truncation, moved decimal point,
    lost sign, single-digit typo or reformatting (1.10 vs 1.1)."""
    if a == b:
        return False
    try:
        x, y = float(a.replace("±", "")), float(b.replace("±", ""))
    except ValueError:
        return False
    if x == y:
        return True
    if x == -y:
        return True
    if x and y:
        if abs(x - y) / max(abs(x), abs(y)) <= 0.01:
            return True
        for f in (10.0, 100.0, 1000.0):
            if abs(x * f - y) <= 1e-9 * abs(y) or abs(y * f - x) <= 1e-9 * abs(x):
                return True
    da, db = re.sub(r"\D", "", a), re.sub(r"\D", "", b)
    return len(da) == len(db) and sum(1 for p, q in zip(da, db) if p != q) == 1


# ---------------------------------------------------------------------------
# markdown -> plain text (for comparing generated output with the source)
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG_RE = re.compile(r"<[^>]+>")
_ESC_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~])")


def markdown_to_plain(md: str) -> str:
    md = _COMMENT_RE.sub(" ", md)
    md = _IMG_RE.sub(" ", md)
    md = _LINK_RE.sub(r"\1", md)
    md = re.sub(r"(?i)<br\s*/?>", " ", md)
    md = re.sub(r"(?i)</t[dh]>", " ", md)
    md = re.sub(r"(?i)</tr>", "\n", md)
    md = _TAG_RE.sub(" ", md)
    lines = []
    for ln in md.splitlines():
        s = ln.strip()
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?", s):
            continue
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", s[1:-1])]
            s = " ".join(cells)
        s = re.sub(r"^#{1,6}\s+", "", s)
        s = re.sub(r"^(>\s?)+", "", s)
        s = re.sub(r"^[-*+]\s+", "", s)
        s = re.sub(r"^!!!\s+\w+(\s+\"[^\"]*\")?", "", s)
        lines.append(s)
    text = "\n".join(lines)
    # protect escaped characters before stripping emphasis markers, then restore them
    text = _ESC_RE.sub(lambda m: f"\ue000{ord(m.group(1))}\ue001", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)", "", text)
    text = re.sub("\ue000(\\d+)\ue001", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"[ \t]+", " ", text)
    return html.unescape(text)
