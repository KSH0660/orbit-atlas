# Spec-to-Knowledge (spec2kb)

JEDEC 표준, 고객 사양서, 데이터시트 같은 기술 PDF를 **문서가 달라도 같은 형식을 유지하는 Markdown 지식베이스**로 바꾸는 사내용 도구입니다. 사내 폐쇄망(RHEL 8.10, Python 3.11, 인터넷 차단)에서 그대로 돌아가도록 만들었고, 비개발자가 웹 화면만으로 업로드부터 검토·수정, ZIP 다운로드까지 할 수 있습니다.

![검토·수정 화면](docs/images/review.png)

| 요구사항 | 구현 |
|---|---|
| Spec Parser → Canonical Schema → Validator → Markdown Exporter | `spec2kb.parser` → `spec2kb.schema` (Canonical JSON) → `spec2kb.validator` → `spec2kb.exporter` |
| 텍스트·표·이미지·다이어그램 추출, Vision LLM 설명 | 레이아웃 분석(제목/문단/목록/NOTE), 괘선 표(병합 셀·다중 머리글·페이지 연속 표), 벡터/래스터 그림 영역 검출과 캡션 연결, 유형별 프롬프트로 구조화된 JSON 설명 |
| 원본 이미지 + AI 설명 보존, 출처 추적 | 그림 PNG(200 DPI) + 표 원본 이미지 + 설명(모델·프롬프트 해시·시각) + `source_map.json`(블록↔페이지·좌표·Markdown 줄) |
| 수치·단위·신호명·표 구조 누락/왜곡 검증 | 페이지 단위 원문↔Markdown 토큰 대조(수치+단위, 숫자, 신호명, 보존 식별자), 왜곡 추정(1.067→1.07, µs→ms), 표 행/열 구조, 번호 연속성, 링크 |
| No-Code Web UI | 업로드 → 설정 → 변환(진행률) → 원본/Markdown 나란히 검토·수정 → 검증 결과 → 미리보기 → ZIP |
| 모델/API Endpoint, 프롬프트 편집, 이미지 유형별 해석 규칙 | ‘모델 / API’ 화면(연결 테스트 포함), 프로필 편집기(공통 지침 + 유형별 규칙·출력 항목), 그림별 추가 지침 |
| 프로필 저장·복제·상속 | General / JEDEC / Customer 기본 제공, 상속(변경 항목만 저장)·복제·독립 사본·가져오기/내보내기 |
| 개별 페이지·그림 재처리, 실패·불확실 항목 확인 | 페이지 재처리, 그림 재해석(유형 변경·추가 지침), 실패/검토 필요 그림 일괄 재해석, 이슈 목록(무시/해결 상태 유지) |
| Provider Adapter 분리, Mock API | OpenAI 호환 / Custom HTTP(요청 템플릿·응답 경로) / Mock, `spec2kb mock-server`(OpenAI 호환 + Custom OCR 엔드포인트) |
| 오프라인 설치·운영 가이드 | 오프라인 번들 스크립트, 설치 스크립트, systemd 유닛, 환경변수 템플릿 ([DEPLOYMENT](docs/DEPLOYMENT.md)) |
| ZIP: Markdown + Assets + Source Mapping + 설정 | `docs/` 또는 Wiki 평면 구조 + `assets/` + `_meta/<문서>/{source_map,canonical,profile,validation_report}` + `mkdocs.yml` |
| MkDocs / Git Wiki 호환 | 상대경로만 사용, MkDocs 레이아웃은 `mkdocs build --strict` 통과를 테스트로 확인, Wiki 레이아웃은 확장자 없는 링크와 `Home.md`·`_Sidebar.md` 생성 |

---

## 1. 구조

