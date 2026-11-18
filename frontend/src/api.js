const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

// The JWT lives in localStorage for simplicity; the backend never exposes DB credentials to the browser.
export const auth = {
  get: () => localStorage.getItem("applyai_token"),
  set: (t) => localStorage.setItem("applyai_token", t),
  clear: () => localStorage.removeItem("applyai_token"),
};

async function req(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (auth.get()) headers.Authorization = `Bearer ${auth.get()}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined) });
  if (res.status === 401 && auth.get()) { auth.clear(); window.location.assign("/login"); throw new Error("Your session expired. Sign in again."); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: (p) => req(p),
  post: (p, body = {}) => req(p, { method: "POST", body }),
  put: (p, body) => req(p, { method: "PUT", body }),
  del: (p) => req(p, { method: "DELETE" }),
  upload: (p, file) => { const f = new FormData(); f.append("file", file); return req(p, { method: "POST", form: f }); },
  blob: async (p) => {
    const res = await fetch(BASE + p, { headers: { Authorization: `Bearer ${auth.get()}` } });
    if (!res.ok) throw new Error("No snapshot yet");
    return URL.createObjectURL(await res.blob());
  },
};
