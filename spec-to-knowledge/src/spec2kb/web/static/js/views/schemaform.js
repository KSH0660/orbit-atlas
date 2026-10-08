// Generic form renderer for pydantic JSON schemas (labels/help come from the schema titles/descriptions).
import { clear, h } from "../ui.js";

const LONG_KEYS = new Set(["prompt", "system_prompt", "common_instructions", "ocr_prompt", "request_template", "description"]);

export function resolveRef(schema, root) {
  if (!schema) return {};
  if (schema.$ref) {
    const name = schema.$ref.split("/").pop();
    const { $ref, ...rest } = schema;
    return { ...resolveRef(root.$defs[name], root), ...rest };
  }
  if (schema.allOf && schema.allOf.length === 1) {
    const { allOf, ...rest } = schema;
    return { ...resolveRef(allOf[0], root), ...rest };
  }
  if (schema.anyOf) {
    const nonNull = schema.anyOf.filter((s) => s.type !== "null");
    if (nonNull.length === 1) {
      const { anyOf, ...rest } = schema;
      return { ...resolveRef(nonNull[0], root), ...rest, nullable: true };
    }
  }
  return schema;
}

export function getAt(obj, path) {
  return path.reduce((o, k) => (o === undefined || o === null ? undefined : o[k]), obj);
}

export function setAt(obj, path, value) {
  let o = obj;
  path.slice(0, -1).forEach((k) => { if (o[k] === undefined || o[k] === null) o[k] = {}; o = o[k]; });
  o[path[path.length - 1]] = value;
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function fmtInherited(v) {
  if (v === undefined) return "(없음)";
  if (typeof v === "string") return v.length > 60 ? `"${v.slice(0, 60)}…"` : `"${v}"`;
  const s = JSON.stringify(v);
  return s.length > 70 ? s.slice(0, 70) + "…" : s;
}

/**
 * Render fields for an object schema.
 * ctx: { root (schema), value (working copy root), parent (inherited root or null), readOnly, onChange() }
 */
export function renderObject(container, schema, path, ctx, depth = 0) {
  const s = resolveRef(schema, ctx.root);
  const props = s.properties || {};
  const simple = [];
  const nested = [];
  for (const [key, raw] of Object.entries(props)) {
    const ps = resolveRef(raw, ctx.root);
    if (ps.type === "object" && ps.properties) nested.push([key, ps]);
    else simple.push([key, ps]);
  }
  for (const [key, ps] of simple) container.appendChild(renderField(key, ps, [...path, key], ctx));
  for (const [key, ps] of nested) {
    const group = h("div", { class: "subgroup" }, h("h4", null, ps.title || key));
    if (ps.description) group.appendChild(h("div", { class: "help" }, ps.description));
    renderObject(group, ps, [...path, key], ctx, depth + 1);
    container.appendChild(group);
  }
}

export function renderField(key, ps, path, ctx) {
  const wrap = h("div", { class: "cfg-field", "data-path": path.join(".") });
  const label = h("div", null, h("div", { class: "flabel" }, ps.title || key), ps.description ? h("div", { class: "help" }, ps.description) : null);
  const ctl = h("div", { class: "fctl" });
  const info = h("div");
  wrap.append(label, ctl);
  ctl.appendChild(info);
  let widgetEl = null;
  // Only the override indicator is refreshed on edits: re-creating the input while it is
  // dispatching change/blur events breaks focus handling in the browser.
  const refresh = () => {
    const value = getAt(ctx.value, path);
    const inherited = ctx.parent ? getAt(ctx.parent, path) : undefined;
    const overridden = ctx.parent && !same(value, inherited);
    wrap.classList.toggle("overridden", !!overridden);
    clear(info);
    if (overridden) {
      info.appendChild(h("div", { class: "inherit" }, `상속값: ${fmtInherited(inherited)}`,
        ctx.readOnly ? null : h("button", { class: "small ghost", type: "button", onclick: () => {
          setAt(ctx.value, path, structuredClone(inherited)); ctx.onChange(); drawWidget(); refresh();
        } }, "상속값으로 되돌리기")));
    }
  };
  const drawWidget = () => {
    if (widgetEl) widgetEl.remove();
    widgetEl = widget(key, ps, getAt(ctx.value, path), (v) => { setAt(ctx.value, path, v); ctx.onChange(); refresh(); }, ctx.readOnly);
    ctl.insertBefore(widgetEl, info);
  };
  drawWidget();
  refresh();
  return wrap;
}

function widget(key, ps, value, set, readOnly) {
  const dis = readOnly ? { disabled: true } : {};
  if (ps.enum) {
    return h("select", { ...dis, onchange: (e) => set(typeof ps.enum[0] === "number" ? Number(e.target.value) : e.target.value) },
      ps.enum.map((v) => h("option", { value: String(v), selected: String(v) === String(value) }, String(v))));
  }
  if (ps.type === "boolean") {
    const text = h("span", null, value ? "사용" : "사용 안 함");
    return h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!value, ...dis, onchange: (e) => {
      text.textContent = e.target.checked ? "사용" : "사용 안 함"; set(e.target.checked);
    } }), text);
  }
  if (ps.type === "integer" || ps.type === "number") {
    return h("input", { type: "number", value: value ?? "", step: ps.type === "integer" ? 1 : "any", min: ps.minimum, max: ps.maximum, ...dis,
      style: { maxWidth: "180px" }, onchange: (e) => {
        if (e.target.value === "") return;
        const v = ps.type === "integer" ? parseInt(e.target.value, 10) : parseFloat(e.target.value);
        if (!Number.isNaN(v)) set(v);
      } });
  }
  if (ps.type === "array" && (!ps.items || resolveItems(ps).type === "string")) {
    return h("textarea", { class: "code", rows: Math.min(10, Math.max(3, (value || []).length + 1)), ...dis,
      placeholder: "한 줄에 하나씩", onchange: (e) => set(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean)) }, (value || []).join("\n"));
  }
  if (ps.type === "object" && ps.additionalProperties !== undefined) {
    const ta = h("textarea", { class: "code", rows: 4, ...dis, placeholder: '{"key": "value"}' }, JSON.stringify(value || {}, null, 2));
    ta.addEventListener("change", () => {
      try { set(JSON.parse(ta.value || "{}")); ta.style.borderColor = ""; }
      catch { ta.style.borderColor = "var(--err)"; }
    });
    return ta;
  }
  const isCode = /pattern|regex|template/.test(key);
  if (LONG_KEYS.has(key) || (typeof value === "string" && (value.includes("\n") || value.length > 90))) {
    return h("textarea", { class: isCode ? "code" : "", rows: Math.min(16, Math.max(3, String(value || "").split("\n").length + 1)), ...dis,
      onchange: (e) => set(e.target.value) }, value ?? "");
  }
  return h("input", { type: "text", value: value ?? "", class: isCode ? "code" : "", ...dis,
    style: isCode ? { fontFamily: "var(--mono)", fontSize: "12.5px" } : null,
    onchange: (e) => set(ps.nullable && e.target.value === "" ? null : e.target.value) });
}

function resolveItems(ps) {
  return ps.items || {};
}