```
              ┌────────────── Web UI (FastAPI + 빌드 없는 Vanilla JS) ──────────────┐
              │ 업로드 · 설정 · 진행률 · 검토/수정 · 검증 결과 · 미리보기 · 프로필 · Provider │
              └──────────────────────────────┬──────────────────────────────────────┘
                                             │ JSON API
   ┌─────────────────────────── Workspace (service.py) ─ JobManager (스레드 풀) ───────────┐
   │                                                                                       │
PDF ─▶ Spec Parser ─────▶ raw/pNNNN.json ─▶ assemble ─▶ Canonical JSON ─▶ Validator ─▶ Markdown Exporter ─▶ ZIP
   │   pdfplumber: 글자·선·표           (페이지별 원시 결과)   ▲   │  + overlay(사용자 수정)      │               MkDocs / Git Wiki
   │   pypdfium2 : 렌더링·밴드 텍스트                        │   │                            └ 공통 규칙·Frontmatter·source_map
   │                                                       │   └─▶ Vision stage ─ Provider Adapter ─ 사내 LLM/Vision/OCR
   │                                                       │        (분류·프롬프트·캐시·검증)   (OpenAI 호환 / Custom HTTP / Mock)
   └───────────────────────── 파일 저장소: <data>/docs/<id>/ (record, source.pdf, raw, canonical, overlay, assets, jobs)
```

- 의존성은 Python 휠만 씁니다(pdfplumber, pypdfium2, Pillow, pydantic, FastAPI, uvicorn, httpx, Markdown). DB, 큐, Node 빌드, LangGraph는 쓰지 않습니다.
- 페이지 단위 원시 결과(raw)와 사용자 수정(overlay)을 따로 저장합니다. 그래서 한 페이지만 다시 분석해도 다른 페이지의 수정 내용과 AI 설명은 그대로 남습니다(같은 이미지면 설명을 재사용).
- 상세 설계: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Canonical 스키마: [docs/CANONICAL_SCHEMA.md](docs/CANONICAL_SCHEMA.md)

## 2. 빠른 시작 (외부망: 개발·검증)

```bash
cd spec-to-knowledge
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pip install -e .

spec2kb serve                         # http://127.0.0.1:8765  (데이터: ./s2k-data)
spec2kb mock-server --port 9100       # (선택) OpenAI 호환 Mock 모델 API — 실제 HTTP 경로 검증용
```

1. 브라우저에서 `http://127.0.0.1:8765`를 열고 `samples/jedec_like_spec.pdf`를 끌어다 놓습니다(프로필: JEDEC Standard).
2. 변환이 끝나면 **검토·수정** 화면에서 원본 페이지와 결과를 비교합니다.
3. **내보내기**에서 ZIP을 받아 `mkdocs serve`로 엽니다.

Mock 서버로 실제 HTTP 호출까지 확인하려면 ‘모델 / API’ → ‘Provider 추가’ → ‘로컬 Mock 서버’를 누른 뒤 저장하고, 문서 설정의 ‘Vision 모델’에서 그 Provider를 고르면 됩니다.

명령줄 일괄 변환:

```bash
spec2kb convert a.pdf b.pdf --profile jedec --out kb.zip --kb-name "DDR KB" [--layout wiki] [--pages 1-50] [--provider corp-vlm] [--fail-on-error]
spec2kb doctor --full                  # 설치 자가 점검 (내장 샘플로 변환·검증·ZIP까지)
spec2kb mock-server --port 9100 [--api-key KEY]
spec2kb profiles list | show jedec --resolved | import profile.json
spec2kb providers list | test corp-vlm
spec2kb schema --out canonical.schema.json
```

## 3. 폐쇄망 설치 (요약)

전체 절차는 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)에 있습니다.

