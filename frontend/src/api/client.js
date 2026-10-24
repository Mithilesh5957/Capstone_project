// FACEATTEND API client — Vite-first (VITE_API_URL), CRA fallback.
const _viteApi =
  typeof import.meta !== "undefined" &&
  import.meta &&
  import.meta.env &&
  import.meta.env.VITE_API_URL
    ? import.meta.env.VITE_API_URL
    : null;

// eslint-disable-next-line no-undef
const _craApi =
  typeof process !== "undefined" &&
  process &&
  process.env &&
  process.env.REACT_APP_API_URL
    ? process.env.REACT_APP_API_URL
    : null;

const API = _viteApi || _craApi || "http://localhost:8000";

function authHeaders() {
  try {
    const raw =
      typeof localStorage !== "undefined"
        ? localStorage.getItem("face_portal_session")
        : null;
    if (!raw) return {};
    const s = JSON.parse(raw);
    if (s && s.token) return { Authorization: `Bearer ${s.token}` };
  } catch {
    /* ignore */
  }
  return {};
}

async function request(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(opts.headers || {}) },
    ...opts,
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

// Try /api/v1/... first, fall back to legacy /api/... so the UI works
// against both the new MARP app and older backend builds.
async function v1(path, opts = {}, legacyPath) {
  try {
    return await request(`/api/v1${path}`, opts);
  } catch (e) {
    if (legacyPath && (e.status === 404 || e.status === 405)) {
      return request(legacyPath, opts);
    }
    throw e;
  }
}

export { API, request, v1 };

export const snapshot = (video, w = 320, h = 240) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  c.getContext("2d").drawImage(video, 0, 0, w, h);
  return c.toDataURL("image/jpeg", 0.8);
};
