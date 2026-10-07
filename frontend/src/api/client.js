const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

async function request(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
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
