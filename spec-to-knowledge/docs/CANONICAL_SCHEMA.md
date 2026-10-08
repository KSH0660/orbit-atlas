# Canonical JSON 스키마

Canonical JSON은 파서·검증기·Markdown 생성기·웹 UI가 함께 쓰는 중간 데이터입니다. 기계용 정의는 [canonical.schema.json](canonical.schema.json)(`spec2kb schema`로 생성)에 있습니다. 좌표는 PDF 포인트이며 원점은 왼쪽 위입니다: `[x0, top, x1, bottom]`. 페이지 번호는 1부터 셉니다.

```jsonc
{
  "schema_version": "1.0",
  "doc_id": "d3f2a9c1b7e4",
  "slug": "synthetic-ddr6-sdram-specification",
  "source": {"filename": "jedec_like_spec.pdf", "sha256": "…", "size_bytes": 78123, "page_count": 10, "pdf_metadata": {}},
  "metadata": {"title": "Synthetic DDR6 SDRAM Specification", "doc_number": "JESD-SYN-01", "revision": "1.0",
               "date": "", "publisher": "JEDEC", "tags": ["jedec"]},
  "metadata_override": {"revision": "1.0a"},                 // 사용자 수정 (effective = metadata + override)
  "pages": [{"number": 2, "width": 612, "height": 792, "kind": "toc", "status": "skipped",
             "removed_lines": ["JEDEC-Style Sample Standard No. SYN-01", "Page 2"],
             "source_text": "…텍스트 레이어 원문(머리글/바닥글 제외)…", "messages": ["목차 페이지로 판단…"]}],
  "blocks": [                                                  // 읽기 순서
    {"id": "p0006-b001", "type": "heading", "page": 6, "bbox": [72, 84.8, 260.1, 97.8],
     "text": "Electrical Characteristics", "number": "5", "level": 1, "font_size": 13, "bold": true,
     "origin": "text_layer", "confidence": 1.0, "md_override": null, "hints": {"hc": {"kind": "numbered"}}},
    {"id": "p0006-b004", "type": "table", "page": 6, "bbox": [123, 156, 489, 280], "ref": "tbl-2"},
    {"id": "p0008-b003", "type": "figure", "page": 8, "ref": "fig-2"},
    {"id": "p0003-b009", "type": "list_item", "label": "•", "text": "JESD-SYN-02, …"},
    {"id": "p0004-b005", "type": "note", "label": "NOTE 1", "text": "Unused CA inputs …"},
    {"id": "p0005-b006", "type": "paragraph", "text": "…", "pages": [5, 6], "hints": {"merged_from": "p0006-b000"}}
  ],
  "tables": [{"id": "tbl-3", "number": "3", "title": "Timing Parameters", "caption": "Table 3 — Timing Parameters",
              "page": 6, "bbox": […], "n_rows": 13, "n_cols": 5, "header_rows": 1, "method": "lines", "confidence": 1.0,
              "parts": [{"page": 6, "bbox": […], "rows": 9, "snapshot": "tbl-3-p0006.png"},
                        {"page": 7, "bbox": […], "rows": 4, "snapshot": "tbl-3-cont-p0007-p0007.png"}],
              "cells": [{"row": 0, "col": 0, "text": "Parameter", "rowspan": 1, "colspan": 1, "header": true, "bbox": […]}],
              "md_override": null}],
  "figures": [{"id": "fig-2", "number": "2", "title": "Read Burst Timing (BL16, RL = 22)", "page": 8, "bbox": […],
               "kind": "vector", "image_type": "timing_diagram", "image_type_source": "rule",
               "asset": "fig-2-p0008.png", "asset_sha256": "…", "width_px": 1316, "height_px": 560,
               "embedded_text": ["T0", "CK_t", "CK_c", "CMD", "RL = 22 nCK", "tDQSCK"],
               "description": {"status": "ok", "image_type": "timing_diagram", "summary": "…",
                               "sections": [{"key": "signals", "title": "Signals", "items": ["CK_t", "CK_c"]}],
                               "uncertain": [], "raw": "{…모델 원문…}", "structured": true,
                               "provider": "corp-vlm", "model": "Qwen2.5-VL-72B-Instruct", "prompt_hash": "…",
                               "created_at": "…", "duration_ms": 2310, "cached": false, "warnings": []},
               "description_override": null, "prompt_extra": "", "md_override": null}],
  "issues": [{"id": "val-number_distorted-6-…", "severity": "error", "code": "number_distorted", "page": 6,
              "message": "6쪽: 원문 숫자가 … 1.067 → 1.07", "source": "validator", "status": "open", "details": {}}],
  "processing": {"generator": "spec2kb 1.0.0", "profile_id": "jedec", "profile_hash": "…", "vision_provider": "mock",
                 "stats": {"body_size": 10.0, "furniture": ["page #"], "headings": 17, "tables": 3, "figures": 3}}
}
```

## 값 목록

| 필드 | 값 |
|---|---|
| `blocks[].type` | `heading`, `paragraph`, `list_item`, `note`, `table`, `figure` |
| `blocks[].origin` | `text_layer`, `ocr`, `vision`, `user` |
| `pages[].kind` | `text`, `scanned`, `toc`, `blank`, `cover` |
| `pages[].status` | `ok`, `warning`, `error`, `skipped`, `pending` |
| `figures[].kind` | `vector`, `raster`, `mixed`, `inferred`(캡션 기반 추정), `page`(스캔 페이지) |
| `description.status` | `ok`, `uncertain`(검토 필요), `failed`, `skipped`, `pending` |
| `issues[].source` | `parser`, `vision`, `validator`, `export` |
| `issues[].status` | `open`, `ignored`, `resolved` (overlay에 저장되어 다시 변환해도 유지) |

## 보조 파일

- `raw/pNNNN.json`: 페이지 분석 원시 결과(`RawPage`: info, blocks, tables, figures, issues, meta_lines, body_size, ocr_text)
- `overlay.json`: `{"blocks": {id: {md_override, edited_at}}, "tables": {...}, "figures": {id: {image_type, description_override, prompt_extra, md_override}}, "metadata": {...}, "issues": {id: status}}`
- 내보내기 `_meta/<doc>/source_map.json`: 파일별 블록 목록(`id, type, page, pages, bbox, ref, line_start, line_end, edited, origin`), 그림(자산 경로·내부 텍스트·설명 출처), 표(부분·행/열·방식·신뢰도)
