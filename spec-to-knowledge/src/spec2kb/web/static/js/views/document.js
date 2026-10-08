// Document workspace: setup -> run -> review -> issues -> preview -> export.
import { api, downloadFrom } from "../api.js";
import { clear, field, fmtBytes, fmtTime, h, progressBar, sevBadge, statusBadge, toast, SEV_LABEL } from "../ui.js";
import { renderReview } from "./review.js";

const TABS = [
  ["setup", "설정"], ["run", "변환"], ["review", "검토·수정"], ["issues", "검증 결과"], ["preview", "미리보기"], ["export", "내보내기"],
];

export async function renderDocument(root, docId, tab, page) {
  let doc = await api.get(`/api/docs/${docId}`);
  if (!tab) {
    tab = doc.active_job ? "run" : (doc.has_result ? "review" : "setup");
    history.replaceState(null, "", `#/doc/${docId}/${tab}`);
  }
  const cleanups = [];
  const s = doc.summary || {};
  const header = h("div", { class: "page-head" },
    h("div", { class: "grow" },
      h("div", { class: "small" }, h("a", { href: "#/docs" }, "← 문서 목록")),
      h("h1", { "data-testid": "doc-title" }, doc.title || doc.filename),
      h("div", { class: "row" }, statusBadge(doc.status), h("span", { class: "badge" }, `프로필: ${doc.profile_id}`),
        h("span", { class: "muted small" }, `${doc.filename} · ${doc.page_count}쪽 · ${fmtBytes(doc.size_bytes)}`),
        doc.has_result ? h("span", { class: `badge ${s.errors ? "err" : "ok"}` }, `오류 ${s.errors || 0}`) : null,
        doc.has_result && s.warnings ? h("span", { class: "badge warn" }, `경고 ${s.warnings}`) : null)),
    h("div", { class: "row" },
      h("a", { class: "btn", href: `/api/docs/${docId}/source.pdf`, target: "_blank" }, "원본 PDF")));

  const steps = h("nav", { class: "steps", "aria-label": "작업 단계" }, TABS.map(([id, label], i) => {
    const needsResult = ["review", "issues", "preview", "export"].includes(id);
    const done = (id === "setup" && doc.has_result) || (id === "run" && doc.has_result);
    return h("a", { href: `#/doc/${docId}/${id}`, class: `${id === tab ? "active" : ""} ${done ? "done" : ""} ${needsResult && !doc.has_result ? "disabled" : ""}`,
      "data-tab": id }, h("span", { class: "num" }, done ? "✓" : String(i + 1)), label);
  }));
  const body = h("div");
  root.append(header, steps, body);

  const refresh = async () => { doc = await api.get(`/api/docs/${docId}`); return doc; };
  const go = (t) => { location.hash = `#/doc/${docId}/${t}`; };

  if (tab === "setup") await renderSetup(body, doc, go);
  else if (tab === "run") cleanups.push(await renderRun(body, doc, refresh, go));
  else if (tab === "review") cleanups.push(await renderReview(body, doc, page, go));
  else if (tab === "issues") await renderIssues(body, doc, go);
  else if (tab === "preview") await renderPreview(body, doc);
  else if (tab === "export") await renderExport(body, doc);
  return () => cleanups.forEach((c) => typeof c === "function" && c());
}

