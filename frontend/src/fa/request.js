/* Shared request helpers for the shipped CRA app (extracted verbatim from
 * App.js in R5; behavior unchanged). Single import point so screens never
 * reimplement auth headers or snapshot logic. */

export const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

export const SESSION_KEY = "face_portal_session";

export function sessionToken() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null")?.token || "";
  } catch {
    return "";
  }
}

export async function api(path, opts = {}) {
  const token = sessionToken();
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(data.detail || data.error || `HTTP ${r.status}`);
    err.status = r.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const snapshot = (video, w = 320, h = 240) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  c.getContext("2d").drawImage(video, 0, 0, w, h);
  return c.toDataURL("image/jpeg", 0.8);
};
