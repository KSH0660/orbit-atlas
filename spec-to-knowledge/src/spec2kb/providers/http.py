"""HTTP providers: OpenAI-compatible chat completions and a templated custom HTTP API."""

from __future__ import annotations

import base64
import copy
import json
import logging
import random
import re
import time
from typing import Any

import httpx

from ..config import get_settings
from .base import Provider, ProviderConfig, ProviderError, ProviderResponse

log = logging.getLogger(__name__)
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _verify(cfg: ProviderConfig) -> bool | str:
    if not cfg.verify_ssl:
        return False
    return cfg.ca_bundle or get_settings().ca_bundle or True


def _auth_headers(cfg: ProviderConfig) -> dict[str, str]:
    headers = dict(cfg.headers)
    key = cfg.resolved_api_key()
    if key and cfg.auth_header:
        headers[cfg.auth_header] = f"{cfg.auth_scheme} {key}".strip() if cfg.auth_scheme else key
    return headers


def _join(base: str, path: str) -> str:
    if not path:
        return base
    return base.rstrip("/") + "/" + path.lstrip("/")


def _describe_http_error(resp: httpx.Response) -> str:
    body = resp.text[:400].replace("\n", " ")
    return f"HTTP {resp.status_code}: {body}"


class _HttpProvider(Provider):
    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        cfg = self.config
        attempts = cfg.max_retries + 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=httpx.Timeout(cfg.timeout_s, connect=min(15.0, cfg.timeout_s)),
                                  verify=_verify(cfg), trust_env=True) as client:
                    resp = client.request(method, url, **kwargs)
                if resp.status_code < 400:
                    return resp
                retryable = resp.status_code in RETRY_STATUS
                err = ProviderError(_describe_http_error(resp), retryable=retryable, status=resp.status_code)
                if not retryable or attempt == attempts - 1:
                    raise err
                delay = _retry_after(resp) or (2 ** attempt) + random.random()
                last = err
            except httpx.TimeoutException as exc:
                last = ProviderError(f"시간 초과 ({cfg.timeout_s:.0f}s): {exc}", retryable=True)
                delay = 2 ** attempt
            except httpx.TransportError as exc:
                last = ProviderError(f"연결 실패: {type(exc).__name__}: {exc}", retryable=True)
                delay = 2 ** attempt
            if attempt < attempts - 1:
                log.warning("provider %s attempt %d failed: %s; retrying in %.1fs", cfg.id, attempt + 1, last, delay)
                time.sleep(min(delay, 30))
        assert last is not None
        raise last


def _retry_after(resp: httpx.Response) -> float | None:
    v = resp.headers.get("retry-after")
    if not v:
        return None
    try:
        return min(30.0, float(v))
    except ValueError:
        return None


class OpenAICompatProvider(_HttpProvider):
    """POST {base_url}/chat/completions with image_url data URIs (vLLM, TGI, LiteLLM, Azure-like gateways)."""

    def complete(self, *, system: str, prompt: str, images: list[bytes] | None = None,
                 max_tokens: int = 1500, temperature: float = 0.0) -> ProviderResponse:
        cfg = self.config
        if not cfg.base_url:
            raise ProviderError("Base URL이 설정되지 않았습니다.")
        if images and not cfg.supports_vision:
            raise ProviderError("이 Provider는 이미지 입력을 지원하지 않도록 설정되어 있습니다.")
        content: list[dict[str, Any]] | str
        if images:
            content = [{"type": "text", "text": prompt}]
            for img in images:
                part: dict[str, Any] = {"url": "data:image/png;base64," + base64.b64encode(img).decode("ascii")}
                if cfg.image_detail:
                    part["detail"] = cfg.image_detail
                content.append({"type": "image_url", "image_url": part})
        else:
            content = prompt
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        body: dict[str, Any] = {"model": cfg.model, "messages": messages, "max_tokens": max_tokens,
                                "temperature": temperature}
        body.update(copy.deepcopy(cfg.extra_body))
        url = cfg.base_url if cfg.base_url.rstrip("/").endswith("/chat/completions") else \
            _join(cfg.base_url, "chat/completions")
        t0 = time.monotonic()
        resp = self._send("POST", url, json=body, headers=_auth_headers(cfg))
        latency = int((time.monotonic() - t0) * 1000)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"응답이 JSON이 아닙니다: {resp.text[:200]}") from exc
        try:
            msg = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"응답 형식이 OpenAI 호환이 아닙니다: {json.dumps(data)[:300]}") from exc
        if isinstance(msg, list):
            msg = "".join(p.get("text", "") for p in msg if isinstance(p, dict))
        return ProviderResponse(text=str(msg or ""), model=str(data.get("model") or cfg.model),
                                latency_ms=latency, usage=data.get("usage") or {})


PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_template(template: Any, values: dict[str, Any]) -> Any:
    """Fill {{placeholders}} in a parsed JSON template; whole-string placeholders keep their type."""
    if isinstance(template, dict):
        return {k: render_template(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(v, values) for v in template]
    if isinstance(template, str):
        m = PLACEHOLDER_RE.fullmatch(template.strip())
        if m and m.group(1) in values:
            return values[m.group(1)]
        return PLACEHOLDER_RE.sub(lambda mm: str(values.get(mm.group(1), mm.group(0))), template)
    return template


def extract_path(data: Any, path: str) -> Any:
    cur = data
    for part in [p for p in re.split(r"\.|\[(\d+)\]", path) if p]:
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError) as exc:
                raise ProviderError(f"응답 경로 '{path}'의 '{part}'를 찾을 수 없습니다.") from exc
        elif isinstance(cur, dict):
            if part not in cur:
                raise ProviderError(f"응답 경로 '{path}'의 '{part}'를 찾을 수 없습니다. 키: {list(cur)[:10]}")
            cur = cur[part]
        else:
            raise ProviderError(f"응답 경로 '{path}'를 따라갈 수 없습니다.")
    return cur


class CustomHttpProvider(_HttpProvider):
    """Any JSON/multipart HTTP API, described by a request template and a response path."""

    def complete(self, *, system: str, prompt: str, images: list[bytes] | None = None,
                 max_tokens: int = 1500, temperature: float = 0.0) -> ProviderResponse:
        cfg = self.config
        if not cfg.base_url:
            raise ProviderError("Base URL이 설정되지 않았습니다.")
        img = images[0] if images else b""
        b64 = base64.b64encode(img).decode("ascii") if img else ""
        values = {"prompt": prompt, "system": system, "image_base64": b64,
                  "image_data_url": ("data:image/png;base64," + b64) if b64 else "",
                  "model": cfg.model, "max_tokens": max_tokens, "temperature": temperature}
        try:
            template = json.loads(cfg.request_template) if cfg.request_template.strip() else \
                {"model": "{{model}}", "prompt": "{{prompt}}", "image": "{{image_base64}}"}
        except json.JSONDecodeError as exc:
            raise ProviderError(f"요청 템플릿이 올바른 JSON이 아닙니다: {exc}") from exc
        body = render_template(template, values)
        if isinstance(body, dict):
            body.update(copy.deepcopy(cfg.extra_body))
        url = _join(cfg.base_url, cfg.endpoint_path)
        headers = _auth_headers(cfg)
        t0 = time.monotonic()
        if cfg.request_format == "multipart":
            fields = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in (body or {}).items()
                      if not (isinstance(v, str) and v == b64)}
            files = {cfg.file_field: ("image.png", img, "image/png")} if img else None
            resp = self._send("POST", url, data=fields, files=files, headers=headers)
        else:
            resp = self._send("POST", url, json=body, headers=headers)
        latency = int((time.monotonic() - t0) * 1000)
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype or resp.text.strip().startswith(("{", "[")):
            try:
                data = resp.json()
            except ValueError:
                data = None
            if data is not None:
                text = extract_path(data, cfg.response_path) if cfg.response_path else data
                if not isinstance(text, str):
                    text = json.dumps(text, ensure_ascii=False)
                return ProviderResponse(text=text, model=cfg.model, latency_ms=latency)
        return ProviderResponse(text=resp.text, model=cfg.model, latency_ms=latency)
