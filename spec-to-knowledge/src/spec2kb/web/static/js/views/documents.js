// Documents: upload + list + bulk export.
import { api, downloadFrom } from "../api.js";
import { clear, confirmDialog, field, fmtBytes, fmtTime, h, progressBar, statusBadge, toast } from "../ui.js";

export async function renderDocuments(root) {
  let timer = null;
  let selected = new Set();
  let profiles = [];
  try { profiles = await api.get("/api/profiles"); } catch (e) { toast(e.message, "error"); }

  const head = h("div", { class: "page-head" },
    h("div", null, h("h1", null, "문서"),
      h("p", null, "PDF를 업로드하면 프로필 규칙에 따라 Markdown 지식베이스로 변환합니다. 업로드 → 설정 확인 → 변환 → 검토·수정 → ZIP 다운로드 순서로 진행하세요.")));

  // --- upload card -----------------------------------------------------------------
  const fileInput = h("input", { type: "file", accept: "application/pdf,.pdf", multiple: true, class: "hidden", "data-testid": "file-input" });
  let pending = [];
  const fileList = h("div", { class: "filelist" });
  const profileSel = h("select", { "data-testid": "upload-profile" },
    profiles.map((p) => h("option", { value: p.id, selected: p.id === "jedec" }, `${p.name}${p.builtin ? "" : " (사용자)"}`)));
  const profileHelp = h("span", { class: "help" });
  const updateHelp = () => {
    const p = profiles.find((x) => x.id === profileSel.value);
    profileHelp.textContent = p ? (p.description || "") : "";
  };
  profileSel.addEventListener("change", updateHelp);
  updateHelp();
  const autoRun = h("input", { type: "checkbox", checked: true, "data-testid": "auto-run" });
  const uploadBtn = h("button", { class: "primary big", disabled: true, "data-testid": "upload-btn", onclick: doUpload }, "업로드");

  const drop = h("div", { class: "dropzone", tabindex: "0", role: "button", "aria-label": "PDF 파일 선택",
    onclick: () => fileInput.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") fileInput.click(); } },
  h("strong", null, "PDF 파일을 여기로 끌어다 놓거나 클릭해서 선택하세요"),
  h("div", { class: "muted small" }, "여러 파일을 한 번에 올릴 수 있습니다. 같은 프로필이 적용됩니다."),
  fileList);
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => setFiles([...e.dataTransfer.files]));
  fileInput.addEventListener("change", () => setFiles([...fileInput.files]));

  function setFiles(files) {
    const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length < files.length) toast("PDF가 아닌 파일은 제외했습니다.", "error");
    pending = pdfs;
    clear(fileList);
    pdfs.forEach((f) => fileList.appendChild(h("span", { class: "badge primary" }, `${f.name} · ${fmtBytes(f.size)}`)));
    uploadBtn.disabled = pdfs.length === 0;
  }

  async function doUpload() {
    if (!pending.length) return;
    uploadBtn.disabled = true;
    uploadBtn.textContent = "업로드 중…";
    const fd = new FormData();
    pending.forEach((f) => fd.append("files", f));
    fd.append("profile_id", profileSel.value);
    try {
      const res = await api.post("/api/docs", fd);
      res.errors.forEach((e) => toast(`${e.filename}: ${e.error}`, "error"));
      for (const d of res.created) {
        if (d.duplicate_of) toast(`${d.filename}: 이미 업로드된 파일과 내용이 같습니다.`, "");
        if (autoRun.checked) {
          try { await api.post(`/api/docs/${d.id}/process`); } catch (e) { toast(e.message, "error"); }
        }
      }
      toast(`${res.created.length}개 문서를 업로드했습니다.${autoRun.checked ? " 변환을 시작합니다." : ""}`, "ok");
      if (res.created.length === 1 && !autoRun.checked) location.hash = `#/doc/${res.created[0].id}/setup`;
      setFiles([]);
      await load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      uploadBtn.textContent = "업로드";
      uploadBtn.disabled = pending.length === 0;
    }
  }

  const uploadCard = h("section", { class: "panel" },
    h("h2", null, "① PDF 업로드"),
    h("div", { class: "row", style: { alignItems: "stretch", gap: "18px" } },
      h("div", { class: "grow" }, drop, fileInput),
      h("div", { class: "stack", style: { width: "330px" } },
        field("적용할 프로필", profileSel, null), profileHelp,
        h("label", { class: "check" }, autoRun, "업로드 후 바로 변환 시작"),
        uploadBtn)));

  // --- list ---------------------------------------------------------------------------------
  const listBody = h("div");
  const kbName = h("input", { type: "text", placeholder: "지식베이스 이름 (예: DDR5 Spec KB)", style: { width: "240px" }, "data-testid": "kb-name" });
  const layoutSel = h("select", { style: { width: "190px" } },
    h("option", { value: "" }, "출력 구조: 프로필 설정"),
    h("option", { value: "mkdocs" }, "MkDocs (docs/ 폴더)"),
    h("option", { value: "wiki" }, "Git Wiki (평면 페이지)"));
  const bulkBtn = h("button", { class: "primary", disabled: true, "data-testid": "bulk-export", onclick: bulkExport }, "선택 문서 ZIP 내보내기");
  const listCard = h("section", { class: "panel" },
    h("div", { class: "row spread" }, h("h2", null, "② 문서 목록"),
      h("div", { class: "row" }, kbName, layoutSel, bulkBtn)),
    listBody);

  async function bulkExport() {
    const ids = [...selected];
    bulkBtn.disabled = true;
    try {
      const name = await downloadFrom("POST", "/api/export", { doc_ids: ids, kb_name: kbName.value, layout: layoutSel.value || null }, "knowledge-base.zip");
      toast(`${name} 다운로드를 시작했습니다.`, "ok");
    } catch (e) { toast(e.message, "error"); } finally { bulkBtn.disabled = selected.size === 0; }
  }

  async function load() {
    let docs;
    try { docs = await api.get("/api/docs"); } catch (e) { toast(e.message, "error"); return; }
    selected = new Set([...selected].filter((id) => docs.some((d) => d.id === id && d.status === "ready")));
    bulkBtn.disabled = selected.size === 0;
    clear(listBody);
    if (!docs.length) {
      listBody.appendChild(h("div", { class: "empty" }, "아직 업로드한 문서가 없습니다. 위에서 PDF를 올려 보세요. 테스트용 샘플은 samples/ 폴더에 있습니다."));
      return;
    }
    const tbl = h("table", { class: "list", "data-testid": "doc-table" },
      h("thead", null, h("tr", null, h("th", null, ""), h("th", null, "문서"), h("th", null, "프로필"), h("th", null, "쪽수"),
        h("th", null, "상태"), h("th", null, "검증 결과"), h("th", null, "업데이트"), h("th", null, ""))),
      h("tbody", null, docs.map((d) => row(d))));
    listBody.appendChild(tbl);
    const busy = docs.some((d) => d.status === "processing" || d.status === "queued");
    clearTimeout(timer);
    if (busy) timer = setTimeout(load, 1500);
  }

  function row(d) {
    const cb = h("input", { type: "checkbox", checked: selected.has(d.id), disabled: d.status !== "ready", "aria-label": "선택",
      onchange: (e) => { e.target.checked ? selected.add(d.id) : selected.delete(d.id); bulkBtn.disabled = selected.size === 0; } });
    const s = d.summary || {};
    let statusCell = statusBadge(d.status);
    if (d.active_job) {
      statusCell = h("div", { class: "inline-progress" }, statusBadge("processing"), progressBar(d.active_job.progress.percent),
        h("span", { class: "small muted" }, `${Math.round(d.active_job.progress.percent)}%`));
    }
    const valid = d.status === "ready" ? h("div", { class: "row" },
      s.errors ? h("span", { class: "badge err" }, `오류 ${s.errors}`) : h("span", { class: "badge ok" }, "오류 0"),
      s.warnings ? h("span", { class: "badge warn" }, `경고 ${s.warnings}`) : null,
      h("span", { class: "small muted" }, `표 ${s.tables ?? 0} · 그림 ${s.figures ?? 0}`)) :
      (d.error ? h("span", { class: "small", style: { color: "var(--err)" } }, d.error.slice(0, 120)) : h("span", { class: "muted" }, "—"));
    return h("tr", { "data-doc": d.id },
      h("td", null, cb),
      h("td", null, h("a", { href: `#/doc/${d.id}`, class: "doc-link" }, h("strong", null, d.title || d.filename)),
        h("div", { class: "small muted" }, `${d.filename} · ${fmtBytes(d.size_bytes)}`)),
      h("td", null, h("span", { class: "badge" }, d.profile_id)),
      h("td", null, d.page_count),
      h("td", null, statusCell),
      h("td", null, valid),
      h("td", { class: "small muted nowrap" }, fmtTime(d.updated_at)),
      h("td", { class: "nowrap" },
        h("a", { class: "btn small", href: `#/doc/${d.id}` }, "열기"), " ",
        d.status === "ready" ? h("button", { class: "small", onclick: async () => {
          try { await downloadFrom("GET", `/api/docs/${d.id}/export.zip`, undefined, "export.zip"); } catch (e) { toast(e.message, "error"); }
        } }, "ZIP") : null, " ",
        h("button", { class: "small danger", disabled: !!d.active_job, onclick: async () => {
          if (!(await confirmDialog("문서 삭제", `'${d.title || d.filename}'와 변환 결과·수정 내용을 모두 삭제합니다.`, "삭제", true))) return;
          try { await api.del(`/api/docs/${d.id}`); toast("삭제했습니다.", "ok"); load(); } catch (e) { toast(e.message, "error"); }
        } }, "삭제")));
  }

  root.append(head, uploadCard, listCard);
  await load();
  return () => clearTimeout(timer);
}
