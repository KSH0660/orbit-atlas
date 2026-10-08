// Profiles: list, create (inherit / clone / flatten), import/export, and the settings editor.
import { api, downloadFrom } from "../api.js";
import { clear, confirmDialog, fmtTime, h, modal, promptDialog, toast } from "../ui.js";
import { getAt, renderField, renderObject, resolveRef } from "./schemaform.js";

const SECTIONS = [
  ["parsing", "파싱 규칙", "머리글/바닥글 제거, 목차, 제목·문단·표·그림 인식 규칙"],
  ["vision", "AI 그림 해석", "Vision 모델, 공통 프롬프트, 이미지 유형별 해석 규칙"],
  ["markdown", "Markdown 출력 규칙", "파일 분할, Frontmatter, 표/그림 표기 방식, 고정 문구"],
  ["validation", "검증 기준", "보존해야 할 단위·신호명·식별자 패턴과 경고 기준"],
];

export async function renderProfiles(root) {
  const list = h("div");
  const head = h("div", { class: "page-head" },
    h("div", null, h("h1", null, "프로필"),
      h("p", null, "문서 종류별 변환 규칙 묶음입니다. 기본 제공 프로필(General, JEDEC, Customer)을 상속하거나 복제해서 팀/고객별 규칙을 만드세요. 상속한 프로필은 바꾼 항목만 저장되므로 부모 프로필 개선이 자동으로 반영됩니다.")),
    h("div", { class: "row" },
      h("button", { onclick: importProfile }, "가져오기 (JSON)"),
      h("button", { class: "primary", "data-testid": "new-profile", onclick: () => createDialog() }, "새 프로필")));
  root.append(head, h("section", { class: "panel" }, list));

  async function load() {
    const profiles = await api.get("/api/profiles");
    clear(list).appendChild(h("table", { class: "list", "data-testid": "profile-table" },
      h("thead", null, h("tr", null, h("th", null, "이름"), h("th", null, "상속 관계"), h("th", null, "변경 항목"), h("th", null, "수정"), h("th", null, ""))),
      h("tbody", null, profiles.map((p) => h("tr", { "data-profile": p.id },
        h("td", null, h("a", { href: `#/profile/${p.id}` }, h("strong", null, p.name)), " ", p.builtin ? h("span", { class: "badge info" }, "기본 제공") : null,
          h("div", { class: "small muted" }, p.id), p.error ? h("div", { class: "small", style: { color: "var(--err)" } }, p.error) : null,
          h("div", { class: "small muted" }, (p.description || "").slice(0, 140))),
        h("td", null, chain(p.chain || [p.id])),
        h("td", { class: "small" }, p.builtin ? "—" : `${p.override_count}개`),
        h("td", { class: "small muted nowrap" }, fmtTime(p.updated_at)),
        h("td", { class: "nowrap" },
          h("a", { class: "btn small", href: `#/profile/${p.id}` }, p.builtin ? "보기" : "편집"), " ",
          h("button", { class: "small", onclick: () => createDialog(p.id, "inherit") }, "상속"), " ",
          h("button", { class: "small", onclick: () => createDialog(p.id, "clone") }, "복제"), " ",
          h("button", { class: "small", onclick: () => downloadFrom("GET", `/api/profiles/${p.id}/export`, undefined, `profile-${p.id}.json`).catch((e) => toast(e.message, "error")) }, "내보내기"), " ",
          p.builtin ? null : h("button", { class: "small danger", onclick: async () => {
            if (!(await confirmDialog("프로필 삭제", `'${p.name}' 프로필을 삭제합니다.`, "삭제", true))) return;
            try { await api.del(`/api/profiles/${p.id}`); toast("삭제했습니다.", "ok"); load(); } catch (e) { toast(e.message, "error"); }
          } }, "삭제")))))));
  }

  async function createDialog(baseId = "jedec", mode = "inherit") {
    const profiles = await api.get("/api/profiles");
    const res = await promptDialog("새 프로필 만들기", [
      { name: "base_id", label: "기준 프로필", type: "select", value: baseId, options: profiles.map((p) => ({ value: p.id, label: `${p.name} (${p.id})` })) },
      { name: "mode", label: "만드는 방식", type: "select", value: mode, options: [
        { value: "inherit", label: "상속 — 바꾼 항목만 저장, 부모 변경이 자동 반영 (권장)" },
        { value: "clone", label: "복제 — 기준 프로필의 변경 항목과 부모를 그대로 복사" },
        { value: "flatten", label: "독립 사본 — 현재 최종 설정 전체를 복사, 부모 없음" }] },
      { name: "id", label: "프로필 ID", placeholder: "예: jedec-ddr5 (영문 소문자, 숫자, -, _)", help: "파일 이름과 API에서 쓰이는 고유 ID입니다." },
      { name: "name", label: "표시 이름", placeholder: "예: JEDEC DDR5 팀 규칙" },
      { name: "description", label: "설명", type: "textarea", rows: 3 },
    ], "만들기");
    if (!res) return;
    try {
      const p = await api.post("/api/profiles", res);
      toast("프로필을 만들었습니다.", "ok");
      location.hash = `#/profile/${p.id}`;
    } catch (e) { toast(e.message, "error"); }
  }

  function importProfile() {
    const input = h("input", { type: "file", accept: "application/json,.json" });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        await api.post("/api/profiles-import", { profile: data, overwrite: false });
        toast(`프로필 '${data.id}'을(를) 가져왔습니다.`, "ok");
        load();
      } catch (e) { toast(`가져오기 실패: ${e.message}`, "error"); }
    });
    input.click();
  }

  await load();
}

