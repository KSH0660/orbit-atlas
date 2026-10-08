"""Provider adapter contract.

Every LLM / Vision / OCR backend is reached through one method::

    provider.complete(system=..., prompt=..., images=[png_bytes, ...]) -> ProviderResponse

so that an in-house model gateway can be connected without code changes
(OpenAI-compatible endpoint or a JSON-templated custom HTTP API), and the
whole pipeline can be verified offline with the mock provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderType = Literal["openai", "custom_http", "mock"]


class ProviderConfig(BaseModel):
    id: str = Field(..., title="Provider ID")
    name: str = Field(..., title="이름")
    type: ProviderType = Field("openai", title="유형", description="openai = OpenAI 호환 /chat/completions (vLLM, TGI, 사내 게이트웨이 등), custom_http = 요청/응답 형식을 직접 지정, mock = 오프라인 검증용")
    description: str = Field("", title="설명")
    base_url: str = Field("", title="API Base URL", description="예: http://llm-gw.corp.local:8000/v1")
    endpoint_path: str = Field("", title="엔드포인트 경로", description="custom_http 전용. base_url 뒤에 붙는 경로 (예: /ocr/v2/recognize)")
    model: str = Field("", title="모델 이름")
    api_key: str = Field("", title="API Key", description="저장 시 화면에는 가려서 표시됩니다. 가능하면 환경변수 이름을 사용하세요.")
    api_key_env: str = Field("", title="API Key 환경변수", description="API Key를 읽을 환경변수 이름 (예: INTERNAL_LLM_KEY). 설정 시 API Key보다 우선합니다.")
    auth_header: str = Field("Authorization", title="인증 헤더 이름")
    auth_scheme: str = Field("Bearer", title="인증 스킴", description="헤더 값 앞에 붙는 접두어. 비우면 키만 전송합니다.")
    headers: dict[str, str] = Field(default_factory=dict, title="추가 HTTP 헤더")
    extra_body: dict[str, Any] = Field(default_factory=dict, title="추가 요청 필드", description="요청 JSON에 병합할 필드 (예: {\"top_p\": 1}).")
    timeout_s: float = Field(120, title="타임아웃(초)", ge=1, le=1800)
    max_retries: int = Field(2, title="재시도 횟수", ge=0, le=10)
    verify_ssl: bool = Field(True, title="TLS 인증서 검증")
    ca_bundle: str = Field("", title="CA 번들 경로", description="사내 인증서 체인 파일 경로. 비우면 S2K_CA_BUNDLE 또는 시스템 기본값.")
    supports_vision: bool = Field(True, title="이미지 입력 지원")
    image_detail: str = Field("", title="이미지 detail", description="OpenAI 호환 image_url.detail 값 (high/low). 비우면 생략.")
    request_format: Literal["json", "multipart"] = Field("json", title="요청 형식(custom_http)")
    request_template: str = Field("", title="요청 템플릿(custom_http)", description="JSON 템플릿. 변수: {{prompt}} {{system}} {{image_base64}} {{image_data_url}} {{model}} {{max_tokens}} {{temperature}}")
    file_field: str = Field("file", title="파일 필드명(multipart)")
    response_path: str = Field("", title="응답 텍스트 경로(custom_http)", description="응답 JSON에서 텍스트 위치. 예: result.text, choices.0.message.content")
    builtin: bool = False

    def resolved_api_key(self) -> str:
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "").strip()
        return self.api_key

    def public(self) -> dict[str, Any]:
        data = self.model_dump()
        data["api_key_set"] = bool(self.api_key)
        data["api_key"] = ""
        data["api_key_env_present"] = bool(self.api_key_env and os.environ.get(self.api_key_env))
        return data


@dataclass
class ProviderResponse:
    text: str
    model: str = ""
    latency_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class Provider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def model(self) -> str:
        return self.config.model or self.config.type

    def complete(self, *, system: str, prompt: str, images: list[bytes] | None = None,
                 max_tokens: int = 1500, temperature: float = 0.0) -> ProviderResponse:
        raise NotImplementedError
