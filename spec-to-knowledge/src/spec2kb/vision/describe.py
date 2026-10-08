"""Figure classification, prompt construction, model call and structured-output parsing."""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image

from ..profiles.model import ImageTypeRule, Profile
from ..providers.base import Provider, ProviderError
from ..schema import DescriptionSection, Figure, VisionResult, utcnow
from ..util import atomic_write_json, read_json
from ..validator.tokens import extract_tokens, normalize_text


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def classify_by_rules(fig: Figure, profile: Profile) -> tuple[str, str]:
    """Return (image_type, source) using caption / embedded-text rules."""
    caption = f"{fig.caption} {fig.title}".strip()
    text = "\n".join(fig.embedded_text)
    best: tuple[int, int, str] | None = None
    for rule in profile.vision.image_types:
        if not rule.enabled or rule.id == "generic":
            continue
        cap_hit = bool(rule.caption_regex and caption and _search(rule.caption_regex, caption))
        hits = len(_findall(rule.text_regex, text)) if rule.text_regex and text else 0
        text_hit = bool(rule.text_regex) and hits >= max(1, rule.min_text_hits)
        if not (cap_hit or text_hit):
            continue
        # a caption match beats any text-only match; priority decides within each group
        score = (1 if cap_hit else 0, rule.priority, 1 if text_hit else 0, rule.id)
        if best is None or score[:3] > best[:3]:
            best = score
    if best is None:
        return "generic", "default"
    return best[3], "rule"