```bash
# (외부망 PC) RHEL 8용 휠 번들 생성: manylinux2014/2_28, CPython 3.11
scripts/build_offline_bundle.sh ./out            # → out/spec2kb-offline-1.0.0.tar.gz (+ .sha256)

# (폐쇄망 서버, RHEL 8.10) python3.11만 있으면 됩니다. Node.js와 컴파일러는 필요 없습니다.
sudo dnf install -y python3.11
tar xzf spec2kb-offline-1.0.0.tar.gz && cd spec2kb-offline-1.0.0
sudo ./install_offline.sh                        # /opt/spec2kb/venv, /var/lib/spec2kb, /etc/spec2kb/spec2kb.env, systemd 유닛, 자가 점검
sudo systemctl enable --now spec2kb
```

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `S2K_DATA_DIR` | `./s2k-data` | 업로드·결과·프로필·Provider·캐시 저장 위치 |
| `S2K_HOST` / `S2K_PORT` | `127.0.0.1` / `8765` | 서버 주소 |
| `S2K_WORKERS` | `2` | 동시에 처리하는 문서 수 |
| `S2K_MAX_UPLOAD_MB` | `300` | 업로드 최대 크기 |
| `S2K_BASIC_AUTH` | (없음) | `user:password` 형식이면 UI와 API에 Basic 인증 적용 |
| `S2K_DEFAULT_PROVIDER` | `mock` | 프로필에 Provider가 지정되지 않았을 때 쓸 Provider |
| `S2K_CA_BUNDLE` | (시스템) | 사내 HTTPS 모델 게이트웨이용 CA 번들 |
| `S2K_ALLOW_API_KEY_STORAGE` | `1` | `0`이면 API Key를 파일에 저장할 수 없고 환경변수만 허용 |
| `S2K_PROVIDERS_SEED` | (없음) | 첫 기동 시 등록할 Provider 목록 JSON ([예시](deploy/providers.seed.example.json)) |
| `S2K_PREVIEW_DPI` | `110` | 검토 화면 원본 페이지 해상도 |
| `S2K_LOG_LEVEL` | `INFO` | 로그 수준 |

## 4. 사용 흐름 (비개발자용)

자세한 화면 설명: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)

1. **문서**: PDF를 끌어다 놓고 프로필을 고릅니다(JEDEC / Customer / General / 사용자 프로필).
2. **설정**: 이 문서에만 적용할 옵션(페이지 범위, AI 설명 사용 여부, Vision 모델, 설명 언어, 파일 분할, 표 형식, 출력 구조)과 메타데이터(제목·문서번호·리비전)를 정합니다.
3. **변환**: 진행률과 로그를 봅니다. 취소할 수 있습니다. 끝나면 일부 페이지만 다시 처리하거나 실패·검토 필요 그림만 다시 해석할 수 있습니다.
4. **검토·수정**: 왼쪽에 원본 페이지와 블록 영역 표시, 오른쪽에 결과 블록이 나옵니다. 블록마다 Markdown을 고칠 수 있고, 저장하면 바로 다시 검증합니다. 그림은 유형 변경, 다시 해석(추가 지침 입력 가능), 설명 직접 작성을 지원합니다. 페이지 단위 재처리도 있습니다.
5. **검증 결과**: 누락·왜곡·구조 오류·AI 설명 검토 항목을 봅니다. 확인한 항목은 ‘무시’로 바꿀 수 있고, 다시 변환해도 그 상태가 유지됩니다.
6. **미리보기**: 최종 Markdown 파일 트리와 렌더링 결과(MkDocs와 같은 Python-Markdown 엔진)를 봅니다.
7. **내보내기**: 문서 하나 또는 여러 문서를 하나의 지식베이스 ZIP으로 받습니다.

## 5. 프로필

프로필은 파싱 규칙, AI 해석 규칙, Markdown 출력 규칙, 검증 기준을 묶은 설정입니다. 웹 화면의 설정 폼은 pydantic 모델(`profiles/model.py`)의 스키마에서 자동으로 만들어집니다.

