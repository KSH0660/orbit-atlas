// Model / API providers: register in-house LLM / Vision / OCR endpoints and test them.
import { api } from "../api.js";
import { clear, confirmDialog, h, modal, toast } from "../ui.js";

const TYPE_LABEL = { openai: "OpenAI 호환", custom_http: "Custom HTTP", mock: "Mock (오프라인)" };

const GROUPS = [
  ["기본 정보", ["id", "name", "type", "description"], null],
  ["연결", ["base_url", "endpoint_path", "model", "timeout_s", "max_retries", "verify_ssl", "ca_bundle"], null],
  ["인증", ["api_key_env", "api_key", "auth_header", "auth_scheme"], ["openai", "custom_http"]],
  ["요청 옵션", ["supports_vision", "image_detail", "headers", "extra_body"], null],
  ["Custom HTTP 형식", ["request_format", "request_template", "file_field", "response_path"], ["custom_http"]],
];

const EXAMPLE_TEMPLATE = JSON.stringify({ model: "{{model}}", prompt: "{{prompt}}", image: "{{image_base64}}", max_tokens: "{{max_tokens}}" }, null, 2);

export async function renderProviders(root) {
  const list = h("div");
  root.append(
    h("div", { class: "page-head" }, h("div", null, h("h1", null, "모델 / API 설정"),
      h("p", null, "사내 LLM·Vision·OCR 모델 API를 등록합니다. OpenAI 호환 API(vLLM, TGI, LiteLLM, 사내 게이트웨이)는 Base URL과 모델명만 넣으면 되고, 형식이 다른 API는 ‘Custom HTTP’로 요청 템플릿과 응답 경로를 지정합니다. 프로필(또는 문서 설정)에서 어떤 Provider를 쓸지 고릅니다.")),
      h("button", { class: "primary", "data-testid": "new-provider", onclick: () => edit(null) }, "Provider 추가")),
    h("section", { class: "panel" }, list),
    h("section", { class: "panel" }, h("h2", null, "연결 팁"), h("ul", null,
      h("li", null, "API Key는 가능하면 ", h("b", null, "환경변수 이름"), "으로 지정하세요 (예: INTERNAL_LLM_KEY). 서버 시작 전에 export 해 두면 설정 파일에 키가 남지 않습니다."),
      h("li", null, "사내 인증서를 쓰는 HTTPS 엔드포인트는 ‘CA 번들 경로’ 또는 서버 환경변수 S2K_CA_BUNDLE을 지정하세요."),
      h("li", null, "외부망 검증: ", h("code", null, "spec2kb mock-server --port 9100"), " 실행 후 Base URL ", h("code", null, "http://127.0.0.1:9100/v1"), "로 OpenAI 호환 Provider를 만들면 실제 HTTP 경로까지 시험할 수 있습니다."),
      h("li", null, "‘연결 테스트’는 작은 이미지와 함께 짧은 요청을 보내 응답 시간과 형식을 확인합니다."))));

  async function load() {
    const items = await api.get("/api/providers");
    clear(list).appendChild(h("table", { class: "list", "data-testid": "provider-table" },
      h("thead", null, h("tr", null, h("th", null, "이름"), h("th", null, "유형"), h("th", null, "엔드포인트 / 모델"), h("th", null, "인증"), h("th", null, ""))),
      h("tbody", null, items.map((p) => h("tr", { "data-provider": p.id },
        h("td", null, h("strong", null, p.name), " ", p.builtin ? h("span", { class: "badge info" }, "기본") : null, h("div", { class: "small muted" }, p.id)),
        h("td", null, h("span", { class: "badge" }, TYPE_LABEL[p.type] || p.type)),
        h("td", { class: "small" }, p.base_url ? h("code", null, p.base_url + (p.endpoint_path || "")) : "—", h("div", { class: "muted" }, p.model)),
        h("td", { class: "small" }, p.api_key_env ? h("span", { class: `badge ${p.api_key_env_present ? "ok" : "warn"}` }, `env ${p.api_key_env}${p.api_key_env_present ? "" : " (없음)"}`)
          : p.api_key_set ? h("span", { class: "badge" }, "저장된 키") : h("span", { class: "muted" }, "없음")),
        h("td", { class: "nowrap" },
          h("button", { class: "small", "data-testid": "test-provider", onclick: (e) => test(p, e.target) }, "연결 테스트"), " ",
          p.builtin ? null : h("button", { class: "small", onclick: () => edit(p) }, "편집"), " ",
          p.builtin ? null : h("button", { class: "small danger", onclick: async () => {
            if (!(await confirmDialog("Provider 삭제", `'${p.name}'을(를) 삭제합니다. 이 Provider를 쓰는 프로필은 기본 Provider로 대체되지 않으니 프로필도 확인하세요.`, "삭제", true))) return;
            try { await api.del(`/api/providers/${p.id}`); load(); } catch (err) { toast(err.message, "error"); }
          } }, "삭제")))))));
  }

  async function test(p, btn) {
    btn.disabled = true;
    btn.textContent = "테스트 중…";
    try {
      const r = await api.post(`/api/providers/${p.id}/test`);
      if (r.ok) toast(`✓ ${p.name}: 응답 "${r.reply}" · ${r.latency_ms} ms${r.image_sent ? " · 이미지 포함" : ""}`, "ok");
      else toast(`✗ ${p.name}: ${r.error}`, "error");
    } catch (e) { toast(e.message, "error"); }
    finally { btn.disabled = false; btn.textContent = "연결 테스트"; }
  }

  async function edit(existing) {
    const schema = await api.get("/api/providers-schema");
    const props = schema.properties;
    const v = existing ? structuredClone(existing) : { id: "", name: "", type: "openai", base_url: "", model: "", timeout_s: 120, max_retries: 2,
      verify_ssl: true, supports_vision: true, auth_header: "Authorization", auth_scheme: "Bearer", headers: {}, extra_body: {}, request_format: "json",
      request_template: "", file_field: "file", response_path: "", api_key: "", api_key_env: "", ca_bundle: "", image_detail: "", endpoint_path: "", description: "" };
    const inputs = {};
    const body = h("div", { class: "stack" });
    const draw = () => {
      clear(body);
      body.appendChild(h("div", { class: "row" }, h("span", { class: "small muted" }, "빠른 설정:"),
        h("button", { class: "small", type: "button", onclick: () => { Object.assign(v, collect(), { type: "openai", base_url: "http://127.0.0.1:9100/v1", model: "mock-vision-1" }); draw(); } }, "로컬 Mock 서버"),
        h("button", { class: "small", type: "button", onclick: () => { Object.assign(v, collect(), { type: "openai", base_url: "http://llm-gateway.example.local:8000/v1", model: "Qwen2.5-VL-72B-Instruct" }); draw(); } }, "vLLM 예시"),
        h("button", { class: "small", type: "button", onclick: () => { Object.assign(v, collect(), { type: "custom_http", endpoint_path: "/ocr", request_template: EXAMPLE_TEMPLATE, response_path: "result.text" }); draw(); } }, "Custom OCR 예시")));
      for (const [title, keys, types] of GROUPS) {
        if (types && !types.includes(v.type)) continue;
        const grid = h("div", { class: "form-grid" });
        for (const k of keys) {
          const ps = props[k] || {};
          if (k === "image_detail" && v.type !== "openai") continue;
          grid.appendChild(fieldFor(k, ps, v[k]));
        }
        body.append(h("h3", { style: { marginTop: "6px" } }, title), grid);
      }
    };
    function fieldFor(k, ps, value) {
      let input;
      const enumVals = ps.enum || (ps.anyOf && ps.anyOf.find((x) => x.enum)?.enum);
      if (k === "type") {
        input = h("select", { onchange: (e) => { Object.assign(v, collect(), { type: e.target.value }); draw(); } },
          Object.entries(TYPE_LABEL).map(([t, l]) => h("option", { value: t, selected: t === value }, l)));
      } else if (enumVals) {
        input = h("select", null, enumVals.map((x) => h("option", { value: x, selected: x === value }, x)));
      } else if (ps.type === "boolean") {
        input = h("input", { type: "checkbox", checked: !!value });
      } else if (k === "headers" || k === "extra_body" || k === "request_template") {
        input = h("textarea", { class: "code", rows: k === "request_template" ? 8 : 3 }, k === "request_template" ? (value || "") : JSON.stringify(value || {}, null, 2));
      } else if (ps.type === "number" || ps.type === "integer") {
        input = h("input", { type: "number", value: value ?? "", step: ps.type === "integer" ? 1 : "any" });
      } else if (k === "api_key") {
        input = h("input", { type: "password", value: "", autocomplete: "new-password", placeholder: existing && existing.api_key_set ? "저장된 키 유지 (변경할 때만 입력)" : "" });
      } else {
        input = h("input", { type: "text", value: value ?? "", disabled: k === "id" && !!existing });
      }
      inputs[k] = input;
      const wide = ["request_template", "headers", "extra_body", "description"].includes(k);
      return h("label", { class: "field", style: wide ? { gridColumn: "1 / -1" } : null },
        h("span", { class: "label" }, ps.title || k), ps.type === "boolean" ? h("span", { class: "check" }, input, "사용") : input,
        ps.description ? h("span", { class: "help" }, ps.description) : null);
    }
    function collect() {
      const out = {};
      for (const [k, el] of Object.entries(inputs)) {
        if (!el.isConnected) continue;
        if (el.type === "checkbox") out[k] = el.checked;
        else if (k === "headers" || k === "extra_body") {
          try { out[k] = JSON.parse(el.value || "{}"); } catch { throw new Error(`${k}: JSON 형식이 아닙니다.`); }
        } else if (el.type === "number") out[k] = Number(el.value);
        else out[k] = el.value;
      }
      return out;
    }
    draw();
    modal({
      title: existing ? `Provider 편집 — ${existing.name}` : "Provider 추가", body, wide: true,
      actions: [
        { label: "취소" },
        { label: "저장", class: "primary", onClick: async () => {
          const data = { ...v, ...collect() };
          delete data.api_key_set; delete data.api_key_env_present; delete data.builtin;
          if (existing) await api.put(`/api/providers/${existing.id}`, data); else await api.post("/api/providers", data);
          toast("저장했습니다. ‘연결 테스트’로 확인하세요.", "ok");
          load();
        } },
      ],
    });
  }

  await load();
}