// ---------------------------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------------------------
async function renderSetup(root, doc, go) {
  const [profiles, providers] = await Promise.all([api.get("/api/profiles"), api.get("/api/providers")]);
  let prof = await api.get(`/api/profiles/${doc.profile_id}`);
  const opts = structuredClone(doc.options || {});
  const get = (path) => path.split(".").reduce((o, k) => (o && k in o ? o[k] : undefined), opts);
  const set = (path, value) => {
    const keys = path.split(".");
    let o = opts;
    keys.slice(0, -1).forEach((k) => { o[k] = o[k] && typeof o[k] === "object" ? o[k] : {}; o = o[k]; });
    if (value === undefined || value === "") delete o[keys[keys.length - 1]]; else o[keys[keys.length - 1]] = value;
  };
  const resolved = (path) => path.split(".").reduce((o, k) => (o ? o[k] : undefined), prof.resolved);

  const profileSel = h("select", { "data-testid": "setup-profile" }, profiles.map((p) => h("option", { value: p.id, selected: p.id === doc.profile_id }, p.name)));
  const profileDesc = h("div", { class: "help" }, prof.raw.description || "");
  const defaults = h("div", { class: "help" });
  profileSel.addEventListener("change", async () => {
    prof = await api.get(`/api/profiles/${profileSel.value}`);
    profileDesc.textContent = prof.raw.description || "";
    renderOptions();
  });

  const optBox = h("div", { class: "form-grid" });
  function sel(path, label, choices, help) {
    const cur = get(path);
    const def = resolved(path);
    const defLabel = (choices.find((c) => String(c[0]) === String(def)) || [def, String(def)])[1];
    const s = h("select", { "data-opt": path, onchange: (e) => {
      const raw = e.target.value;
      if (raw === "__default") set(path, undefined);
      else set(path, typeof def === "number" ? Number(raw) : (typeof def === "boolean" ? raw === "true" : raw));
    } }, h("option", { value: "__default" }, `프로필 기본값 (${defLabel})`),
    choices.map(([v, l]) => h("option", { value: String(v), selected: cur !== undefined && String(cur) === String(v) }, l)));
    return field(label, s, help);
  }
  function txt(path, label, help, placeholder) {
    const def = resolved(path);
    const i = h("input", { type: "text", value: get(path) ?? "", "data-opt": path, placeholder: placeholder || (def ? `프로필 기본값: ${def}` : "비워두면 프로필 기본값"),
      oninput: (e) => set(path, e.target.value.trim() || undefined) });
    return field(label, i, help);
  }
  function renderOptions() {
    clear(optBox);
    optBox.append(
      txt("parsing.page_range", "처리할 페이지", "예: 1-20, 25. 비우면 전체 페이지. 큰 문서는 일부만 먼저 시험해 보세요.", "전체 페이지"),
      sel("vision.enabled", "AI 그림 설명", [[true, "사용"], [false, "사용 안 함 (이미지와 캡션만 보존)"]]),
      sel("vision.provider", "Vision 모델", providers.map((p) => [p.id, `${p.name} (${p.id})`]), "‘모델 / API’ 메뉴에서 사내 모델을 등록할 수 있습니다."),
      txt("vision.language", "AI 설명 언어", "예: English, Korean"),
      sel("markdown.split_level", "Markdown 파일 분할", [[0, "문서 전체를 한 파일로"], [1, "최상위 절마다 (1, 2, 3…)"], [2, "2단계 절마다 (1.1, 1.2…)"], [3, "3단계 절마다"]]),
      sel("markdown.table_format", "표 형식", [["auto", "자동 (병합 셀이 있으면 HTML)"], ["gfm", "항상 Markdown 표"], ["html", "항상 HTML 표"]]),
      sel("markdown.layout", "출력 구조", [["mkdocs", "MkDocs (docs/ 폴더)"], ["wiki", "Git Wiki (평면 페이지)"]]),
      sel("markdown.figure_description_style", "AI 설명 표시", [["blockquote", "인용 블록 (모든 엔진 호환)"], ["details", "접기 (details)"], ["admonition", "MkDocs admonition"]]),
    );
    clear(defaults);
    defaults.append(`이 문서에만 적용되는 설정입니다. 프로필 자체를 바꾸려면 `, h("a", { href: `#/profile/${profileSel.value}` }, "프로필 편집"), "을 이용하세요.");
  }
  renderOptions();

  const runBtn = h("button", { class: "primary big", "data-testid": "run-btn", onclick: async () => {
    runBtn.disabled = true;
    try {
      await api.patch(`/api/docs/${doc.id}`, { profile_id: profileSel.value, options: opts });
      await api.post(`/api/docs/${doc.id}/process`);
      toast("변환을 시작했습니다.", "ok");
      go("run");
    } catch (e) { toast(e.message, "error"); runBtn.disabled = false; }
  } }, doc.has_result ? "설정 저장 후 다시 변환" : "설정 저장 후 변환 시작");
  const saveBtn = h("button", { onclick: async () => {
    try { await api.patch(`/api/docs/${doc.id}`, { profile_id: profileSel.value, options: opts }); toast("저장했습니다.", "ok"); }
    catch (e) { toast(e.message, "error"); }
  } }, "설정만 저장");

  root.append(
    h("section", { class: "panel" }, h("h2", null, "프로필"),
      h("div", { class: "row", style: { alignItems: "flex-start" } },
        h("div", { style: { width: "360px" } }, field("변환 규칙 프로필", profileSel, null), profileDesc),
        h("div", { class: "grow callout" }, "프로필에는 제목·표·그림 인식 규칙, AI 프롬프트, Markdown 형식, 검증 기준이 들어 있습니다. 같은 종류의 문서에는 같은 프로필을 써야 결과 형식이 일관됩니다."))),
    h("section", { class: "panel" }, h("h2", null, "이 문서의 옵션"), defaults, h("div", { style: { height: "10px" } }), optBox),
    doc.has_result ? h("div", { class: "callout warn", style: { margin: "16px 0" } },
      "다시 변환해도 검토 단계에서 수정한 내용과 무시 처리한 이슈는 유지됩니다(같은 위치의 항목에 다시 적용). 일부 페이지만 바꾸려면 ‘검토·수정’에서 페이지 재처리를 사용하세요.") : null,
    h("div", { class: "row", style: { marginTop: "16px" } }, runBtn, saveBtn),
  );
  if (doc.has_result) root.appendChild(await metadataPanel(doc));
}