function chain(ids) {
  return h("span", { class: "chain" }, ids.map((id, i) => [i ? h("span", { class: "arrow" }, "←") : null, h("span", { class: "badge" }, id)]));
}

let schemaCache = null;

export async function renderProfileEditor(root, pid) {
  const [data, schema, profiles] = await Promise.all([api.get(`/api/profiles/${pid}`), schemaCache || api.get("/api/profiles-schema"), api.get("/api/profiles")]);
  schemaCache = schema;
  const raw = data.raw;
  const readOnly = !!raw.builtin;
  const value = {};
  for (const [k] of SECTIONS) value[k] = structuredClone(data.resolved[k]);
  const parent = raw.extends ? data.parent_resolved : null;
  let dirty = false;
  const saveBtn = h("button", { class: "primary", disabled: true, "data-testid": "save-profile", onclick: save }, "저장");
  const dirtyMark = h("span", { class: "small muted" });
  const ctx = { root: schema, value, parent, readOnly, onChange: () => { dirty = true; saveBtn.disabled = readOnly; dirtyMark.textContent = "저장하지 않은 변경 사항이 있습니다"; } };

  const nameIn = h("input", { type: "text", value: raw.name || "", disabled: readOnly, oninput: ctx.onChange });
  const descIn = h("textarea", { rows: 2, disabled: readOnly, oninput: ctx.onChange }, raw.description || "");
  const descendants = new Set(profiles.filter((p) => (p.chain || []).includes(pid)).map((p) => p.id));
  const extSel = h("select", { disabled: readOnly, onchange: ctx.onChange },
    h("option", { value: "" }, "(상속 없음 — 기본값에서 시작)"),
    profiles.filter((p) => !descendants.has(p.id)).map((p) => h("option", { value: p.id, selected: p.id === raw.extends }, `${p.name} (${p.id})`)));

  const head = h("div", { class: "page-head" },
    h("div", { class: "grow" }, h("div", { class: "small" }, h("a", { href: "#/profiles" }, "← 프로필 목록")),
      h("h1", null, raw.name, " ", readOnly ? h("span", { class: "badge info" }, "기본 제공 · 읽기 전용") : null),
      h("div", { class: "row" }, h("span", { class: "small muted" }, "상속 관계:"), chain(data.chain))),
    h("div", { class: "row" }, dirtyMark, readOnly ? h("button", { class: "primary", onclick: () => cloneFromBuiltin() }, "상속하여 편집용 프로필 만들기") : saveBtn));

  const meta = h("section", { class: "panel" }, h("div", { class: "form-grid" },
    h("label", { class: "field" }, h("span", { class: "label" }, "표시 이름"), nameIn),
    h("label", { class: "field" }, h("span", { class: "label" }, "부모 프로필 (상속)"), extSel,
      h("span", { class: "help" }, "부모의 설정을 물려받고, 이 프로필에서 바꾼 항목만 덮어씁니다. ● 표시 = 이 프로필에서 바꾼 항목")),
    h("label", { class: "field", style: { gridColumn: "1 / -1" } }, h("span", { class: "label" }, "설명"), descIn)));

  const tabs = h("div", { class: "segmented", style: { margin: "10px 0" } });
  const body = h("div");
  const views = { form: "설정 편집", overrides: "변경 항목(JSON)", resolved: "최종 설정(JSON)" };
  let currentView = "form";
  for (const [k, label] of Object.entries(views)) {
    tabs.appendChild(h("button", { class: k === "form" ? "active" : "", onclick: (e) => {
      currentView = k; tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === e.target)); draw();
    } }, label));
  }

  function draw() {
    clear(body);
    if (currentView === "form") {
      for (const [key, title, desc] of SECTIONS) {
        const sec = h("details", { class: "cfg-section", open: key === "parsing" }, h("summary", null, title, h("span", { class: "small muted" }, desc)));
        const inner = h("div", { class: "cfg-body" });
        const sch = resolveRef(schema.properties[key], schema);
        if (key === "vision") {
          const props = { ...sch.properties };
          delete props.image_types;
          renderObject(inner, { ...sch, properties: props }, [key], ctx);
          inner.appendChild(imageTypesEditor(ctx, schema));
        } else {
          renderObject(inner, sch, [key], ctx);
        }
        sec.appendChild(inner);
        body.appendChild(sec);
      }
    } else if (currentView === "overrides") {
      body.appendChild(h("div", { class: "panel" }, h("p", { class: "help" }, "부모 프로필 대비 이 프로필에 저장된 변경 항목입니다 (저장 후 기준)."),
        h("pre", { class: "rawmd" }, JSON.stringify(raw.overrides || {}, null, 2))));
    } else {
      body.appendChild(h("div", { class: "panel" }, h("pre", { class: "rawmd" }, JSON.stringify(data.resolved, null, 2))));
    }
  }

  async function save() {
    saveBtn.disabled = true;
    try {
      await api.put(`/api/profiles/${pid}`, { name: nameIn.value, description: descIn.value, extends: extSel.value || null, resolved: value });
      dirty = false;
      toast("프로필을 저장했습니다. 이 프로필을 쓰는 문서는 ‘다시 변환’ 시 반영됩니다.", "ok");
      clear(root);
      await renderProfileEditor(root, pid);
    } catch (e) { toast(e.message, "error"); saveBtn.disabled = false; }
  }

  async function cloneFromBuiltin() {
    const res = await promptDialog(`'${raw.name}'을(를) 상속한 프로필 만들기`, [
      { name: "id", label: "새 프로필 ID", value: `${pid}-custom`, help: "영문 소문자, 숫자, -, _" },
      { name: "name", label: "표시 이름", value: `${raw.name} (사용자)` },
    ], "만들기");
    if (!res) return;
    try { const p = await api.post("/api/profiles", { ...res, base_id: pid, mode: "inherit" }); location.hash = `#/profile/${p.id}`; }
    catch (e) { toast(e.message, "error"); }
  }

  const beforeUnload = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
  window.addEventListener("beforeunload", beforeUnload);
  root.append(head, meta, tabs, body);
  draw();
  return () => window.removeEventListener("beforeunload", beforeUnload);
}

