"""Provider registry stored in <data>/providers.json (the built-in mock is always present)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from ..util import atomic_write_json, read_json
from .base import Provider, ProviderConfig, ProviderError
from .http import CustomHttpProvider, OpenAICompatProvider
from .mock import MockProvider

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,62}$")

BUILTIN_MOCK = ProviderConfig(id="mock", name="Mock (오프라인 검증용)", type="mock", model="mock-vision-1",
                              description="네트워크 없이 전체 파이프라인을 검증하기 위한 결정적(Deterministic) 응답 Provider. 실제 이미지를 해석하지 않습니다.",
                              builtin=True)


def make_provider(cfg: ProviderConfig) -> Provider:
    if cfg.type == "openai":
        return OpenAICompatProvider(cfg)
    if cfg.type == "custom_http":
        return CustomHttpProvider(cfg)
    if cfg.type == "mock":
        return MockProvider(cfg)
    raise ProviderError(f"알 수 없는 Provider 유형: {cfg.type}")


class ProviderStore:
    def __init__(self, path: Path, allow_key_storage: bool = True, seed_file: str = ""):
        self.path = path
        self.allow_key_storage = allow_key_storage
        self._lock = threading.RLock()
        if not self.path.exists():
            seeded: list[dict] = []
            if seed_file and Path(seed_file).exists():
                seeded = json.loads(Path(seed_file).read_text(encoding="utf-8"))
            atomic_write_json(self.path, {"providers": seeded})

    def _load(self) -> list[ProviderConfig]:
        data = read_json(self.path, {"providers": []}) or {"providers": []}
        out = []
        for raw in data.get("providers", []):
            try:
                out.append(ProviderConfig(**raw))
            except Exception:  # skip broken entries rather than failing the whole app
                continue
        return out

    def _save(self, items: list[ProviderConfig]) -> None:
        atomic_write_json(self.path, {"providers": [p.model_dump(exclude={"builtin"}) for p in items if not p.builtin]})

    def list(self) -> list[ProviderConfig]:
        return [BUILTIN_MOCK] + [p for p in self._load() if p.id != "mock"]

    def get(self, pid: str) -> ProviderConfig:
        for p in self.list():
            if p.id == pid:
                return p
        raise ProviderError(f"Provider를 찾을 수 없습니다: '{pid}'. '모델/API 설정'에서 등록하세요.")

    def upsert(self, data: dict[str, Any], *, create: bool) -> ProviderConfig:
        with self._lock:
            pid = str(data.get("id", "")).strip()
            if pid == "mock":
                raise ProviderError("기본 Mock Provider는 수정할 수 없습니다. 새 Provider를 추가하세요.")
            if not ID_RE.match(pid):
                raise ProviderError("Provider ID는 영문 소문자/숫자/-/_ 2~63자여야 합니다.")
            items = self._load()
            existing = next((p for p in items if p.id == pid), None)
            if create and existing:
                raise ProviderError(f"이미 존재하는 Provider ID입니다: {pid}")
            if not create and not existing:
                raise ProviderError(f"Provider를 찾을 수 없습니다: {pid}")
            data = dict(data)
            data.pop("builtin", None)
            data.pop("api_key_set", None)
            data.pop("api_key_env_present", None)
            if existing and not data.get("api_key"):
                data["api_key"] = existing.api_key  # empty field in the form = keep the stored key
            if data.get("api_key") and not self.allow_key_storage:
                raise ProviderError("이 서버는 API Key 저장이 비활성화되어 있습니다 (S2K_ALLOW_API_KEY_STORAGE=0). 환경변수 이름을 사용하세요.")
            cfg = ProviderConfig(**data)
            if cfg.type == "custom_http" and cfg.request_template.strip():
                try:
                    json.loads(cfg.request_template)
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"요청 템플릿이 올바른 JSON이 아닙니다: {exc}") from exc
            items = [p for p in items if p.id != pid] + [cfg]
            self._save(items)
            return cfg

    def delete(self, pid: str) -> None:
        with self._lock:
            if pid == "mock":
                raise ProviderError("기본 Mock Provider는 삭제할 수 없습니다.")
            items = self._load()
            if not any(p.id == pid for p in items):
                raise ProviderError(f"Provider를 찾을 수 없습니다: {pid}")
            self._save([p for p in items if p.id != pid])

    def provider(self, pid: str) -> Provider:
        return make_provider(self.get(pid))