- **General**: 일반 PDF용입니다. 2단 레이아웃 자동 감지, 괘선 없는 표 보조 추출, 캡션 위치 자동 판단을 켭니다.
- **JEDEC**(General 상속): 1단 레이아웃, 표 캡션은 위·그림 캡션은 아래, JESD 문서번호·리비전 추출, JEDEC 타이밍 다이어그램 프롬프트를 씁니다.
- **Customer**(General 상속): `1.` 형식 제목, 요구사항 ID(REQ-xxx-nnn) 보존 검증, Confidential 머리글 제거를 씁니다.
- **상속**은 부모와 다른 항목만 저장하므로 부모 프로필을 고치면 자식에도 자동으로 반영됩니다. 이미지 유형 규칙은 `id` 단위로 병합되므로 프롬프트 하나만 바꿀 수 있습니다.
- 저장할 때 모든 정규식을 컴파일하고 필수 그룹(`num`, `title`)이 있는지 검사합니다. 오류가 있으면 저장하지 않고 이전 상태로 되돌립니다.

## 6. 모델 / API (Provider Adapter)

자세한 내용: [docs/PROVIDERS.md](docs/PROVIDERS.md)

| 유형 | 용도 |
|---|---|
| `openai` | `/chat/completions` 호환 게이트웨이(vLLM, TGI, LiteLLM, 사내 프록시). 이미지는 `image_url` data URI로 보냅니다. |
| `custom_http` | 형식이 다른 사내 OCR/Vision API. JSON 요청 템플릿(`{{prompt}}`, `{{image_base64}}` 등)과 응답 경로(`result.text`)를 지정하며, multipart도 지원합니다. |
| `mock` | 오프라인 검증용입니다. 프롬프트에 포함된 그림 내부 텍스트로 결정적인 JSON을 만들고, 실패·지연·환각 주입 옵션이 있습니다. |

공통으로 타임아웃, 429/5xx 재시도(지수 백오프, Retry-After 반영), 사내 CA 번들, 프록시 환경변수, API Key 환경변수 참조를 지원합니다. 결과는 이미지·프롬프트·모델 기준으로 캐시합니다.

## 7. 결과물 (ZIP)

```
<kb-name>/
├─ mkdocs.yml                       # nav 포함, md_in_html·admonition·tables·toc
├─ README.md
├─ docs/
│  ├─ index.md                      # 지식베이스 홈(문서 목록)
│  └─ <doc-slug>/                   # 예: jesd-syn-01 (문서번호 기반)
│     ├─ index.md                   # 문서 정보, 목차, 그림·표 목록, 표지 영역
│     ├─ 01-foreword.md …           # 절 단위 파일, 공통 Frontmatter
│     └─ assets/  fig-2.png, tbl-3.png, tbl-3-part2.png, page-0007.png
└─ _meta/
   ├─ kb.json                       # 문서·파일 목록, 생성기 버전
   ├─ providers.json                # 사용한 Provider 설정(키 제외)
   └─ <doc-slug>/ canonical.json, source_map.json, profile.json, validation_report.{json,md}
```

Wiki 레이아웃(`--layout wiki`)은 `Home.md`, `_Sidebar.md`, `<doc>.md`, `<doc>--NN-<section>.md`, `assets/<doc>/`의 평면 구조를 쓰고, 링크는 확장자 없이 씁니다.

Markdown 공통 규칙(모든 문서·프로필 동일): [docs/MARKDOWN_RULES.md](docs/MARKDOWN_RULES.md)

## 8. 검증 항목

