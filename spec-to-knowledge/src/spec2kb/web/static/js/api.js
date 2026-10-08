// JSON API client. Errors carry the server's Korean "detail" message.

async function request(method, url, body, opts = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new Error("서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.");
  }
  if (opts.raw) {
    if (!res.ok) throw new Error(await errorText(res));
    return res;
  }
  if (!res.ok) throw new Error(await errorText(res));
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

async function errorText(res) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    return JSON.stringify(data);
  } catch {
    return `요청 실패 (HTTP ${res.status})`;
  }
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body) => request("POST", url, body === undefined ? {} : body),
  put: (url, body) => request("PUT", url, body),
  patch: (url, body) => request("PATCH", url, body),
  del: (url) => request("DELETE", url),
  raw: (method, url, body) => request(method, url, body, { raw: true }),
};

export async function downloadFrom(method, url, body, fallbackName) {
  const res = await api.raw(method, url, body);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const { downloadBlob } = await import("./ui.js");
  downloadBlob(blob, name);
  return name;
}
