import { API, v1, request } from "./client";

export const startSession = (session_name) =>
  v1("/attendance/start",
    { method: "POST", body: JSON.stringify({ session_name }) },
    "/api/attendance/start");

export const stopSession = () =>
  v1("/attendance/stop", { method: "POST" }, "/api/attendance/stop");

export const roster = (session_id) => {
  const q = session_id ? `?session_id=${session_id}` : "";
  return v1(`/attendance/roster${q}`, {}, `/api/attendance/roster${q}`);
};

export const overrideStatus = (session_id, student_id, status) =>
  v1("/attendance/override",
    { method: "POST", body: JSON.stringify({ session_id, student_id, status }) },
    "/api/attendance/override");

export const detect = (image) =>
  v1("/attendance/detect",
    { method: "POST", body: JSON.stringify({ image }) },
    "/api/detect");

export const detectAnnotated = (image) =>
  v1("/attendance/detect/annotated",
    { method: "POST", body: JSON.stringify({ image }) },
    "/api/detect/annotated");

export const exportCsvUrl = (session_id) =>
  `${API}/api/v1/attendance/export.csv?session_id=${session_id}`;

export const recentLogs = (limit = 20) => request(`/api/logs?limit=${limit}`);

export const listSessions = (limit = 20) =>
  v1(`/attendance/sessions?limit=${limit}`, {}, `/api/attendance/sessions?limit=${limit}`);