async function metadataPanel(doc) {
  const m = doc.metadata_effective || {};
  const auto = doc.metadata || {};
  const fields = [["title", "문서 제목"], ["doc_number", "문서 번호"], ["revision", "리비전"], ["publisher", "발행 기관"], ["date", "발행일"]];
  const inputs = {};
  const grid = h("div", { class: "form-grid" }, fields.map(([k, label]) => {
    inputs[k] = h("input", { type: "text", value: m[k] || "", "data-meta": k });
    return field(label, inputs[k], auto[k] ? `자동 추출: ${auto[k]}` : "자동 추출 값 없음");
  }));
  const save = h("button", { onclick: async () => {
    const body = {};
    for (const [k] of fields) body[k] = inputs[k].value.trim() === (auto[k] || "") ? "" : inputs[k].value;
    try { await api.patch(`/api/docs/${doc.id}/metadata`, body); toast("메타데이터를 저장했습니다. Frontmatter에 반영됩니다.", "ok"); }
    catch (e) { toast(e.message, "error"); }
  } }, "메타데이터 저장");
  return h("section", { class: "panel", style: { marginTop: "16px" } }, h("h2", null, "문서 메타데이터 (Frontmatter)"),
    h("p", { class: "help" }, "PDF에서 자동 추출한 값입니다. 잘못된 값은 고쳐서 저장하세요. 비우면 자동 추출 값을 사용합니다."), grid,
    h("div", { style: { marginTop: "10px" } }, save));
}

// ---------------------------------------------------------------------------------------------
// run
// ---------------------------------------------------------------------------------------------
const PHASE_LABEL = { scan: "머리글/바닥글 분석", parse: "페이지 분석", ocr: "스캔 페이지 OCR", assemble: "문서 조립", vision: "AI 그림 설명",
  validate: "검증", save: "저장" };

