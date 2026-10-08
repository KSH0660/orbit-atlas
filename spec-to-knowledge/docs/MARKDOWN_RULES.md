# Markdown 공통 규칙

아래 규칙은 프로필이나 문서와 관계없이 같습니다(`exporter/markdown.py`, `exporter/package.py`). 프로필은 표시 방식처럼 정해진 선택지만 고를 수 있습니다.

## 파일과 경로

- 한 문서는 폴더 하나입니다(MkDocs: `docs/<doc-slug>/`, Wiki: `<doc-slug>.md` + `<doc-slug>--*.md`).
- `doc-slug`는 문서번호(없으면 제목)를 소문자 ASCII 슬러그로 바꾼 값입니다(예: `JESD-SYN-01` → `jesd-syn-01`). 지식베이스 안에서 겹치면 `-2`를 붙입니다.
- 절 파일 이름은 `NN-<제목 슬러그>.md`입니다(파일 분할 수준만큼, 기본 최상위 절). 부록은 `annex-a-…`가 됩니다.
- 이미지는 `assets/`에 둡니다: `fig-<번호>.png`, `tbl-<번호>.png`, 연속 표 두 번째 부분은 `tbl-<번호>-part2.png`, 스캔 페이지는 `page-NNNN.png`.
- 링크는 **상대 경로만** 씁니다. MkDocs는 `.md`를 붙이고 Wiki는 확장자 없이 씁니다. 절대 경로는 검증기가 오류로 처리합니다.

## Frontmatter

절 파일은 모두 같은 키를 같은 순서로 씁니다(프로필 `frontmatter_fields`로 고르고, 값이 없으면 빈 문자열).

```yaml
---
title: "5 Electrical Characteristics"
doc_number: "JESD-SYN-01"
doc_title: "Synthetic DDR6 SDRAM Specification"
revision: "1.0"
publisher: "JEDEC"
section: "5"
source_file: "jedec_like_spec.pdf"
source_pages: "6-7"
profile: "jedec"
generator: "spec2kb 1.0.0"
generated_at: "2026-10-08T05:36:01+00:00"
tags: ["jedec"]
---
```

문자열은 모두 큰따옴표로 감싸고 이스케이프하며, 목록은 flow 형식으로 씁니다.

## 블록

| 블록 | 형식 |
|---|---|
| 제목 | `#` 개수 = (절 단계 − 파일 최상위 단계 + 1), 최대 6. 번호를 유지합니다(`## 5.1 DC Operating Conditions`). |
| 문단 | 한 문단은 한 줄(줄바꿈 없음). 줄 끝 하이픈은 붙이고(`on-die`), 프로필 옵션으로 하이픈 제거를 고를 수 있습니다. |
| 목록 | 항상 `- `로 시작합니다. 열거 기호는 텍스트로 남깁니다(`- a) …`). 연속된 항목은 빈 줄 없이 이어 씁니다. |
| NOTE | `> **NOTE 1** …` (인용 블록) |
| 표 | `**Table N — 제목**` 다음 줄에 표를 둡니다. 병합 셀이나 다중 머리글이 있으면 HTML(`rowspan`/`colspan`, `thead`/`tbody`), 아니면 GFM으로 씁니다. 셀 안의 `|`는 이스케이프합니다. |
| 그림 | `![Figure N — 제목](assets/fig-N.png)` → `*Figure N — 제목*` → AI 설명 블록 → `**Text in figure:** CK_t · CK_c · …` |
| AI 설명 | 제목 줄 `**AI description (유형 · 모델 · auto-generated — verify against the original figure)**`, 요약, 유형별 항목(**Signals**, **Event sequence** …), **Uncertain**. 표시 방식은 인용 블록(기본), `<details>`, MkDocs admonition 중 하나입니다. 사용자가 직접 쓴 설명은 **Reviewed description**으로 표시합니다. |
| 스캔 페이지 | 페이지 이미지 + `*Scanned page N (scanned page — OCR text below, verify against the image)*` + OCR 텍스트 |
| 출처 | 페이지가 바뀌는 곳과 표·그림 앞에 `<!-- source: p.6-7 tbl-3 -->`(HTML 주석, 렌더링 안 됨). 다른 방식으로 본문 `(p. N)` 표기나 생략을 고를 수 있습니다. |

## 이스케이프 (최소화)

신호명은 검색과 grep이 되도록 그대로 둡니다: `CK_t`, `DQS_c`, `CA[13:0]`, `tCK(avg)`.

- 항상 이스케이프하는 문자: `\`, `` ` ``, `*`
- `_`는 단어 경계에 있을 때만 이스케이프합니다(`suffix \_n`). 단어 안의 `_`(`CK_t`)는 그대로 둡니다.
- 태그처럼 보이는 `<`는 `&lt;`로 바꿉니다(`< 3`은 그대로).
- 줄 맨 앞의 `#`, `>`, `-`, `+`, `*`, `|`, `1.`은 이스케이프합니다.

## 문서 인덱스 (`index.md`)

`# 제목` → **Document information** 표(문서번호, 리비전, 발행 기관, 원본 파일·쪽수, SHA-256, 프로필, 생성 시각) → **Contents**(절 파일 링크와 바로 아래 하위 절) → **Figures**와 **Tables**(파일 링크와 페이지) → **Front matter**(표지나 첫 제목 앞의 내용) 순서로 씁니다. 고정 문구는 프로필의 ‘고정 문구’로 바꿀 수 있습니다(예: 한국어 라벨).
