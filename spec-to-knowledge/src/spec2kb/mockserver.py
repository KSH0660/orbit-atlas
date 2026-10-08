"""Mock model API server for offline / external-network verification.

Endpoints
  POST /v1/chat/completions   OpenAI-compatible (text + image_url parts)
  GET  /v1/models             model list
  POST /ocr                   custom JSON API example: {"image": b64, "prompt": str} -> {"result": {"text": str}}
  GET  /health

Run:  spec2kb mock-server --port 9100 [--api-key secret]
"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from .providers.base import ProviderError
from .providers.mock import mock_generate


def create_mock_app(api_key: str = "") -> FastAPI:
    app = FastAPI(title="spec2kb mock model API", docs_url=None, redoc_url=None)
    app.state.calls = []

    def check(auth: str | None) -> None:
        if api_key and auth != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="invalid api key")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        check(authorization)
        return {"object": "list", "data": [{"id": "mock-vision-1", "object": "model", "owned_by": "spec2kb"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        check(authorization)
        body = await request.json()
        messages = body.get("messages") or []
        system, prompt, images = "", "", 0
        for m in messages:
            content = m.get("content")
            if m.get("role") == "system":
                system = content if isinstance(content, str) else ""
                continue
            if isinstance(content, str):
                prompt += content
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        prompt += part.get("text", "")
                    elif part.get("type") == "image_url":
                        url = (part.get("image_url") or {}).get("url", "")
                        if url.startswith("data:image/") and ";base64," in url:
                            base64.b64decode(url.split(",", 1)[1][:4096] + "==", validate=False)
                            images += 1
        app.state.calls.append({"prompt_chars": len(prompt), "images": images, "model": body.get("model")})
        try:
            text = mock_generate(system, prompt, images > 0, body)
        except ProviderError as exc:
            raise HTTPException(status_code=exc.status or 500, detail=str(exc)) from exc
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(time.time()),
            "model": body.get("model") or "mock-vision-1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4,
                      "total_tokens": (len(prompt) + len(text)) // 4},
        }

    @app.post("/ocr")
    async def ocr(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        check(authorization)
        body = await request.json()
        prompt = str(body.get("prompt", ""))
        has_image = bool(body.get("image"))
        app.state.calls.append({"prompt_chars": len(prompt), "images": int(has_image), "model": body.get("model")})
        try:
            text = mock_generate("", prompt, has_image, body)
        except ProviderError as exc:
            raise HTTPException(status_code=exc.status or 500, detail=str(exc)) from exc
        return {"result": {"text": text}, "engine": "mock-ocr"}

    return app
