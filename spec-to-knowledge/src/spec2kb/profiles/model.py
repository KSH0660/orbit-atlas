"""Profile model: every user-tunable parsing / vision / Markdown / validation setting.

Titles and descriptions are Korean because the web UI renders its settings
forms directly from this model's JSON schema (single source of truth).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

class HeaderFooterCfg(_Cfg):
    enabled: bool = Field(True, title="머리글/바닥글 제거", description="페이지마다 반복되는 상·하단 텍스트(문서번호, 페이지 번호 등)를 본문에서 제거합니다.")
    top_ratio: float = Field(0.09, title="상단 영역 비율", description="페이지 높이 대비 머리글로 간주할 상단 영역 (0.09 = 9%).", ge=0, le=0.3)
    bottom_ratio: float = Field(0.08, title="하단 영역 비율", description="페이지 높이 대비 바닥글로 간주할 하단 영역.", ge=0, le=0.3)
    min_repeat_ratio: float = Field(0.3, title="반복 판정 비율", description="전체 페이지 중 이 비율 이상에서 반복되면 머리글/바닥글로 판단합니다.", ge=0.05, le=1)
    remove_page_numbers: bool = Field(True, title="페이지 번호 제거", description="상·하단 영역의 'Page 3', '- 3 -', '3 of 10' 형태를 제거합니다.")
    extra_patterns: list[str] = Field(default_factory=list, title="추가 제거 패턴(정규식)", description="위치와 관계없이 줄 전체가 일치하면 제거할 정규식 목록.")


class TocCfg(_Cfg):
    skip: bool = Field(True, title="목차 페이지 건너뛰기", description="점선 리더(.....)와 페이지 번호로 끝나는 줄이 많은 페이지를 목차로 보고 본문에서 제외합니다.")
    title_pattern: str = Field(r"(?i)^(table of )?contents$", title="목차 제목 패턴")
    leader_pattern: str = Field(r"(\.\s?){4,}\s*([\dA-Za-z]{1,4}(-\d+)?)?$", title="목차 줄 패턴", description="목차 항목 줄로 판단할 정규식 (점선 리더 + 페이지).")
    min_line_ratio: float = Field(0.35, title="목차 판정 비율", description="페이지의 줄 중 이 비율 이상이 목차 패턴이면 목차 페이지로 판단합니다.")


class HeadingCfg(_Cfg):
    numbered_pattern: str = Field(
        r"^(?P<num>\d{1,2}(?:\.\d{1,3}){0,5}|[A-Z](?:\.\d{1,3}){1,5})\.?\s+(?P<title>[A-Za-z(\"'][^\n]{0,200})$",
        title="번호 제목 패턴", description="'4.1.2 Title' 형태의 번호 제목을 찾는 정규식. num, title 그룹이 필요합니다.")
    annex_pattern: str = Field(
        r"^(?:Annex|ANNEX|Appendix|APPENDIX)\s+(?P<num>[A-Z])\b\s*(?P<title>.*)$",
        title="부록 제목 패턴", description="'Annex A (informative) ...' 형태의 부록 제목 정규식.")
    require_emphasis: bool = Field(True, title="강조(굵게/큰 글씨) 필수", description="번호가 있어도 굵거나 본문보다 큰 글씨일 때만 제목으로 인정합니다. 목록·수치 오인식을 줄입니다.")
    emphasis_size_ratio: float = Field(1.08, title="큰 글씨 판정 배율", description="본문 글자 크기 대비 이 배율 이상이면 '큰 글씨'로 봅니다.")
    max_length: int = Field(160, title="제목 최대 길이(문자)")
    max_level: int = Field(6, title="최대 제목 깊이", ge=1, le=6)
    check_sequence: bool = Field(True, title="번호 순서 검사", description="직전 제목과 번호가 이어지지 않으면(예: 6.2 다음 2) 강조가 약한 경우 본문으로 처리합니다.")
    unnumbered: bool = Field(True, title="번호 없는 제목 인식", description="'Foreword', 'Introduction'처럼 번호 없이 크고 굵은 줄을 1단계 제목으로 인식합니다.")
    unnumbered_size_ratio: float = Field(1.2, title="번호 없는 제목 글씨 배율")
    unnumbered_max_words: int = Field(10, title="번호 없는 제목 최대 단어 수")


class ParagraphCfg(_Cfg):
    columns: Literal["1", "auto"] = Field("1", title="단(컬럼) 구성", description="'1' = 1단 문서, 'auto' = 2단 레이아웃을 자동 감지하여 왼쪽→오른쪽 순서로 읽습니다.")
    gap_ratio: float = Field(0.55, title="문단 분리 간격 배율", description="줄 간격이 글자 높이 × 이 값보다 크면 새 문단으로 나눕니다.")
    dehyphenate: bool = Field(False, title="줄끝 하이픈 연결", description="줄 끝 '-'로 끊긴 단어를 합칩니다. 기술 용어(on-die 등) 손상 위험이 있어 기본값은 끔.")
    merge_across_pages: bool = Field(True, title="페이지 넘김 문단 연결", description="페이지 끝에서 끊긴 문장이 다음 페이지 소문자로 이어지면 한 문단으로 합칩니다.")
    bullet_chars: str = Field("•●▪■◦○–—*·-", title="글머리 기호 문자")
    enum_pattern: str = Field(r"^(\(?[a-z]\)|\(?[ivx]{1,4}\)|\(?\d{1,2}\))\s+", title="번호 목록 패턴", description="'a)', '(1)', 'ii)' 형태의 목록 항목 정규식.")
    note_pattern: str = Field(r"^(NOTES?|Note)(\s+\d+)?\s*[:.]?\s", title="NOTE 패턴", description="'NOTE 1 ...' 처럼 주석 문단을 인식하는 정규식.")


class TableCfg(_Cfg):
    enabled: bool = Field(True, title="표 추출")
    strategy: Literal["lines", "lines+text"] = Field("lines", title="표 감지 방식", description="lines = 괘선 기반(JEDEC 권장), lines+text = 괘선이 없는 표도 캡션 기준으로 텍스트 정렬 분석.")
    caption_pattern: str = Field(r"^Table\s+(?P<num>[A-Z]?\d+(?:[.\-]\d+)*)\s*(?:[—–:\-.]\s*)?(?P<title>.*)$", title="표 캡션 패턴")
    caption_position: Literal["above", "below", "auto"] = Field("above", title="캡션 위치", description="JEDEC은 표 위에 캡션이 있습니다.")
    caption_max_distance: float = Field(45, title="캡션-표 최대 거리(pt)")
    min_rows: int = Field(2, title="최소 행 수")
    min_cols: int = Field(2, title="최소 열 수")
    header_detection: Literal["bold", "first_row", "none"] = Field("bold", title="머리글 행 판정", description="bold = 굵은 글씨 행을 머리글로, first_row = 첫 행을 항상 머리글로.")
    max_header_rows: int = Field(3, title="최대 머리글 행 수")
    merge_continued: bool = Field(True, title="연속 표 병합", description="'(Cont'd)' 캡션 또는 다음 페이지 상단의 같은 열 구조 표를 하나로 합칩니다.")
    continued_pattern: str = Field(r"(?i)\((?:cont(?:'|’)?d\.?|continued)\)", title="연속 표 캡션 패턴")
    text_fallback: bool = Field(True, title="괘선 없는 표 보조 추출", description="캡션은 있는데 괘선 표가 없으면 텍스트 정렬로 표를 재구성합니다(불확실 항목으로 표시).")
    snapshot: bool = Field(True, title="표 원본 이미지 저장", description="표 영역을 이미지로도 저장해 원본과 비교할 수 있게 합니다.")
    snapshot_dpi: int = Field(150, title="표 이미지 해상도(DPI)")


class FigureCfg(_Cfg):
    enabled: bool = Field(True, title="그림 추출")
    caption_pattern: str = Field(r"^(?:Figure|Fig\.)\s+(?P<num>[A-Z]?\d+(?:[.\-]\d+)*)\s*(?:[—–:\-.]\s*)?(?P<title>.*)$", title="그림 캡션 패턴")
    caption_position: Literal["below", "above", "auto"] = Field("below", title="캡션 위치", description="JEDEC은 그림 아래에 캡션이 있습니다.")
    caption_max_distance: float = Field(90, title="캡션-그림 최대 거리(pt)")
    cluster_gap: float = Field(14, title="도형 묶음 간격(pt)", description="선·사각형·곡선을 하나의 그림으로 묶는 최대 간격.")
    min_width: float = Field(36, title="최소 폭(pt)")
    min_height: float = Field(24, title="최소 높이(pt)")
    min_objects: int = Field(4, title="최소 도형 수(벡터)")
    keep_uncaptioned: bool = Field(True, title="캡션 없는 그림 보존")
    min_uncaptioned_area: float = Field(9000, title="캡션 없는 그림 최소 면적(pt²)")
    infer_from_caption: bool = Field(True, title="캡션 기준 영역 추정", description="캡션은 있지만 도형이 감지되지 않으면 캡션 주변 영역을 그림으로 저장합니다.")
    render_dpi: int = Field(200, title="그림 렌더링 DPI", ge=72, le=600)
    max_pixels: int = Field(4000, title="최대 이미지 변 길이(px)")
    padding: float = Field(4, title="여백(pt)")


class ScannedCfg(_Cfg):
    min_chars: int = Field(25, title="스캔 페이지 판정 글자 수", description="텍스트 레이어 글자가 이 값보다 적고 큰 이미지가 있으면 스캔 페이지로 판단합니다.")
    ocr: bool = Field(True, title="스캔 페이지 OCR", description="Vision/OCR 모델로 텍스트를 추출합니다. 결과는 '불확실'로 표시되어 검토 대상이 됩니다.")
    ocr_dpi: int = Field(200, title="OCR 렌더링 DPI")
    ocr_prompt: str = Field(
        "Transcribe all text on this scanned specification page exactly as printed. "
        "Keep numbers, units and signal names unchanged. Use one line per text line. "
        "Mark unreadable words with [?]. Return plain text only.",
        title="OCR 프롬프트")


class MetadataCfg(_Cfg):
    doc_number_pattern: str = Field("", title="문서 번호 패턴", description="1~2페이지에서 문서 번호를 찾는 정규식 (첫 번째 그룹 사용).")
    revision_pattern: str = Field(r"\bRev(?:ision|\.)?\s*([A-Z0-9][\w.]*)", title="리비전 패턴")
    publisher: str = Field("", title="발행 기관")
    tags: list[str] = Field(default_factory=list, title="기본 태그")


class ParsingCfg(_Cfg):
    page_range: str = Field("", title="처리 페이지 범위", description="예: '1-20, 25'. 비우면 전체.")
    header_footer: HeaderFooterCfg = Field(default_factory=HeaderFooterCfg, title="머리글/바닥글")
    toc: TocCfg = Field(default_factory=TocCfg, title="목차")
    headings: HeadingCfg = Field(default_factory=HeadingCfg, title="제목(섹션)")
    paragraphs: ParagraphCfg = Field(default_factory=ParagraphCfg, title="문단·목록")
    tables: TableCfg = Field(default_factory=TableCfg, title="표")
    figures: FigureCfg = Field(default_factory=FigureCfg, title="그림·다이어그램")
    scanned: ScannedCfg = Field(default_factory=ScannedCfg, title="스캔 페이지")
    metadata: MetadataCfg = Field(default_factory=MetadataCfg, title="문서 메타데이터")


# ---------------------------------------------------------------------------
# vision
# ---------------------------------------------------------------------------

class SectionSpec(_Cfg):
    key: str = Field(..., title="키")
    title: str = Field(..., title="Markdown 표시 제목")


class ImageTypeRule(_Cfg):
    id: str = Field(..., title="유형 ID")
    label: str = Field(..., title="표시 이름")
    enabled: bool = Field(True, title="사용")
    priority: int = Field(0, title="우선순위", description="여러 규칙이 일치하면 높은 값이 우선합니다.")
    caption_regex: str = Field("", title="캡션 일치 정규식")
    text_regex: str = Field("", title="그림 내부 텍스트 정규식")
    min_text_hits: int = Field(1, title="내부 텍스트 최소 일치 수")
    prompt: str = Field("", title="유형별 해석 지침")
    sections: list[SectionSpec] = Field(default_factory=list, title="출력 항목")


DEFAULT_SYSTEM_PROMPT = (
    "You are a meticulous hardware documentation engineer. You convert figures from "
    "technical specifications into faithful, structured text for an engineering knowledge base."
)

DEFAULT_COMMON_INSTRUCTIONS = (
    "Describe only what is visible in the image. Never invent values, signal names or units.\n"
    "Copy numbers, units and signal names exactly as printed (e.g. CK_t, tRCD, 1.1 V).\n"
    "If something is unreadable or ambiguous, list it under \"uncertain\" instead of guessing.\n"
    "\n"
    "Figure: {figure_label}\n"
    "Section: {section}\n"
    "Document: {doc_title}\n"
    "Text found inside the figure region (from the PDF text layer, reliable):\n{embedded_text}\n"
    "\n"
    "Write the descriptions in {language}."
)


def _rule(id, label, priority, caption_regex, text_regex, min_hits, prompt, sections):
    return ImageTypeRule(id=id, label=label, priority=priority, caption_regex=caption_regex,
                         text_regex=text_regex, min_text_hits=min_hits, prompt=prompt,
                         sections=[SectionSpec(key=k, title=t) for k, t in sections])


def default_image_types() -> list[ImageTypeRule]:
    return [
        _rule("timing_diagram", "Timing diagram", 50, r"(?i)timing|waveform|burst|sequence",
              r"\b(CK_?[tc]|CLK\w*|DQS\w*|DQ\[?|T\d{1,2}\b|t[A-Z][A-Z0-9]{1,}\w*|CMD|CA\[)", 3,
              "This is a timing diagram. List every signal row from top to bottom, then the "
              "order of events along the time axis (commands, clock edges, data beats), then "
              "every timing parameter or latency annotation with its value and unit exactly "
              "as printed.",
              [("signals", "Signals"), ("sequence", "Event sequence"),
               ("parameters", "Timing parameters"), ("notes", "Notes")]),
        _rule("state_diagram", "State diagram", 40, r"(?i)state|transition|flow ?chart|flow diagram",
              r"(?i)\b(idle|active|state|entry|exit)\b", 2,
              "This is a state diagram or flow chart. List every state (node), then every "
              "transition as 'FROM -> TO: trigger/condition', exactly as labeled.",
              [("states", "States"), ("transitions", "Transitions"), ("notes", "Notes")]),
        _rule("pinout", "Pinout / ball map", 45, r"(?i)\bball\b|pin ?out|pin assignment|footprint|ballout",
              r"\b[A-Z]\d{1,2}\b", 6,
              "This is a pinout or ball assignment map. Describe the grid (rows, columns, view "
              "side) and list each readable ball/pin position with its signal name.",
              [("layout", "Layout"), ("pins", "Pins"), ("notes", "Notes")]),
        _rule("block_diagram", "Block diagram", 30, r"(?i)block|architecture|system|topology|overview|connection",
              "", 1,
              "This is a block diagram. List every block/component, then every connection "
              "or signal path between blocks with its label (bus names, voltages, protocols).",
              [("components", "Components"), ("connections", "Connections"), ("notes", "Notes")]),
        _rule("chart", "Chart / graph", 35, r"(?i)graph|chart|plot|curve|\bvs\.?\b|versus|derating|eye",
              "", 1,
              "This is a chart. Describe the axes (quantity and unit), each data series, and the "
              "key points (limits, crossings, maxima) with values exactly as printed.",
              [("axes", "Axes"), ("series", "Series"), ("key_points", "Key points")]),
        _rule("package_drawing", "Package / mechanical drawing", 35,
              r"(?i)package|outline|dimension|mechanical|drawing|land pattern", "", 1,
              "This is a mechanical drawing. Describe the views shown and list every dimension "
              "with its symbol, value, tolerance and unit exactly as printed.",
              [("views", "Views"), ("dimensions", "Dimensions"), ("notes", "Notes")]),
        _rule("table_image", "Table image", 20, r"(?i)^table", "", 1,
              "This image contains a table. Transcribe the column headers and every row "
              "exactly, one row per item as 'col1 | col2 | ...'.",
              [("columns", "Columns"), ("rows", "Rows")]),
        _rule("generic", "Generic figure", 0, "", "", 1,
              "Describe the figure: what it shows, its main elements and any labeled values.",
              [("elements", "Elements"), ("notes", "Notes")]),
    ]


class VisionCfg(_Cfg):
    enabled: bool = Field(True, title="AI 그림 설명 생성", description="Vision 모델로 그림/다이어그램 설명을 생성합니다. 끄면 이미지와 캡션만 보존합니다.")
    provider: str = Field("", title="Vision 모델(Provider)", description="'모델/API 설정'에 등록된 Provider ID. 비우면 기본 Provider를 사용합니다.")
    ocr_provider: str = Field("", title="OCR 모델(Provider)", description="스캔 페이지 OCR에 사용할 Provider. 비우면 Vision Provider를 사용합니다.")
    classification: Literal["rules", "llm", "rules_then_llm"] = Field("rules", title="이미지 유형 분류 방식", description="rules = 캡션/내부 텍스트 규칙, llm = 모델에 질의, rules_then_llm = 규칙 실패 시 모델.")
    concurrency: int = Field(2, title="동시 호출 수", ge=1, le=16)
    max_image_px: int = Field(1600, title="전송 이미지 최대 변(px)", description="모델 입력 한도에 맞게 긴 변을 축소합니다.")
    language: str = Field("English", title="설명 언어", description="예: English, Korean(한국어).")
    temperature: float = Field(0.0, title="Temperature", ge=0, le=2)
    max_tokens: int = Field(1500, title="최대 출력 토큰")
    use_cache: bool = Field(True, title="결과 캐시 사용", description="같은 이미지·프롬프트·모델 조합은 재호출하지 않습니다.")
    flag_unverified_values: bool = Field(True, title="원문에 없는 수치 경고", description="AI 설명 속 수치·신호명이 그림 내부/페이지 텍스트에 없으면 '불확실'로 표시합니다.")
    system_prompt: str = Field(DEFAULT_SYSTEM_PROMPT, title="시스템 프롬프트")
    common_instructions: str = Field(DEFAULT_COMMON_INSTRUCTIONS, title="공통 지침", description="변수: {figure_label} {caption} {section} {doc_title} {page} {embedded_text} {language} {image_type_label}")
    image_types: list[ImageTypeRule] = Field(default_factory=default_image_types, title="이미지 유형별 해석 규칙")


# ---------------------------------------------------------------------------
# markdown
# ---------------------------------------------------------------------------

class LabelsCfg(_Cfg):
    ai_description: str = Field("AI description", title="AI 설명 제목")
    unverified: str = Field("auto-generated — verify against the original figure", title="검증 안내 문구")
    uncertain: str = Field("Uncertain", title="불확실 항목 제목")
    figure_text: str = Field("Text in figure", title="그림 내부 텍스트 제목")
    source: str = Field("Source", title="출처 라벨")
    page: str = Field("p.", title="페이지 라벨")
    table_snapshot: str = Field("original table image", title="표 원본 이미지 링크 문구")
    reviewed_description: str = Field("Reviewed description", title="사용자 검토 설명 제목")
    contents: str = Field("Contents", title="목차 제목")
    document_info: str = Field("Document information", title="문서 정보 제목")
    figures: str = Field("Figures", title="그림 목록 제목")
    tables: str = Field("Tables", title="표 목록 제목")
    front_matter: str = Field("Front matter", title="표지/서문 영역 제목")
    scanned_note: str = Field("scanned page — OCR text below, verify against the image", title="스캔 페이지 안내 문구")


class MarkdownCfg(_Cfg):
    layout: Literal["mkdocs", "wiki"] = Field("mkdocs", title="출력 구조", description="mkdocs = docs/<문서>/ 하위 폴더 + .md 링크, wiki = 평면 페이지 + 확장자 없는 링크(GitLab/GitHub Wiki).")
    split_level: int = Field(1, title="파일 분할 수준", description="0 = 문서 하나를 한 파일로, 1 = 최상위 절(1, 2, 3...)마다 파일, 2 = 2단계 절마다 파일.", ge=0, le=3)
    frontmatter: bool = Field(True, title="Frontmatter 사용")
    frontmatter_fields: list[str] = Field(
        default_factory=lambda: ["title", "doc_number", "doc_title", "revision", "publisher",
                                 "section", "source_file", "source_pages", "profile",
                                 "generator", "generated_at", "tags"],
        title="Frontmatter 필드", description="사용 가능: title, doc_id, doc_number, doc_title, revision, publisher, date, section, source_file, source_sha256, source_pages, profile, generator, generated_at, tags")
    extra_frontmatter: dict[str, str] = Field(default_factory=dict, title="추가 Frontmatter", description="모든 파일에 추가할 고정 키/값.")
    heading_numbers: bool = Field(True, title="제목 번호 유지")
    table_format: Literal["auto", "gfm", "html"] = Field("auto", title="표 형식", description="auto = 병합 셀/다중 머리글이 있으면 HTML, 아니면 GFM 파이프 표.")
    figure_description_style: Literal["blockquote", "details", "admonition"] = Field("blockquote", title="AI 설명 표시 방식", description="blockquote = 모든 엔진 호환, details = 접기(HTML), admonition = MkDocs admonition 확장 필요.")
    include_embedded_text: bool = Field(True, title="그림 내부 텍스트 포함", description="검색성을 위해 그림 안의 텍스트(신호명 등)를 함께 기록합니다.")
    include_table_snapshot_link: bool = Field(False, title="표 원본 이미지 링크 포함")
    source_refs: Literal["comment", "inline", "none"] = Field("comment", title="출처 표기", description="comment = HTML 주석(<!-- p.12 -->), inline = 본문에 '(p. 12)' 표시, none = 생략.")
    file_name_pattern: str = Field("{index:02d}-{slug}", title="파일 이름 패턴", description="변수: {index} {slug} {number}")
    labels: LabelsCfg = Field(default_factory=LabelsCfg, title="고정 문구")


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

DEFAULT_UNITS = [
    "V", "mV", "µV", "uV", "A", "mA", "µA", "uA", "nA", "W", "mW", "µW", "uW",
    "s", "ms", "µs", "us", "ns", "ps", "fs", "Hz", "kHz", "MHz", "GHz",
    "nCK", "tCK", "tCK(avg)", "UI", "Ω", "ohm", "ohms", "kΩ", "MΩ", "°C", "℃", "K", "%",
    "pF", "nF", "µF", "uF", "nH", "µH", "Gb", "Mb", "Kb", "GB", "MB", "KB", "bit", "bits",
    "Byte", "Bytes", "B", "Mbps", "Gbps", "MT/s", "GT/s", "mm", "µm", "um", "mil", "V/ns", "mV/ns",
    "dB", "dBm", "ppm",
]

DEFAULT_SIGNAL_PATTERNS = [
    r"\b[A-Z][A-Z0-9]*_(?:[tc]|n|N|[A-Z0-9]+)\b",            # CK_t, CS_n, DQS_c, DM_n
    r"\b[A-Z][A-Z0-9]*\[\d+(?::\d+)?\]",                     # CA[13:0], DQ[15:0]
    r"\bt[A-Z][A-Z0-9]{1,}(?:_[A-Za-z0-9]+)?(?:\([a-z]+\))?",  # tRCD, tCCD_L, tCK(avg)
    r"\bV(?:DD|DDQ|PP|SS|SSQ|REF)[A-Z0-9]*\b",              # VDD, VDDQ, VPP, VDD2H
]


class ValidationCfg(_Cfg):
    enabled: bool = Field(True, title="검증 실행")
    units: list[str] = Field(default_factory=lambda: list(DEFAULT_UNITS), title="단위 목록", description="수치+단위 토큰 추출에 사용합니다.")
    signal_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_SIGNAL_PATTERNS), title="신호명 패턴(정규식)")
    extra_token_patterns: list[str] = Field(default_factory=list, title="추가 보존 토큰 패턴", description="반드시 보존되어야 하는 식별자 정규식 (예: 요구사항 ID 'REQ-[A-Z]+-\\d+').")
    coverage_warn_ratio: float = Field(0.9, title="텍스트 보존율 경고 기준", description="페이지 원문 대비 Markdown 문자 보존율이 이 값보다 낮으면 경고합니다.", ge=0, le=1)
    check_numbering: bool = Field(True, title="번호 연속성 검사", description="절/그림/표 번호의 누락·중복을 검사합니다.")
    check_tables: bool = Field(True, title="표 구조 검사")
    check_links: bool = Field(True, title="링크/이미지 경로 검사")


class Profile(_Cfg):
    id: str = Field(..., title="프로필 ID")
    name: str = Field(..., title="이름")
    description: str = Field("", title="설명")
    extends: str | None = Field(None, title="상속(부모 프로필)")
    builtin: bool = Field(False, title="기본 제공")
    created_at: str = ""
    updated_at: str = ""
    parsing: ParsingCfg = Field(default_factory=ParsingCfg, title="파싱")
    vision: VisionCfg = Field(default_factory=VisionCfg, title="AI 그림 해석")
    markdown: MarkdownCfg = Field(default_factory=MarkdownCfg, title="Markdown 출력")
    validation: ValidationCfg = Field(default_factory=ValidationCfg, title="검증")

    def image_type(self, type_id: str) -> ImageTypeRule | None:
        return next((r for r in self.vision.image_types if r.id == type_id), None)


SETTINGS_SECTIONS = ("parsing", "vision", "markdown", "validation")
META_FIELDS = ("id", "name", "description", "extends", "builtin", "created_at", "updated_at")