def _search(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False


def _findall(pattern: str, text: str) -> list[Any]:
    try:
        return re.findall(pattern, text)
    except re.error:
        return []


def figure_label(fig: Figure) -> str:
    if fig.number:
        return f"Figure {fig.number} — {fig.title}".strip(" —")
    return fig.title or fig.caption or f"Unnumbered figure on page {fig.page}"


def build_prompt(fig: Figure, rule: ImageTypeRule, profile: Profile, section: str, doc_title: str,
                 model: str) -> tuple[str, str, str]:
    v = profile.vision
    embedded = "\n".join(f"- {t}" for t in fig.embedded_text[:200]) or "(none)"
    values = _SafeDict(figure_label=figure_label(fig), caption=fig.caption or "(no caption)", section=section or "(unknown)",
                       doc_title=doc_title or "(unknown)", page=str(fig.page), embedded_text=embedded,
                       language=v.language, image_type_label=rule.label)
    common = v.common_instructions.format_map(values)
    type_part = rule.prompt.format_map(values) if rule.prompt else ""
    keys = ['- "summary": string, 1-3 sentences describing what the figure shows']
    for s in rule.sections:
        keys.append(f'- "{s.key}": array of strings ({s.title})')
    keys.append('- "uncertain": array of strings (anything unreadable or ambiguous; empty if none)')
    spec = ("Return ONLY one JSON object, without code fences or commentary, with exactly these keys:\n"
            + "\n".join(keys))
    extra = f"\n\nAdditional reviewer instructions for this figure:\n{fig.prompt_extra.strip()}" if fig.prompt_extra.strip() else ""
    prompt = f"{common}\n\nImage type: {rule.label}\n{type_part}{extra}\n\n{spec}"
    system = v.system_prompt
    phash = hashlib.sha256(f"{system}\x1f{prompt}\x1f{model}\x1f{v.max_tokens}\x1f{v.temperature}".encode()).hexdigest()[:16]
    return system, prompt, phash


def classification_prompt(fig: Figure, profile: Profile) -> str:
    lines = [f"- {r.id}: {r.label}" for r in profile.vision.image_types if r.enabled]
    embedded = ", ".join(fig.embedded_text[:40]) or "(none)"
    return ("Classify this figure from a technical specification into exactly one image type.\n"
            f"Caption: {fig.caption or '(none)'}\nText in figure: {embedded}\n"
            "Allowed types:\n" + "\n".join(lines) + "\nReply with the id only.")


def prepare_image(path: Path, max_px: int) -> bytes:
    with Image.open(path) as im:
        im.load()
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if max(im.size) > max_px:
            im.thumbnail((max_px, max_px), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_model_json(text: str) -> dict[str, Any] | None:
    t = text.strip()
    m = JSON_FENCE_RE.search(t)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = t[start:end + 1]
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            data = json.loads(attempt)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def _as_items(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip(" -•\t") for s in v.splitlines() if s.strip(" -•\t")]
    if isinstance(v, dict):
        return [f"{k}: {_flat(x)}" for k, x in v.items()]
    if isinstance(v, list):
        return [_flat(x) for x in v if _flat(x)]
    return [str(v)]


def _flat(x: Any) -> str:
    if isinstance(x, dict):
        return "; ".join(f"{k}: {_flat(v)}" for k, v in x.items())
    if isinstance(x, list):
        return ", ".join(_flat(v) for v in x)
    return str(x).strip()


def result_from_text(text: str, rule: ImageTypeRule) -> VisionResult:
    data = parse_model_json(text)
    res = VisionResult(image_type=rule.id, raw=text[:20000])
    if data is None:
        res.structured = False
        res.summary = text.strip()[:4000]
        res.status = "uncertain"
        res.warnings.append("모델 응답이 지정한 JSON 형식이 아니어서 원문 그대로 저장했습니다.")
        return res
    res.summary = _flat(data.get("summary", "")).strip()
    for s in rule.sections:
        res.sections.append(DescriptionSection(key=s.key, title=s.title, items=_as_items(data.get(s.key))))
    known = {"summary", "uncertain"} | {s.key for s in rule.sections}
    extra = [k for k in data if k not in known]
    for k in extra:
        res.sections.append(DescriptionSection(key=k, title=k.replace("_", " ").capitalize(), items=_as_items(data[k])))
    res.uncertain = _as_items(data.get("uncertain"))
    res.status = "uncertain" if res.uncertain else "ok"
    if not res.summary:
        res.warnings.append("요약(summary)이 비어 있습니다.")
        res.status = "uncertain"
    return res


def unverified_tokens(res: VisionResult, reference_text: str, profile: Profile) -> list[str]:
    """Values / signal names stated by the model that do not appear in the source text."""
    v = profile.validation
    desc_text = "\n".join([res.summary] + [i for s in res.sections for i in s.items])
    desc = extract_tokens(desc_text, v.units, v.signal_patterns, v.extra_token_patterns)
    ref = extract_tokens(reference_text, v.units, v.signal_patterns, v.extra_token_patterns)
    ref_norm = normalize_text(reference_text)
    out: list[str] = []
    for key in desc.values:
        if key not in ref.values and key.split(" ")[0] not in ref.numbers:
            out.append(key)
    for sig in desc.signals:
        if sig not in ref.signals and sig not in ref_norm:
            out.append(sig)
    for ex in desc.extras:
        if ex not in ref.extras:
            out.append(ex)
    return sorted(set(out))


class VisionCache:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def key(self, *parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    def get(self, key: str) -> dict | None:
        return read_json(self.dir / key[:2] / f"{key}.json")

    def put(self, key: str, data: dict) -> None:
        atomic_write_json(self.dir / key[:2] / f"{key}.json", data)


def describe_figure(fig: Figure, image_path: Path, provider: Provider, profile: Profile, section: str,
                    doc_title: str, page_text: str, cache: VisionCache | None,
                    bypass_cache: bool = False) -> VisionResult:
    v = profile.vision
    rule = profile.image_type(fig.image_type) or profile.image_type("generic")
    if rule is None:  # profile removed every type: fall back to a minimal generic rule
        rule = ImageTypeRule(id="generic", label="Generic figure", prompt="Describe the figure.")
    system, prompt, phash = build_prompt(fig, rule, profile, section, doc_title, provider.model)
    ck = cache.key(fig.asset_sha256, phash, provider.id, provider.model) if cache else ""
    if cache and v.use_cache and not bypass_cache:
        hit = cache.get(ck)
        if hit:
            res = VisionResult(**hit)
            res.cached = True
            _post_check(res, fig, page_text, profile)
            return res
    t0 = time.monotonic()
    try:
        img = prepare_image(image_path, v.max_image_px)
        resp = provider.complete(system=system, prompt=prompt, images=[img], max_tokens=v.max_tokens,
                                 temperature=v.temperature)
    except (ProviderError, OSError) as exc:
        return VisionResult(status="failed", image_type=rule.id, provider=provider.id, model=provider.model,
                            prompt_hash=phash, created_at=utcnow(), error=str(exc)[:1000],
                            duration_ms=int((time.monotonic() - t0) * 1000))
    res = result_from_text(resp.text, rule)
    res.provider, res.model, res.prompt_hash = provider.id, resp.model or provider.model, phash
    res.created_at = utcnow()
    res.duration_ms = resp.latency_ms or int((time.monotonic() - t0) * 1000)
    if cache and v.use_cache and res.status != "failed":
        cache.put(ck, res.model_dump(exclude={"warnings"}))
    _post_check(res, fig, page_text, profile)
    return res


def _post_check(res: VisionResult, fig: Figure, page_text: str, profile: Profile) -> None:
    res.warnings = [w for w in res.warnings if not w.startswith("원문")]
    if res.status == "failed" or not profile.vision.flag_unverified_values:
        return
    reference = "\n".join(fig.embedded_text + [fig.caption, page_text])
    bad = unverified_tokens(res, reference, profile)
    if bad:
        res.warnings.append("원문(그림 내부 텍스트·캡션·페이지 본문)에서 확인되지 않는 값/신호명: " + ", ".join(bad[:20]))
        if res.status == "ok":
            res.status = "uncertain"
    if fig.kind == "raster" and not fig.embedded_text and res.status == "ok":
        res.warnings.append("래스터 이미지라 텍스트 레이어가 없어 AI 설명을 원문과 자동 대조할 수 없습니다.")
        res.status = "uncertain"