| 코드 | 의미 | 심각도 |
|---|---|---|
| `value_missing` | 원문의 수치+단위(1.1 V, 14.375 ns, 3.9 µs …)가 없거나 개수가 줄었습니다. 비슷한 값이 있으면 ‘왜곡 의심’으로 함께 표시합니다. | 오류 |
| `number_distorted` | 원문 숫자가 다른 값으로 바뀐 것으로 보입니다(반올림·소수점 이동·부호·한 자리 오타). | 오류 |
| `number_missing` | 단위 없는 숫자(표 셀 등)가 빠졌습니다. | 경고 |
| `signal_missing` | 신호명·파라미터명(CK_t, CA[13:0], tRCD, VDD …)이 빠졌습니다. 등장 횟수로 비교합니다. | 경고 |
| `identifier_missing` | 프로필에 지정한 보존 식별자(예: REQ-PWR-001)가 빠졌습니다. | 오류 |
| `text_coverage_low` | 페이지 원문 대비 Markdown 문자 보존율이 기준보다 낮습니다. | 경고 |
| `table_*` | 그리드 무결성, Markdown 표의 행·열 수와 들쭉날쭉함(사용자 수정 포함), 빈 셀 과다, 신뢰도 | 오류/경고 |
| `figure/table/heading_*_gap·duplicate` | 번호 누락·중복. 일부 페이지만 처리했으면 정보로만 표시합니다. | 경고/정보 |
| `vision_*` | AI 설명 실패, 원문에 없는 값을 언급함, 모델이 불확실하다고 표시함, 래스터라 자동 대조 불가 | 오류/경고 |
| `ocr_*`, `scanned_page` | 스캔 페이지와 OCR 결과 검토가 필요합니다. | 경고 |
| `broken_link`, `asset_missing`, `frontmatter_*` | 내보낼 결과의 링크·이미지·Frontmatter 무결성 | 오류 |

AI 설명은 대조 대상(Markdown 쪽 텍스트)에서 빼고 비교합니다. AI가 쓴 수치가 본문에서 빠진 수치를 가려 버리는 일을 막기 위해서입니다.

