# 모델 Provider 연결 (사내 LLM / Vision / OCR)

모든 모델 호출은 다음 계약 하나만 거칩니다(`spec2kb/providers/base.py`).

```python
provider.complete(system=str, prompt=str, images=[png_bytes, ...], max_tokens=int, temperature=float) -> ProviderResponse(text, model, latency_ms, usage)
```

Provider는 그림 설명(Vision), 스캔 페이지 OCR, 선택 사항인 LLM 이미지 분류, 연결 테스트에 쓰입니다. 특정 모델 가중치나 클라우드 SDK에 의존하지 않고 HTTP만 씁니다.

## 1. OpenAI 호환 (`type: openai`)

vLLM(`--served-model-name`), TGI(Messages API), LiteLLM, Ollama(`/v1`), 대부분의 사내 게이트웨이가 여기에 해당합니다.

| 필드 | 예시 | 설명 |
|---|---|---|
| `base_url` | `https://llm-gw.corp.local/v1` | 끝에 `/chat/completions`를 붙여 호출합니다. 전체 경로를 넣어도 됩니다. |
| `model` | `Qwen2.5-VL-72B-Instruct` | 요청의 `model` 필드 |
| `api_key_env` | `INTERNAL_LLM_KEY` | 키를 읽을 환경변수(권장) |
| `api_key` | — | 파일에 저장하는 키. 화면에서는 가려지고 ZIP에는 넣지 않습니다. |
| `auth_header` / `auth_scheme` | `Authorization` / `Bearer` | 사내 규격에 맞게 바꿉니다(예: `X-API-Key` / 빈값). |
| `headers` | `{"X-Team": "mem"}` | 추가 헤더 |
| `extra_body` | `{"top_p": 1, "response_format": {"type": "json_object"}}` | 요청 JSON에 병합합니다. |
| `image_detail` | `high` | `image_url.detail` |
| `timeout_s`, `max_retries` | `180`, `2` | 429/5xx/타임아웃/연결 실패 시 재시도합니다(지수 백오프, Retry-After 반영). |
| `verify_ssl`, `ca_bundle` | `true`, `/etc/pki/...pem` | 사내 PKI. 비우면 `S2K_CA_BUNDLE` 또는 시스템 기본값을 씁니다. |

요청 예:

```json
{"model": "Qwen2.5-VL-72B-Instruct", "max_tokens": 1500, "temperature": 0,
 "messages": [{"role": "system", "content": "You are a meticulous hardware documentation engineer..."},
              {"role": "user", "content": [{"type": "text", "text": "<프롬프트>"},
                                           {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]}]}
```

## 2. Custom HTTP (`type: custom_http`)

형식이 정해진 사내 OCR이나 Vision API는 코드를 고치지 않고 연결할 수 있습니다.

| 필드 | 예시 |
|---|---|
| `base_url` + `endpoint_path` | `https://ocr.corp.local` + `/api/v2/recognize` |
| `request_format` | `json` 또는 `multipart` |
| `request_template` | `{"image": "{{image_base64}}", "lang": "en", "instruction": "{{prompt}}", "max_len": "{{max_tokens}}"}` |
| `response_path` | `result.text` 또는 `data.pages[0].text` 또는 `choices.0.message.content` |
| `file_field` | multipart일 때 이미지 파일 필드명(기본 `file`) |

템플릿 변수: `{{prompt}}`, `{{system}}`, `{{image_base64}}`, `{{image_data_url}}`, `{{model}}`, `{{max_tokens}}`, `{{temperature}}`. 문자열 전체가 변수 하나면 숫자 같은 원래 타입을 유지하고, 문자열 안에 섞여 있으면 문자열로 치환합니다(JSON 이스케이프는 자동). `response_path`가 비어 있으면 응답 본문 전체를 씁니다. multipart에서는 템플릿 필드가 폼 필드가 되고 이미지는 파일로 보냅니다.

## 3. Mock (`type: mock`)

- 내장 `mock` Provider는 항상 있고 삭제할 수 없습니다. 네트워크 없이 전체 파이프라인을 검증하는 용도입니다.
- 프롬프트의 ‘그림 내부 텍스트’와 요청 JSON 키를 읽어 결정적인 JSON을 만듭니다. 이미지는 해석하지 않습니다.
- `extra_body` 옵션: `mock_hallucinate: true`(원문에 없는 값을 섞어 검증기 확인), `mock_fail: "always"`(실패 처리 확인), `mock_latency_ms`(취소·진행률 확인).

### Mock 모델 서버 (실제 HTTP 경로 검증)

```bash
spec2kb mock-server --port 9100 --api-key test-key
```

- `POST /v1/chat/completions`(OpenAI 호환), `GET /v1/models`, `POST /ocr`(Custom HTTP 예시: `{"image","prompt"}` → `{"result":{"text"}}`)
- UI의 ‘Provider 추가 → 로컬 Mock 서버’ 버튼이 `http://127.0.0.1:9100/v1`을 채웁니다. 실제 사내 게이트웨이와 같은 코드 경로(인증 헤더, 재시도, 이미지 전송)를 시험할 수 있습니다.

## 4. 프롬프트 구성

그림 하나에 대한 프롬프트는 다음 순서로 조립됩니다(`vision/describe.py: build_prompt`).

1. **공통 지침**(프로필 `vision.common_instructions`). 변수: `{figure_label}` `{caption}` `{section}` `{doc_title}` `{page}` `{embedded_text}` `{language}` `{image_type_label}`
   - `{embedded_text}`는 그림 영역 안의 PDF 텍스트 레이어(신호명, 타이밍 라벨 등)입니다. 모델에게 정확한 철자를 알려 주는 역할을 합니다.
2. **이미지 유형별 지침**(프로필 `vision.image_types[].prompt`). 유형은 캡션 정규식, 내부 텍스트 정규식, 우선순위로 정하며 사용자가 바꿀 수도 있습니다.
3. **그림별 추가 지침**(검토 화면의 ‘다시 해석’에서 입력)
4. **출력 형식**: 유형의 출력 항목(`sections`)으로 만든 JSON 키 목록. 항상 `summary`와 `uncertain`이 들어갑니다.

응답 처리 순서:

- 코드펜스와 앞뒤 설명을 지우고 JSON을 추출합니다. 끝의 쉼표는 보정합니다. 실패하면 원문을 그대로 보존하고 ‘검토 필요’로 표시합니다.
- 설명에 나온 수치+단위와 신호명이 그림 내부 텍스트·캡션·페이지 본문에 없으면 ‘원문에서 확인되지 않는 값’으로 경고하고 ‘검토 필요’로 표시합니다.
- 캐시 키는 이미지 SHA-256, 프롬프트 해시, Provider, 모델입니다. 같은 조합은 다시 호출하지 않고, ‘다시 해석’은 캐시를 무시합니다.

## 5. 첫 기동 시 자동 등록

`S2K_PROVIDERS_SEED=/etc/spec2kb/providers.json`을 지정하면 `providers.json`이 없을 때 이 목록으로 초기화합니다([예시](../deploy/providers.seed.example.json)).