async function renderRun(root, doc, refresh, go) {
  let timer = null;
  const box = h("div");
  root.appendChild(box);

  async function tick() {
    const d = await refresh();
    clear(box);
    const job = d.active_job;
    if (job) {
      const full = await api.get(`/api/jobs/${job.id}`);
      box.append(h("section", { class: "panel" },
        h("h2", null, `${full.title || "변환"} 진행 중`),
        h("div", { class: "row spread" }, h("strong", { "data-testid": "phase" }, PHASE_LABEL[full.progress.phase] || full.progress.phase || "준비 중"),
          h("span", null, `${Math.round(full.progress.percent)}%`)),
        progressBar(full.progress.percent, true),
        h("p", { class: "muted" }, full.progress.message || ""),
        h("div", { class: "row" }, h("button", { class: "danger", onclick: async () => {
          await api.post(`/api/jobs/${job.id}/cancel`); toast("취소를 요청했습니다.");
        } }, "작업 취소")),
        h("h3", { style: { marginTop: "14px" } }, "작업 로그"),
        h("div", { class: "log" }, (full.log || []).join("\n") || "…")));
      timer = setTimeout(tick, 900);
      return;
    }
    const last = (d.jobs || [])[0];
    if (last && last.status === "done" && d.has_result) {
      const s = d.summary || {};
      box.append(h("section", { class: "panel", "data-testid": "run-done" },
        h("h2", null, "변환 완료"),
        h("div", { class: "kpis" },
          kpi("페이지", s.pages), kpi("제목", s.headings), kpi("표", s.tables), kpi("그림", s.figures),
          kpi("오류", s.errors, s.errors ? "err" : ""), kpi("경고", s.warnings, s.warnings ? "warn" : "")),
        h("p", null, s.errors ? "오류가 있습니다. ‘검증 결과’에서 원인을 확인하고 ‘검토·수정’에서 고치세요." : "검증 오류가 없습니다. AI 설명 등 경고 항목을 검토한 뒤 내보내세요."),
        h("div", { class: "row" }, h("button", { class: "primary", onclick: () => go("review") }, "검토·수정으로 이동"),
          h("button", { onclick: () => go("issues") }, "검증 결과 보기"), h("button", { onclick: () => go("preview") }, "Markdown 미리보기"))));
    } else if (last && (last.status === "failed" || last.status === "cancelled")) {
      box.append(h("section", { class: "panel" }, h("h2", null, last.status === "failed" ? "작업 실패" : "작업 취소됨"),
        h("div", { class: "callout warn" }, last.error || ""),
        h("div", { class: "row", style: { marginTop: "10px" } }, h("button", { class: "primary", onclick: async () => {
          try { await api.post(`/api/docs/${d.id}/process`); tick(); } catch (e) { toast(e.message, "error"); }
        } }, "다시 실행"), h("button", { onclick: () => go("setup") }, "설정 확인"))));
    } else {
      box.append(h("section", { class: "panel" }, h("h2", null, "아직 변환하지 않았습니다"),
        h("p", null, "설정을 확인한 뒤 변환을 시작하세요."),
        h("button", { class: "primary", onclick: async () => {
          try { await api.post(`/api/docs/${d.id}/process`); tick(); } catch (e) { toast(e.message, "error"); }
        } }, "변환 시작")));
    }
    if ((d.jobs || []).length) {
      box.append(h("section", { class: "panel" }, h("h2", null, "작업 기록"),
        h("table", { class: "list" }, h("thead", null, h("tr", null, h("th", null, "작업"), h("th", null, "상태"), h("th", null, "시작"), h("th", null, "종료"), h("th", null, "메시지"))),
          h("tbody", null, d.jobs.map((j) => h("tr", null, h("td", null, j.title || j.type), h("td", null, statusBadge(j.status)),
            h("td", { class: "small" }, fmtTime(j.started_at)), h("td", { class: "small" }, fmtTime(j.finished_at)),
            h("td", { class: "small" }, j.error || (j.result && j.result.summary ? `오류 ${j.result.summary.errors} · 경고 ${j.result.summary.warnings}` : ""))))))));
    }
  }
  await tick();
  return () => clearTimeout(timer);
}

function kpi(label, value, cls = "") {
  return h("div", { class: `kpi ${cls}` }, h("div", { class: "v" }, value ?? 0), h("div", { class: "k" }, label));
}

// ---------------------------------------------------------------------------------------------
// issues
// ---------------------------------------------------------------------------------------------
const CODE_LABEL = {
  value_missing: "수치·단위 누락/왜곡", number_missing: "숫자 누락", number_distorted: "숫자 왜곡", signal_missing: "신호명 누락", identifier_missing: "식별자 누락",
  text_coverage_low: "본문 누락 의심", table_grid_invalid: "표 구조 오류", table_ragged: "표 열 불일치", table_cols_changed: "표 열 수 변경",
  table_rows_changed: "표 행 수 변경", table_sparse: "빈 셀 과다", table_low_confidence: "표 추출 신뢰도 낮음", table_text_fallback: "괘선 없는 표",
  table_merged: "연속 표 병합", vision_failed: "AI 설명 실패", vision_uncertain: "AI 설명 검토 필요", vision_pending: "AI 설명 없음",
  vision_skipped: "AI 설명 생략", figure_uncaptioned: "캡션 없는 그림", figure_region_inferred: "그림 영역 추정", caption_without_figure: "그림 없는 캡션",
  caption_without_table: "표 없는 캡션", scanned_page: "스캔 페이지", ocr_unverified: "OCR 검토 필요", ocr_missing: "OCR 실패", ocr_disabled: "OCR 꺼짐",
  heading_number_gap: "절 번호 건너뜀", heading_duplicate: "절 번호 중복", figure_number_gap: "그림 번호 누락", table_number_gap: "표 번호 누락",
  broken_link: "깨진 링크", asset_missing: "이미지 파일 없음", frontmatter_missing: "Frontmatter 없음", edit_orphaned: "수정 내용 적용 실패",
  page_parse_failed: "페이지 분석 실패", figure_render_failed: "그림 렌더링 실패",
};

