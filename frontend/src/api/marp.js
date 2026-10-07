import { API, v1, request } from "./client";

export const marpReadiness = () =>
  fetch(`${API}/api/v1/marp/healthz/readiness`)
    .then(async (r) => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) }))
    .catch(() => fetch(`${API}/healthz/readiness`)
      .then(async (r) => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) }))
      .catch(() => null));

export const marpStatus = () =>
  v1("/marp/status", {}, "/api/status");

export const chaosStatus = () =>
  request("/api/v1/marp/chaos/status").catch(() => v1("/marp/status", {}, "/api/status"));

export const injectChaos = (cfg) =>
  request("/api/v1/marp/chaos/inject", { method: "POST", body: JSON.stringify(cfg) });

export const resetChaos = () =>
  request("/api/v1/marp/chaos/reset", { method: "POST" }).catch(() =>
    v1("/marp/chaos/recover", { method: "POST" }, "/api/chaos/recover"));

export const chaos = (kind) => {
  const map = {
    "db-drop": ["/marp/chaos/db-drop", "/api/chaos/db-drop"],
    db_drop: ["/marp/chaos/db-drop", "/api/chaos/db-drop"],
    "unload-model": ["/marp/chaos/unload-model", "/api/chaos/unload-model"],
    model_unload: ["/marp/chaos/unload-model", "/api/chaos/unload-model"],
    recover: ["/marp/chaos/recover", "/api/chaos/recover"],
  };
  const [v1p, leg] = map[kind] || map["db-drop"];
  return v1(v1p, { method: "POST" }, leg);
};

export const tuneChaos = (knobs) =>
  request("/api/v1/marp/chaos/tune", { method: "POST", body: JSON.stringify(knobs) });

export const detectionSettings = () => request("/api/v1/settings/detection");
export const updateDetectionSettings = (body) =>
  request("/api/v1/settings/detection", { method: "POST", body: JSON.stringify(body) });