## 9. 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest            # 단위 + E2E(API·실제 HTTP Provider·mkdocs build --strict·CLI·작업 취소/복구) + 브라우저 E2E
python -m pytest -m "not browser"   # Chromium 없는 환경
```

| 범위 | 내용 |
|---|---|
| 파싱 정확도 (`test_parser_accuracy.py`) | 합성 샘플 4종의 정답(`samples/*.truth.json`)과 비교합니다. 제목(번호·단계) 완전 일치, 표 셀 완전 일치(병합 셀·2단 머리글·페이지 연속 표·괘선 없는 표), 그림 번호·캡션·내부 라벨, 목차·머리글/바닥글 제거, 2단 읽기 순서, 스캔 페이지 검출, 한글 제목·캡션(`그림 1.`/`표 1.`)과 본문 언급(`그림 1은`) 구분, 페이지 테두리, OCR 텍스트 레이어가 있는 스캔 페이지, 부록형 번호(`Figure A.1`, `Table 3a`) |
| 프로필 | 상속, 최소 diff 저장, id 단위 병합·삭제, 복제·평탄화, 순환·정규식 오류 롤백, 가져오기 |
| Markdown | 이스케이프(신호명 보존), GFM과 HTML 표(병합), MkDocs·Wiki 레이아웃, 문서 간 Frontmatter 키 일관성, 상대 링크 |
| 검증기 | 단위 정규화(µ/μ), 값 누락·단위 변경·숫자 왜곡·신호 누락·표 구조 변경 검출, 이슈 상태 유지, 링크 검사 |
| Provider | OpenAI 호환과 Custom HTTP를 실제 HTTP로 Mock 서버에 연결, 인증 실패, 503 재시도, 연결 거부, 키 마스킹, 환각 값 검출, 캐시, 실패 처리 |
| E2E API | 업로드 → 변환 → 페이지 보기 → 수정 → 이슈 무시 유지 → 페이지 재처리 후 수정 재적용 → 그림 재해석 → 메타데이터 → 미리보기 → 2문서 KB ZIP → 링크 검사 → `mkdocs build --strict` → Wiki ZIP, 업로드 오류, Provider 실패, Basic 인증 |
| CLI / 작업 | `convert`·`schema`·`doctor`, 서버 재시작 시 중단 작업 복구, 실행 중 취소 |
| 브라우저 E2E | Playwright + Chromium으로 업로드, 검토 수정, 그림 재해석, 검증 결과, 미리보기 이미지, ZIP 다운로드, 프로필 상속 편집, Provider 등록·연결 테스트를 수행하고 콘솔 오류 0건을 확인 |

최근 실행 결과: **54 passed** (Ubuntu 24.04, CPython 3.11.17, Chromium 1194).

## 10. 프로젝트 구조

```
spec-to-knowledge/
├─ src/spec2kb/
│  ├─ parser/      pdfdoc(파일·렌더) layout(줄·머리글/바닥글·목차·단) blocks(문단·목록·NOTE·제목 후보)
│  │               tables(괘선·병합 셀·무괘선) figures(도형 군집·라벨) page(페이지 조립) finalize(문서 단위 후처리) pipeline
│  ├─ schema.py    Canonical JSON (pydantic)
│  ├─ profiles/    model(설정 스키마·기본 프롬프트) store(상속·diff·검증) builtin/*.json
│  ├─ providers/   base http(OpenAI 호환·Custom HTTP) mock store
│  ├─ vision/      describe(분류·프롬프트·JSON 파싱·검증·캐시) stage(동시 실행·OCR)
│  ├─ validator/   tokens(수치·단위·신호 토큰, Markdown→평문) checks(검증·보고서)
│  ├─ exporter/    markdown(블록 규칙) package(레이아웃·Frontmatter·source map·mkdocs.yml·ZIP)
│  ├─ service.py   작업 흐름(업로드·변환·재처리·수정·검증·미리보기·내보내기)
│  ├─ jobs.py store.py config.py htmlrender.py mockserver.py cli.py
│  ├─ web/         app.py(API) static/(index.html, css, js/views/*.js — 빌드 없음)
│  └─ selftest/sample.pdf          doctor --full 용
├─ samples/        합성 샘플 PDF 4종(JEDEC형·고객·스캔·한글) + 정답 JSON + 결정적 생성 스크립트(reportlab)
├─ tests/          단위 + e2e(API, CLI/작업, 브라우저)
├─ scripts/        build_offline_bundle.sh, install_offline.sh
├─ deploy/         systemd 유닛, 환경변수 템플릿, nginx 예시, Provider 시드 예시
└─ docs/           ARCHITECTURE, DEPLOYMENT, PROVIDERS, USER_GUIDE, MARKDOWN_RULES, CANONICAL_SCHEMA, canonical.schema.json
```

---

## 11. 자체 검토 (Self-review)

검토 기준은 요구사항의 최우선 원칙인 파싱 정확도, 문서 간 형식 일관성, 사용자 커스터마이징, 폐쇄망 이식성입니다. ‘확인함’은 이 저장소의 테스트나 직접 실행으로 확인한 것이고, ‘미검증’은 이 환경에서 확인할 수 없었던 것입니다.

### 11.1 기능 완성도

| 항목 | 상태 | 근거 / 비고 |
|---|---|---|
| 텍스트 구조(제목·문단·목록·NOTE), 머리글/바닥글·목차 제거 | 확인함 | 합성 JEDEC·고객·한글 샘플에서 제목 28개를 번호·단계까지 정답과 완전히 일치시켰고, 머리글·쪽번호·목차 점선은 본문에 남지 않음 |
| 한글 문서 | 확인함 | 한글 제목(`1. 개요`), 캡션(`표 1.`, `그림 1.`), 본문 언급(`그림 1은 …`) 구분, 한글 이미지 유형 키워드, 캡션 접두어 설정(`그림`/`표`), 비라틴 제목의 파일 이름 대체(`sec-1`) |
| 표(병합 셀, 2단 머리글, 연속 표, 괘선 없는 표) | 확인함 | 표 6개의 셀 텍스트가 정답과 완전히 일치. 연속 표는 반복 머리글을 지우고 병합. 무괘선 표는 ‘검토 필요’로 표시 |
| 그림(벡터 다이어그램, 래스터 이미지, 캡션 연결, 내부 텍스트) | 확인함 | 타이밍·상태·블록 다이어그램과 볼맵 이미지를 검출. 캡션은 그림 텍스트에 섞이지 않음 |
| Vision 설명(유형별 규칙·구조화 JSON·환각 의심 표시·캐시) | Mock으로 확인함 | 실제 사내 모델로는 미검증. 프롬프트·출력 형식은 프로필에서 조정 가능 |
| 스캔 페이지 OCR | 경로만 확인함 | Mock OCR은 이미지를 읽지 않으므로 OCR 품질은 실제 모델로 확인해야 함. 결과는 항상 ‘OCR 검토 필요’로 표시 |
| 검증기(수치·단위·숫자 왜곡·신호명·식별자·표 구조·번호·링크) | 확인함 | 수정으로 누락·왜곡을 일부러 만들어 검출되는지 테스트로 확인. 깨끗한 변환에서는 오류 0건 |
| 출처 추적 | 확인함 | 모든 블록에 페이지·좌표, `source_map.json`에 Markdown 줄 범위, 그림 설명에 Provider·모델·프롬프트 해시·생성 시각 기록 |
| 웹 UI 전 과정 | 확인함 | 브라우저 E2E 테스트로 확인했고 콘솔 오류 0건 |
| 프로필 저장·복제·상속, 프롬프트·유형 규칙 편집 | 확인함 | API와 브라우저 테스트 |
| 페이지·그림 선택 재처리, 수정 내용 유지 | 확인함 | 재처리 후 같은 블록 ID에 수정이 다시 적용됨을 E2E로 확인. 대상이 사라지면 `edit_orphaned` 이슈에 수정 내용 보존 |
| MkDocs·Git Wiki 호환 | 확인함 / 일부 미검증 | MkDocs는 `mkdocs build --strict` 통과. Wiki는 링크 해석 규칙(확장자 없는 링크)을 테스트로 확인했으나 실제 GitLab/GitHub Wiki 서버에 올려 보지는 않음 |
| 성능 | 확인함 | 300쪽 합성 문서(표 90, 그림 90): 변환·Mock 설명·검증·ZIP 합계 약 25초. 페이지 화면 API 약 0.13초 |

### 11.2 오류 처리

- **업로드**: 확장자, `%PDF` 시그니처, 크기 제한, 열 수 없는 PDF, 0쪽 PDF를 각각 한국어 메시지로 거부하고 남은 파일을 정리합니다. 같은 내용의 파일을 다시 올리면 알려 줍니다.
- **페이지 격리**: 한 페이지 분석이 예외를 내도 문서 전체는 계속 진행합니다(`page_parse_failed` 이슈와 traceback 기록).
- **모델 호출**: 타임아웃·연결 실패·429·5xx는 재시도하고(지수 백오프, Retry-After), 4xx는 바로 실패합니다. 응답이 JSON이 아니면 원문을 보존하고 ‘검토 필요’로 표시합니다. 실패한 그림은 `vision_failed` 오류가 되지만 문서 변환은 끝까지 진행합니다. 없는 Provider ID를 지정해도 이유를 표시하고 진행합니다.
- **작업**: 취소할 수 있고, 취소되면 절반만 쓴 결과를 남기지 않습니다. 서버가 재시작되면 중단된 작업을 ‘실패’로 표시해 다시 실행할 수 있게 합니다. 문서별로 작업은 하나만 돌리고, 작업 중에는 수정을 409로 막습니다. 작업 상태는 문서 레코드를 갱신한 다음에 공개해 경쟁 조건을 없앴습니다.
- **저장**: 모든 JSON과 이미지를 임시 파일 → fsync → rename으로 원자적으로 씁니다. 데이터 파일 권한은 0600입니다.
- **설정**: 프로필은 pydantic 검증, 정규식 컴파일·필수 그룹 검사, 상속 순환 검사를 거치고 실패하면 롤백합니다. Provider의 요청 템플릿은 JSON 문법을 검사합니다.
- **보안**: 파일 경로 탈출을 막고, 미리보기 HTML은 허용 목록으로 정화합니다(스크립트·이벤트 속성·javascript: URL 제거). API Key는 화면과 ZIP에서 가리고, 환경변수 참조를 우선하며, 파일 저장을 금지하는 옵션도 있습니다. Basic 인증은 선택입니다.

### 11.3 오프라인 이식 가능성

- **확인함**: `scripts/build_offline_bundle.sh`로 RHEL 8용 번들(휠 28개, 약 26 MB)을 만들었습니다. 압축을 풀고 프록시 변수를 지운 채 `pip --no-index`로 새 venv에 설치한 뒤 `spec2kb doctor --full`(내장 샘플 변환·검증·ZIP)이 통과했습니다. 설치한 휠로 띄운 서버에서 UI 정적 파일도 정상 제공됐습니다.
- 바이너리 휠은 모두 manylinux2014 또는 manylinux_2_28(glibc ≤ 2.28)이라 RHEL 8.10의 glibc 2.28과 호환됩니다. 컴파일러, Node.js, 외부 CDN·폰트·JS, 모델 가중치, 클라우드 SDK는 필요 없습니다. UI는 빌드 단계 없는 정적 파일이라 Node.js 18이 있어도 쓰지 않습니다.
- **미검증**: 실제 RHEL 8.10 머신에서는 실행하지 못했습니다(검증 환경은 Ubuntu 24.04, CPython 3.11.17). RHEL 전용 단계(`dnf install python3.11`, systemd 유닛, SELinux·firewalld)는 문서화만 했습니다. 3.11.9와 3.11.17은 같은 마이너 버전이라 휠 호환성(cp311)은 같습니다.

### 11.4 알려진 한계와 권장 후속 작업

1. **실제 JEDEC PDF로는 검증하지 못했습니다(저작권).** 정답 비교는 합성 샘플로만 했습니다. 도입 첫 단계로 대표 실문서 3~5건을 변환해 검증 결과를 보고 JEDEC 프로필의 캡션·제목 패턴과 머리글 제거 패턴을 조정하기를 권장합니다. 프로필 상속을 쓰면 기본값을 건드리지 않고 조정할 수 있습니다.
2. **실제 Vision 모델 품질은 미확인입니다.** 사내 모델이 지정한 JSON 형식을 얼마나 지키는지와 프롬프트는 실데이터로 튜닝해야 합니다. 형식을 어기면 원문을 보존하고 ‘검토 필요’로 표시합니다.
3. **표**: 캡션이 없는 무괘선 표는 표로 인식하지 못하고 문단으로 남습니다. 셀 안의 줄바꿈은 공백으로 합칩니다.
4. **수식·위/아래 첨자**: 텍스트로 평탄화됩니다(예: V<sub>DDQ</sub> → VDDQ). 첨자 의미가 중요한 경우 검토 단계에서 수정해야 합니다.
5. **레이아웃 휴리스틱**: 2단 자동 감지는 General 프로필에서만 켭니다. 회전된 페이지와 세로 텍스트는 본문에서 빠지고 그림 이미지에만 남습니다. 페이지 전체를 가로지르는 벡터 워터마크는 그림 영역을 넓힐 수 있습니다(텍스트·이미지 워터마크와 페이지 테두리, 스캔 원본 배경 이미지는 제외 처리). 비밀번호가 걸린 PDF는 지원하지 않습니다.
6. **교차 참조**: “see Table 2” 같은 본문 참조는 링크로 바꾸지 않습니다.
7. **운영 형태**: 단일 프로세스 서버입니다(작업 상태가 메모리와 파일에 있음). `uvicorn --workers` 같은 멀티 프로세스로 띄우면 안 됩니다. 동시 처리량은 `S2K_WORKERS`로 조절하고, 더 키우려면 외부 큐가 필요합니다. 사용자별 권한과 감사 로그는 없으므로 리버스 프록시 SSO와 함께 쓰기를 권장합니다.
8. **래스터 그림**: 래스터 그림 속 수치는 텍스트 레이어가 없어 원문과 자동 대조할 수 없습니다. 이런 그림은 항상 ‘검토 필요’로 표시합니다.