async function renderIssues(root, doc, go) {
  let data = await api.get(`/api/docs/${doc.id}/issues`);
  const sevSel = h("select", { style: { width: "140px" } }, h("option", { value: "" }, "모든 심각도"),
    ["error", "warning", "info"].map((s) => h("option", { value: s }, SEV_LABEL[s])));
  const stSel = h("select", { style: { width: "140px" } }, h("option", { value: "open" }, "열린 항목"), h("option", { value: "" }, "전체"),
    h("option", { value: "ignored" }, "무시함"), h("option", { value: "resolved" }, "해결함"));
  const search = h("input", { type: "search", placeholder: "메시지 검색", style: { width: "220px" } });
  const kpis = h("div", { class: "kpis" });
  const list = h("div");
  const revalidate = h("button", { onclick: async () => {
    try { await api.post(`/api/docs/${doc.id}/validate`); data = await api.get(`/api/docs/${doc.id}/issues`); draw(); toast("다시 검증했습니다.", "ok"); }
    catch (e) { toast(e.message, "error"); }
  } }, "다시 검증");

  function draw() {
    const s = data.summary;
    clear(kpis).append(kpi("오류", s.errors, s.errors ? "err" : ""), kpi("경고", s.warnings, s.warnings ? "warn" : ""), kpi("정보", s.infos),
      kpi("무시/해결", s.ignored), kpi("사용자 수정", s.edited_blocks));
    const q = search.value.trim().toLowerCase();
    const items = data.issues.filter((i) => (!sevSel.value || i.severity === sevSel.value) && (!stSel.value || i.status === stSel.value) &&
      (!q || i.message.toLowerCase().includes(q) || (i.code || "").includes(q)));
    clear(list);
    if (!items.length) { list.appendChild(h("div", { class: "empty" }, "조건에 맞는 항목이 없습니다.")); return; }
    list.appendChild(h("table", { class: "list", "data-testid": "issue-table" },
      h("thead", null, h("tr", null, h("th", null, "심각도"), h("th", null, "페이지"), h("th", null, "유형"), h("th", null, "내용"), h("th", null, "처리"))),
      h("tbody", null, items.map((i) => h("tr", { class: i.status !== "open" ? "muted" : "" },
        h("td", null, sevBadge(i.severity)),
        h("td", null, i.page ? h("a", { href: `#/doc/${doc.id}/review/${i.page}` }, `${i.page}쪽`) : "—"),
        h("td", { class: "small" }, CODE_LABEL[i.code] || i.code),
        h("td", { class: "small" }, i.message, i.file ? h("div", { class: "muted" }, i.file) : null),
        h("td", null, h("select", { style: { width: "110px" }, onchange: async (e) => {
          try { await api.patch(`/api/docs/${doc.id}/issues/${encodeURIComponent(i.id)}`, { status: e.target.value });
            data = await api.get(`/api/docs/${doc.id}/issues`); draw(); } catch (err) { toast(err.message, "error"); }
        } }, [["open", "열림"], ["ignored", "무시"], ["resolved", "해결"]].map(([v, l]) => h("option", { value: v, selected: i.status === v }, l)))))))));
  }
  [sevSel, stSel].forEach((el) => el.addEventListener("change", draw));
  search.addEventListener("input", draw);
  root.append(h("section", { class: "panel" },
    h("div", { class: "row spread" }, h("h2", null, "검증 결과"), h("div", { class: "row" }, sevSel, stSel, search, revalidate)),
    h("p", { class: "help" }, "원문 PDF의 수치·단위·신호명·표 구조가 Markdown에 그대로 남았는지 페이지 단위로 대조한 결과와, 처리 중 실패·불확실 항목입니다. 페이지를 누르면 원본과 나란히 보며 고칠 수 있습니다. 확인 후 문제가 없으면 ‘무시’로 바꾸세요(다시 변환해도 유지)."),
    kpis, h("div", { style: { height: "12px" } }), list));
  draw();
}

