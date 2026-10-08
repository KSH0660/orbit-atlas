// Review: original page (with block boxes) side by side with editable Markdown blocks.
import { api } from "../api.js";
import { BLOCK_LABEL, clear, confirmDialog, h, modal, progressBar, promptDialog, sevBadge, toast } from "../ui.js";

const VSTATUS = { ok: ["ok", "확인됨"], uncertain: ["warn", "검토 필요"], failed: ["err", "실패"], skipped: ["", "생략"], pending: ["", "대기"] };

export async function renderReview(root, doc, page, go) {
  let pages = await api.get(`/api/docs/${doc.id}/pages`);
  let onlyProblems = false;
  let current = page || (pages.find((p) => p.issues.error || p.issues.warning) || pages.find((p) => p.status !== "skipped") || pages[0]).number;
  let jobTimer = null;
  let data = null;

  const nav = h("div", { class: "pagenav", "data-testid": "page-nav" });
  const imgWrap = h("div", { class: "pageimg", "data-testid": "page-image" });
  const removedNote = h("div", { class: "small muted", style: { padding: "6px 2px" } });
  const pageHead = h("div", { class: "row spread", style: { marginBottom: "8px" } });
  const jobBanner = h("div");
  const blocksCol = h("div", { class: "blocks-col" });
  root.append(jobBanner, h("div", { class: "review" }, nav, h("div", { class: "pageview" }, pageHead, imgWrap, removedNote), blocksCol));

  function drawNav() {
    clear(nav);
    nav.appendChild(h("label", { class: "check small", style: { marginBottom: "4px" } },
      h("input", { type: "checkbox", checked: onlyProblems, onchange: (e) => { onlyProblems = e.target.checked; drawNav(); } }), "문제만"));
    for (const p of pages) {
      const problems = p.issues.error + p.issues.warning;
      if (onlyProblems && !problems && p.number !== current) continue;
      const dot = p.kind === "toc" || p.status === "skipped" ? "skipped" : p.status;
      nav.appendChild(h("button", { class: p.number === current ? "active" : "", "data-page": p.number,
        title: `${p.number}쪽 · ${p.kind === "toc" ? "목차(제외)" : p.kind === "scanned" ? "스캔" : p.kind === "cover" ? "표지" : ""} 오류 ${p.issues.error} · 경고 ${p.issues.warning}`,
        onclick: () => load(p.number) },
      h("span", null, `${p.number}`), h("span", { class: "row", style: { gap: "4px" } },
        problems ? h("span", { class: "small" }, problems) : null, h("span", { class: `sdot ${dot}` }))));
    }
  }

  async function load(n) {
    current = n;
    history.replaceState(null, "", `#/doc/${doc.id}/review/${n}`);
    drawNav();
    try { data = await api.get(`/api/docs/${doc.id}/pages/${n}`); } catch (e) { toast(e.message, "error"); return; }
    drawPage();
    drawBlocks();
  }

  function drawPage() {
    const p = data.page;
    clear(pageHead).append(
      h("div", null, h("strong", null, `${p.number} / ${data.page_count}쪽`), " ",
        p.kind !== "text" ? h("span", { class: "badge info" }, { toc: "목차 (본문 제외)", scanned: "스캔 페이지", cover: "표지", blank: "빈 페이지" }[p.kind] || p.kind) : null),
      h("div", { class: "row" },
        h("button", { class: "small", disabled: current <= 1, onclick: () => load(current - 1), "aria-label": "이전 페이지" }, "◀"),
        h("button", { class: "small", disabled: current >= data.page_count, onclick: () => load(current + 1), "aria-label": "다음 페이지" }, "▶"),
        h("button", { class: "small", "data-testid": "reprocess-page", onclick: reprocessPage }, "이 페이지 다시 처리")));
    clear(imgWrap);
    const img = h("img", { src: `/api/docs/${doc.id}/pages/${p.number}/image`, alt: `${p.number}쪽 원본`, loading: "eager" });
    imgWrap.appendChild(img);
    const W = p.width || 612, H = p.height || 792;
    const [ox, oy] = p.origin || [0, 0];  // CropBox offset: block coordinates are in MediaBox space
    for (const item of data.blocks) {
      const b = item.block;
      let bbox = b.page === current ? b.bbox : null;
      if (item.table && item.table.parts) {
        const part = item.table.parts.find((x) => x.page === current);
        if (part) bbox = part.bbox;
      }
      if (!bbox) continue;
      const [x0, y0, x1, y1] = [bbox[0] - ox, bbox[1] - oy, bbox[2] - ox, bbox[3] - oy];
      const box = h("div", { class: `bbox t-${b.type}`, "data-bid": b.id, title: BLOCK_LABEL[b.type] || b.type,
        style: { left: `${(x0 / W) * 100}%`, top: `${(y0 / H) * 100}%`, width: `${((x1 - x0) / W) * 100}%`, height: `${((y1 - y0) / H) * 100}%` },
        onmouseenter: () => highlight(b.id, true), onmouseleave: () => highlight(b.id, false),
        onclick: () => { const c = blocksCol.querySelector(`[data-card="${b.id}"]`); c && c.scrollIntoView({ behavior: "smooth", block: "center" }); } });
      imgWrap.appendChild(box);
    }
    removedNote.textContent = p.removed_lines && p.removed_lines.length ? `제거한 머리글/바닥글: ${p.removed_lines.join(" | ")}` : "";
  }

  function highlight(bid, on) {
    imgWrap.querySelectorAll(`[data-bid="${bid}"]`).forEach((el) => el.classList.toggle("hl", on));
    blocksCol.querySelectorAll(`[data-card="${bid}"]`).forEach((el) => el.classList.toggle("hl", on));
  }

  function drawBlocks() {
    clear(blocksCol);
    const issues = data.issues.filter((i) => i.status === "open");
    if (issues.length) {
      blocksCol.appendChild(h("div", { class: "issue-strip", "data-testid": "page-issues" }, issues.map((i) =>
        h("div", { class: `issue ${i.severity}` }, sevBadge(i.severity), h("span", { class: "grow" }, i.message),
          h("button", { class: "small ghost", title: "확인했으며 문제없음", onclick: async () => {
            try { await api.patch(`/api/docs/${doc.id}/issues/${encodeURIComponent(i.id)}`, { status: "ignored" }); await refreshAll(); }
            catch (e) { toast(e.message, "error"); }
          } }, "무시")))));
    }
    if (!data.blocks.length) {
      blocksCol.appendChild(h("div", { class: "panel empty" }, data.page.kind === "toc" ? "목차 페이지는 본문에서 제외했습니다. 필요하면 프로필의 ‘목차 페이지 건너뛰기’를 끄세요." : "이 페이지에서 추출된 내용이 없습니다."));
      return;
    }
    const list = h("div", { class: "blocks", "data-testid": "blocks" });
    for (const item of data.blocks) list.appendChild(item.block.type === "figure" ? figureCard(item) : blockCard(item));
    blocksCol.appendChild(list);
  }

  function cardShell(item, extraHead, bodyEl, actions) {
    const b = item.block;
    const head = h("div", { class: "bhead" },
      h("span", { class: `badge ${b.type === "heading" ? "primary" : ""}` }, BLOCK_LABEL[b.type] || b.type, b.type === "heading" && b.level ? ` H${b.level}` : ""),
      b.origin === "ocr" ? h("span", { class: "badge warn" }, "OCR") : null,
      item.edited ? h("span", { class: "badge edited" }, "수정됨") : null,
      b.page !== current ? h("span", { class: "badge" }, `${b.page}쪽에서 이어짐`) : null,
      extraHead, h("div", { class: "bactions" }, actions));
    return h("div", { class: "block", "data-card": b.id, onmouseenter: () => highlight(b.id, true), onmouseleave: () => highlight(b.id, false) }, head, bodyEl);
  }

  function blockCard(item) {
    const b = item.block;
    const body = h("div", { class: "md", html: item.html });
    const isTable = b.type === "table";
    const actions = [h("button", { class: "small", "data-testid": "edit-block", onclick: () => edit() }, "수정")];
    if (isTable && item.table && item.table.snapshot) {
      actions.unshift(h("button", { class: "small ghost", onclick: () => modal({ title: "원본 표 이미지", wide: true,
        body: h("div", null, (item.table.parts || []).filter((p) => p.snapshot).map((p) => h("img", { src: `/api/docs/${doc.id}/assets/${p.snapshot}`, style: { maxWidth: "100%" } }))),
        actions: [{ label: "닫기" }] }) }, "원본 표"));
    }
    const card = cardShell(item, isTable && item.table ? h("span", { class: "small muted" },
      `${item.table.n_rows}×${item.table.n_cols} · 머리글 ${item.table.header_rows}행 · ${item.table.method === "text" ? "텍스트 정렬 추출" : "괘선 추출"}`) : null, body, actions);

    function edit() {
      const ta = h("textarea", { class: "code", rows: Math.min(28, Math.max(4, item.markdown.split("\n").length + 2)), "data-testid": "block-editor" }, item.markdown);
      const save = h("button", { class: "primary small", "data-testid": "save-block", onclick: async () => {
        save.disabled = true;
        try {
          const url = isTable ? `/api/docs/${doc.id}/tables/${b.ref}` : `/api/docs/${doc.id}/blocks/${b.id}`;
          const value = ta.value.trim() === (item.generated_markdown || "").trim() ? null : ta.value;
          await api.patch(url, { md_override: value });
          toast("저장했습니다. 검증을 다시 실행했습니다.", "ok");
          await refreshAll();
        } catch (e) { toast(e.message, "error"); save.disabled = false; }
      } }, "저장");
      const revert = item.edited ? h("button", { class: "small", onclick: async () => {
        try {
          await api.patch(isTable ? `/api/docs/${doc.id}/tables/${b.ref}` : `/api/docs/${doc.id}/blocks/${b.id}`, { md_override: null });
          toast("자동 생성 결과로 되돌렸습니다.", "ok"); await refreshAll();
        } catch (e) { toast(e.message, "error"); }
      } }, "자동 생성값으로 되돌리기") : null;
      body.replaceChildren(ta, h("div", { class: "row", style: { marginTop: "6px" } }, save,
        h("button", { class: "small", onclick: () => body.replaceChildren(...h("div", { html: item.html }).childNodes) }, "취소"), revert,
        h("span", { class: "help" }, isTable ? "GFM 표 또는 HTML 표를 그대로 수정하세요. 저장 시 행·열 구조와 수치가 원문과 다시 대조됩니다." : "Markdown으로 수정합니다. 저장하면 원문 수치·신호명 대조 검증이 다시 실행됩니다.")));
      ta.focus();
    }
    return card;
  }

  function figureCard(item) {
    const b = item.block;
    const f = item.figure;
    if (!f) return blockCard(item);
    const d = f.description;
    const [vcls, vlabel] = d ? (VSTATUS[d.status] || ["", d.status]) : ["", "없음"];
    const typeSel = h("select", { style: { width: "200px" }, "data-testid": "figure-type", disabled: f.kind === "page" },
      data.image_types.map((t) => h("option", { value: t.id, selected: t.id === f.image_type }, t.label)));
    typeSel.addEventListener("change", async () => {
      try { await api.patch(`/api/docs/${doc.id}/figures/${f.id}`, { image_type: typeSel.value }); toast("이미지 유형을 바꿨습니다. ‘다시 해석’으로 설명을 새로 만드세요.", "ok"); await refreshAll(); }
      catch (e) { toast(e.message, "error"); }
    });
    const body = h("div", { class: "figure-box" },
      h("div", { class: "md", html: item.html }),
      f.kind !== "page" ? h("dl", { class: "kv" },
        h("dt", null, "이미지 유형"), h("dd", null, h("div", { class: "row" }, typeSel, h("span", { class: "small muted" },
          { rule: "규칙으로 자동 분류", llm: "모델이 분류", user: "사용자 지정", default: "기본값" }[f.image_type_source] || ""))),
        h("dt", null, "AI 설명 상태"), h("dd", null, h("span", { class: `badge ${vcls}`, "data-testid": "vision-status" }, vlabel),
          d && d.model ? h("span", { class: "small muted" }, ` ${d.provider}/${d.model}${d.cached ? " · 캐시" : ""}${d.duration_ms ? ` · ${(d.duration_ms / 1000).toFixed(1)}s` : ""}`) : null),
        d && d.error ? [h("dt", null, "오류"), h("dd", { class: "small", style: { color: "var(--err)" } }, d.error)] : null,
        d && d.warnings && d.warnings.length ? [h("dt", null, "검토 사유"), h("dd", { class: "small" }, d.warnings.join(" / "))] : null,
        f.prompt_extra ? [h("dt", null, "추가 지침"), h("dd", { class: "small" }, f.prompt_extra)] : null,
        h("dt", null, "출처"), h("dd", { class: "small" }, `${f.page}쪽 · ${f.kind} · ${f.width_px}×${f.height_px}px`)) : null);
    const actions = f.kind === "page" ? [] : [
      h("button", { class: "small", "data-testid": "redescribe", onclick: () => redescribe(f) }, "다시 해석"),
      h("button", { class: "small", onclick: () => writeDescription(f, item) }, f.description_override ? "설명 수정" : "설명 직접 작성"),
      f.description_override ? h("button", { class: "small", onclick: async () => {
        try { await api.patch(`/api/docs/${doc.id}/figures/${f.id}`, { description_override: null }); await refreshAll(); } catch (e) { toast(e.message, "error"); }
      } }, "AI 설명으로 복귀") : null,
    ];
    return cardShell(item, h("span", { class: "small muted" }, f.number ? `Figure ${f.number}` : f.kind === "page" ? "스캔 페이지 이미지" : "캡션 없음"), body, actions);
  }

  async function redescribe(f) {
    const types = data.image_types.map((t) => ({ value: t.id, label: t.label }));
    const res = await promptDialog(`그림 다시 해석 — ${f.number ? "Figure " + f.number : f.id}`, [
      { name: "image_type", label: "이미지 유형", type: "select", options: types, value: f.image_type, help: "유형에 따라 프롬프트와 출력 항목(신호, 상태, 치수 등)이 달라집니다. 유형별 프롬프트는 프로필에서 편집합니다." },
      { name: "prompt_extra", label: "이 그림에만 적용할 추가 지침 (선택)", type: "textarea", rows: 4, value: f.prompt_extra || "",
        help: "예: ‘tDQSCK 화살표의 시작과 끝 클록을 명시하라’. 결과가 프롬프트에 그대로 추가됩니다." },
    ], "다시 해석");
    if (!res) return;
    try {
      const job = await api.post(`/api/docs/${doc.id}/figures/redescribe`, { figure_ids: [f.id], image_type: res.image_type, prompt_extra: res.prompt_extra });
      await waitJob(job, "그림 재해석");
    } catch (e) { toast(e.message, "error"); }
  }

  async function writeDescription(f, item) {
    let initial = f.description_override;
    if (!initial && f.description) {
      const d = f.description;
      initial = [d.summary, ...d.sections.filter((s) => s.items.length).map((s) => `\n**${s.title}**\n\n${s.items.map((i) => `- ${i}`).join("\n")}`)].join("\n");
    }
    const res = await promptDialog("그림 설명 직접 작성", [
      { name: "text", label: "설명 (Markdown)", type: "textarea", code: true, rows: 14, value: initial || "", wide: true,
        help: "저장하면 ‘검토된 설명’으로 표시되고 AI 설명 대신 사용됩니다. 다시 해석해도 이 내용은 지워지지 않습니다(직접 ‘AI 설명으로 복귀’ 전까지)." },
    ], "저장");
    if (!res) return;
    try { await api.patch(`/api/docs/${doc.id}/figures/${f.id}`, { description_override: res.text.trim() || null }); toast("저장했습니다.", "ok"); await refreshAll(); }
    catch (e) { toast(e.message, "error"); }
  }

  async function reprocessPage() {
    if (!(await confirmDialog("페이지 다시 처리", `${current}쪽을 현재 프로필로 다시 분석합니다. 같은 위치의 수정 내용은 다시 적용되며, 그림 이미지가 바뀌면 AI 설명을 새로 만듭니다.`, "다시 처리"))) return;
    try {
      const job = await api.post(`/api/docs/${doc.id}/reprocess`, { pages: [current] });
      await waitJob(job, `${current}쪽 재처리`);
    } catch (e) { toast(e.message, "error"); }
  }

  function waitJob(job, label) {
    return new Promise((resolve) => {
      const tick = async () => {
        let j;
        try { j = await api.get(`/api/jobs/${job.id}`); } catch (e) { toast(e.message, "error"); resolve(); return; }
        clear(jobBanner).append(h("div", { class: "panel", style: { marginBottom: "12px" } },
          h("div", { class: "row spread" }, h("strong", null, `${label} 진행 중…`), h("span", null, `${Math.round(j.progress.percent)}%`)), progressBar(j.progress.percent),
          h("div", { class: "small muted" }, j.progress.message || "")));
        if (["done", "failed", "cancelled"].includes(j.status)) {
          clear(jobBanner);
          if (j.status === "done") toast(`${label} 완료`, "ok"); else toast(`${label} 실패: ${j.error}`, "error");
          await refreshAll();
          resolve();
          return;
        }
        jobTimer = setTimeout(tick, 700);
      };
      tick();
    });
  }

  async function refreshAll() {
    pages = await api.get(`/api/docs/${doc.id}/pages`);
    await load(current);
  }

  const keyHandler = (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (document.querySelector(".modal-back")) return;
    if (e.key === "ArrowRight" && current < pages.length) load(current + 1);
    if (e.key === "ArrowLeft" && current > 1) load(current - 1);
  };
  document.addEventListener("keydown", keyHandler);
  await load(current);
  return () => { clearTimeout(jobTimer); document.removeEventListener("keydown", keyHandler); };
}
