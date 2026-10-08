// Small DOM helpers (no framework, no build step).

// Views pass arrays and conditional (null/false) children to Element.append; make that safe
// app-wide instead of rendering "null" or "[object HTMLElement],..." text.
const nativeAppend = Element.prototype.append;
Element.prototype.append = function appendFlat(...nodes) {
  return nativeAppend.apply(this, nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
};

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === "html") el.innerHTML = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function toast(message, kind = "") {
  const root = document.getElementById("toasts");
  const t = h("div", { class: `toast ${kind}`, role: "status" }, message);
  root.appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 8000 : 3500);
}

export function modal({ title, body, actions = [], wide = false, onClose }) {
  const root = document.getElementById("modal-root");
  const close = () => { back.remove(); document.removeEventListener("keydown", esc); onClose && onClose(); };
  const esc = (e) => { if (e.key === "Escape") close(); };
  const footer = h("footer", null, actions.map((a) => h("button", {
    class: a.class || "", onclick: async (e) => {
      if (a.onClick) {
        e.target.disabled = true;
        try { const keep = await a.onClick(close); if (keep !== false) close(); }
        catch (err) { toast(err.message || String(err), "error"); }
        finally { e.target.disabled = false; }
      } else close();
    },
  }, a.label)));
  const box = h("div", { class: `modal ${wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true" },
    h("header", null, h("h2", null, title), h("button", { class: "ghost", onclick: close, "aria-label": "닫기" }, "✕")),
    h("div", { class: "mbody" }, body), footer);
  const back = h("div", { class: "modal-back", onclick: (e) => { if (e.target === back) close(); } }, box);
  root.appendChild(back);
  document.addEventListener("keydown", esc);
  const first = box.querySelector("input, textarea, select");
  if (first) setTimeout(() => first.focus(), 30);
  return { close, box };
}

export function confirmDialog(title, message, okLabel = "확인", danger = false) {
  return new Promise((resolve) => {
    let done = false;
    modal({
      title, body: h("p", null, message),
      actions: [
        { label: "취소", onClick: () => { done = true; resolve(false); } },
        { label: okLabel, class: danger ? "danger" : "primary", onClick: () => { done = true; resolve(true); } },
      ],
      onClose: () => { if (!done) resolve(false); },
    });
  });
}

export function promptDialog(title, fields, okLabel = "확인") {
  // fields: [{name, label, value, help, type: text|textarea|select, options:[{value,label}]}]
  return new Promise((resolve) => {
    let done = false;
    const inputs = {};
    const body = h("div", { class: "stack" }, fields.map((f) => {
      let input;
      if (f.type === "select") {
        input = h("select", null, f.options.map((o) => h("option", { value: o.value, selected: o.value === f.value }, o.label)));
      } else if (f.type === "textarea") {
        input = h("textarea", { class: f.code ? "code" : "", rows: f.rows || 6 }, f.value || "");
      } else {
        input = h("input", { type: "text", value: f.value || "", placeholder: f.placeholder || "" });
      }
      inputs[f.name] = input;
      return h("label", { class: "field" }, h("span", { class: "label" }, f.label), input, f.help ? h("span", { class: "help" }, f.help) : null);
    }));
    modal({
      title, body, wide: fields.some((f) => f.wide),
      actions: [
        { label: "취소", onClick: () => { done = true; resolve(null); } },
        { label: okLabel, class: "primary", onClick: () => {
          done = true;
          const out = {};
          for (const [k, el] of Object.entries(inputs)) out[k] = el.value;
          resolve(out);
        } },
      ],
      onClose: () => { if (!done) resolve(null); },
    });
  });
}

export const STATUS_LABEL = {
  uploaded: "업로드됨", queued: "대기 중", processing: "처리 중", ready: "완료", failed: "실패", cancelled: "취소됨",
  running: "실행 중", done: "완료",
};

export function statusBadge(status) {
  const cls = { ready: "ok", done: "ok", failed: "err", cancelled: "warn", processing: "processing", queued: "queued", running: "processing" }[status] || "";
  return h("span", { class: `badge ${cls}` }, STATUS_LABEL[status] || status);
}

export const SEV_LABEL = { error: "오류", warning: "경고", info: "정보" };
export function sevBadge(sev) {
  return h("span", { class: `badge ${sev}` }, SEV_LABEL[sev] || sev);
}

export const BLOCK_LABEL = { heading: "제목", paragraph: "문단", list_item: "목록", note: "NOTE", table: "표", figure: "그림" };

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function fmtBytes(n) {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function progressBar(percent, big = false) {
  return h("div", { class: `progress ${big ? "big" : ""}`, role: "progressbar", "aria-valuenow": Math.round(percent || 0), "aria-valuemin": 0, "aria-valuemax": 100 },
    h("div", { style: { width: `${Math.max(0, Math.min(100, percent || 0))}%` } }));
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function field(label, control, help) {
  return h("label", { class: "field" }, h("span", { class: "label" }, label), control, help ? h("span", { class: "help" }, help) : null);
}
