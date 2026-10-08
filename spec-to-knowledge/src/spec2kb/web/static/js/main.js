// Hash router and app shell.
import { api } from "./api.js";
import { clear, h } from "./ui.js";
import { renderDocuments } from "./views/documents.js";
import { renderDocument } from "./views/document.js";
import { renderProfiles, renderProfileEditor } from "./views/profiles.js";
import { renderProviders } from "./views/providers.js";
import { renderHelp } from "./views/help.js";

const app = document.getElementById("app");
let cleanup = null;

const routes = [
  [/^#\/docs\/?$/, (m) => renderDocuments(app), "docs"],
  [/^#\/doc\/([a-z0-9]+)(?:\/([a-z]+))?(?:\/(\d+))?$/, (m) => renderDocument(app, m[1], m[2] || "", m[3] ? Number(m[3]) : null), "docs"],
  [/^#\/profiles\/?$/, () => renderProfiles(app), "profiles"],
  [/^#\/profile\/([a-z0-9_\-]+)$/, (m) => renderProfileEditor(app, m[1]), "profiles"],
  [/^#\/providers\/?$/, () => renderProviders(app), "providers"],
  [/^#\/help\/?$/, () => renderHelp(app), "help"],
];

async function route() {
  const hash = location.hash || "#/docs";
  if (typeof cleanup === "function") { try { cleanup(); } catch { /* ignore */ } }
  cleanup = null;
  for (const [re, fn, nav] of routes) {
    const m = hash.match(re);
    if (m) {
      document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));
      clear(app);
      try {
        cleanup = await fn(m);
      } catch (e) {
        clear(app);
        app.appendChild(h("div", { class: "panel" }, h("h2", null, "화면을 표시할 수 없습니다"), h("p", null, e.message || String(e)),
          h("a", { href: "#/docs" }, "문서 목록으로")));
      }
      return;
    }
  }
  location.hash = "#/docs";
}

async function pollHealth() {
  const el = document.getElementById("server-status");
  try {
    const hres = await api.get("/api/health");
    el.className = "server-status";
    el.replaceChildren(h("span", { class: "dot" }), `서버 정상 · v${hres.version}`);
    el.title = `데이터 폴더: ${hres.data_dir}\n기본 Provider: ${hres.default_provider}`;
  } catch {
    el.className = "server-status down";
    el.replaceChildren(h("span", { class: "dot" }), "서버 연결 끊김");
  }
}

window.addEventListener("hashchange", route);
route();
pollHealth();
setInterval(pollHealth, 15000);