// ---------------------------------------------------------------------------------------------
// preview
// ---------------------------------------------------------------------------------------------
async function renderPreview(root, doc) {
  const tree = h("div", { class: "panel filetree", "data-testid": "file-tree" }, "미리보기 생성 중…");
  const view = h("div", { class: "panel" });
  root.appendChild(h("div", { class: "preview" }, tree, view));
  let info;
  try { info = await api.post(`/api/docs/${doc.id}/preview`); } catch (e) { clear(tree).append(e.message); return; }
  let mode = "rendered";
  let current = info.index;
  const seg = h("div", { class: "segmented" },
    h("button", { class: "active", onclick: (e) => setMode("rendered", e) }, "렌더링"),
    h("button", { onclick: (e) => setMode("raw", e) }, "Markdown 원문"));
  function setMode(m, e) { mode = m; seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === e.target)); open(current); }
  clear(tree).append(h("div", { class: "small muted", style: { marginBottom: "6px" } }, `출력 구조: ${info.layout} · 파일 ${info.files.length}개 · 이미지 ${info.assets.length}개`),
    info.files.map((f) => h("a", { href: "#", "data-path": f.path, onclick: (e) => { e.preventDefault(); open(f.path); } },
      f.path.endsWith("index.md") || !f.section ? f.title : `${f.title}`, h("div", { class: "small muted" }, f.path.split("/").pop()))));
  async function open(path) {
    current = path;
    tree.querySelectorAll("a").forEach((a) => a.classList.toggle("active", a.dataset.path === path));
    let f;
    try { f = await api.get(`/api/docs/${doc.id}/preview/file?path=${encodeURIComponent(path)}`); } catch (e) { toast(e.message, "error"); return; }
    clear(view).append(h("div", { class: "row spread" }, h("code", null, path), seg),
      mode === "raw" ? h("pre", { class: "rawmd", "data-testid": "raw-md" }, f.markdown)
        : h("div", { class: "md doc-render", "data-testid": "rendered-md", html: f.html }));
    view.querySelectorAll('a[href^="#preview:"]').forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); open(a.getAttribute("href").slice("#preview:".length));
    }));
  }
  open(current);
}

// ---------------------------------------------------------------------------------------------
// export
// ---------------------------------------------------------------------------------------------
async function renderExport(root, doc) {
  const layout = h("select", { style: { width: "260px" } }, h("option", { value: "" }, "프로필 설정 따름"),
    h("option", { value: "mkdocs" }, "MkDocs (docs/ 폴더 + mkdocs.yml)"), h("option", { value: "wiki" }, "Git Wiki (평면 페이지, 확장자 없는 링크)"));
  const btn = h("button", { class: "primary big", "data-testid": "export-btn", onclick: async () => {
    btn.disabled = true;
    try {
      const name = await downloadFrom("GET", `/api/docs/${doc.id}/export.zip${layout.value ? `?layout=${layout.value}` : ""}`, undefined, "export.zip");
      toast(`${name} 다운로드를 시작했습니다.`, "ok");
    } catch (e) { toast(e.message, "error"); } finally { btn.disabled = false; }
  } }, "ZIP 다운로드");
  const s = doc.summary || {};
  root.append(h("section", { class: "panel" }, h("h2", null, "지식베이스 ZIP 내보내기"),
    s.errors ? h("div", { class: "callout warn" }, `열린 오류가 ${s.errors}개 있습니다. 그대로 내보낼 수 있지만 ‘검증 결과’를 먼저 확인하는 것을 권장합니다.`) : h("div", { class: "callout ok" }, "열린 검증 오류가 없습니다."),
    h("div", { class: "row", style: { margin: "14px 0" } }, field("출력 구조", layout), btn),
    h("h3", null, "ZIP 구성"),
    h("ul", null,
      h("li", null, h("code", null, "docs/<문서>/index.md"), " — 문서 정보·목차·그림/표 목록 (Wiki 구조: ", h("code", null, "<문서>.md"), ")"),
      h("li", null, h("code", null, "docs/<문서>/NN-<절>.md"), " — 절 단위 Markdown, 모든 파일에 공통 Frontmatter"),
      h("li", null, h("code", null, "docs/<문서>/assets/"), " — 그림 원본 이미지, 표 원본 이미지, 스캔 페이지"),
      h("li", null, h("code", null, "_meta/<문서>/source_map.json"), " — Markdown 블록 ↔ PDF 페이지·좌표 매핑"),
      h("li", null, h("code", null, "_meta/<문서>/canonical.json"), " — Canonical 중간 데이터, ", h("code", null, "profile.json"), " — 적용 설정, ", h("code", null, "validation_report.md"), " — 검증 보고서"),
      h("li", null, h("code", null, "mkdocs.yml"), " — ", h("code", null, "mkdocs serve"), "로 바로 열람 (MkDocs 구조일 때)")),
    h("h3", null, "기타 다운로드"),
    h("div", { class: "row" },
      h("a", { class: "btn", href: `/api/docs/${doc.id}/canonical`, target: "_blank" }, "Canonical JSON 보기"),
      h("a", { class: "btn", href: `/api/docs/${doc.id}/source.pdf`, target: "_blank" }, "원본 PDF"))));
}