function imageTypesEditor(ctx, schema) {
  const box = h("div", { class: "subgroup" }, h("h4", null, "이미지 유형별 해석 규칙"),
    h("div", { class: "help" }, "그림은 캡션/내부 텍스트 정규식으로 유형이 정해지고, 유형별 지침과 출력 항목으로 프롬프트가 만들어집니다. 캡션이 일치하는 규칙이 텍스트만 일치하는 규칙보다 우선하며, 같은 그룹 안에서는 우선순위가 높은 규칙이 이깁니다."));
  const list = h("div");
  const ruleSchema = resolveRef(schema.$defs.ImageTypeRule, schema);
  const draw = () => {
    clear(list);
    const rules = getAt(ctx.value, ["vision", "image_types"]) || [];
    const parentRules = ctx.parent ? (getAt(ctx.parent, ["vision", "image_types"]) || []) : [];
    rules.forEach((r, idx) => {
      const pr = parentRules.find((x) => x.id === r.id);
      const changed = ctx.parent && JSON.stringify(pr) !== JSON.stringify(r);
      const card = h("details", { class: "rule-card", "data-rule": r.id },
        h("summary", null, h("strong", null, r.label || r.id), h("span", { class: "badge" }, r.id), h("span", { class: "small muted" }, `우선순위 ${r.priority}`),
          r.enabled ? null : h("span", { class: "badge warn" }, "꺼짐"), changed ? h("span", { class: "badge edited" }, pr ? "변경됨" : "추가됨") : null));
      const inner = h("div", { class: "cfg-body" });
      for (const [key, ps0] of Object.entries(ruleSchema.properties)) {
        if (key === "sections") continue;
        const ps = resolveRef(ps0, schema);
        const f = renderField(key, ps, ["vision", "image_types", idx, key], { ...ctx, parent: ctx.parent && pr ? { vision: { image_types: Object.assign([], { [idx]: pr }) } } : null,
          onChange: () => { ctx.onChange(); } });
        if (key === "id" && pr) f.querySelectorAll("input").forEach((i) => { i.disabled = true; });
        inner.appendChild(f);
      }
      const secTa = h("textarea", { class: "code", rows: Math.max(3, (r.sections || []).length + 1), disabled: ctx.readOnly,
        onchange: (e) => {
          r.sections = e.target.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
            const [key, ...rest] = l.split(":");
            return { key: key.trim().replace(/[^A-Za-z0-9_]/g, "_"), title: (rest.join(":").trim() || key.trim()) };
          });
          ctx.onChange();
        } }, (r.sections || []).map((s) => `${s.key}: ${s.title}`).join("\n"));
      inner.appendChild(h("div", { class: "cfg-field" }, h("div", null, h("div", { class: "flabel" }, "출력 항목"),
        h("div", { class: "help" }, "한 줄에 ‘키: Markdown 제목’. 모델은 summary, 이 키들, uncertain을 가진 JSON으로 답하도록 요청받습니다.")), h("div", { class: "fctl" }, secTa)));
      if (!ctx.readOnly) {
        inner.appendChild(h("div", { class: "row", style: { marginTop: "8px" } },
          h("button", { class: "small danger", type: "button", onclick: () => {
            rules.splice(idx, 1); ctx.onChange(); draw();
          } }, pr ? "이 프로필에서 제거" : "삭제")));
      }
      card.appendChild(inner);
      list.appendChild(card);
    });
  };
  const addBtn = ctx.readOnly ? null : h("button", { class: "small", type: "button", onclick: async () => {
    const res = await promptDialog("이미지 유형 추가", [
      { name: "id", label: "유형 ID", placeholder: "예: mode_register", help: "영문 소문자/숫자/_" },
      { name: "label", label: "표시 이름", placeholder: "예: Mode register diagram" },
    ], "추가");
    if (!res || !res.id) return;
    const rules = getAt(ctx.value, ["vision", "image_types"]);
    if (rules.some((r) => r.id === res.id)) { toast("이미 있는 ID입니다.", "error"); return; }
    rules.push({ id: res.id.trim(), label: res.label || res.id, enabled: true, priority: 30, caption_regex: "", text_regex: "", min_text_hits: 1,
      prompt: "Describe the figure.", sections: [{ key: "elements", title: "Elements" }, { key: "notes", title: "Notes" }] });
    ctx.onChange();
    draw();
  } }, "+ 유형 추가");
  box.append(list, addBtn);
  draw();
  return box;
}

export { modal };
