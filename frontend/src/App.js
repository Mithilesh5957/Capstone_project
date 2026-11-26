import { useCallback, useEffect, useRef, useState } from "react";
import {
  FaButton,
  FaCard,
  FaModalFrame,
  FaStatusIndicator,
} from "./fa/primitives";
import { API, SESSION_KEY, api, sessionToken, snapshot } from "./fa/request";
import EnrollTab from "./screens/EnrollTab";
import HubDashboard from "./screens/HubDashboard";
import LoginScreen from "./screens/LoginScreen";
import ScannerView from "./screens/ScannerView";
import SettingsView from "./screens/SettingsView";
import StudentPortal from "./screens/StudentPortal";

/* ============================================================================
 * KL University — Face Attendance Portal.
 * Login gate -> Admin (Hub / Enroll / Live Scanner + MARP chaos) | Student.
 * Shared UI: fa/ tokens + primitives (+ fa/request for API helpers).
 * Feature screens live in ./screens (extracted verbatim from this file in
 * R5; behavior unchanged). No mock data: everything loads from the live API.
 * ========================================================================== */

const ANGLES = ["Front", "Left Profile", "Right Profile", "Upper Angle"];
const BRANCHES = ["CSE", "ECE", "ME", "AI&DS", "EEE", "BT"];
const FILTERS = ["ALL", ...BRANCHES];
function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(loadSession);
  // Backend roles are lowercase ("admin"/"student"); normalize for display.
  const role = (session?.role || "").toLowerCase() === "student" ? "Student" : "Admin";

  // R1: pre-fix sessions stored no token (fallback login). They are not
  // authorized for any protected API — force a fresh legitimate login.
  // No disable comment: the effect uses only the stable setSession updater
  // and the SESSION_KEY constant, so exhaustive-deps reports no violation.
  useEffect(() => {
    if (session && !session.token) {
      localStorage.removeItem(SESSION_KEY);
      setSession(null);
    }
  }, []);

  // R1: expired/invalid token (401) or insufficient privilege (403) ends the
  // session so the user must re-authenticate; other errors stay silent.
  const handleApiError = useCallback((e) => {
    if (e && (e.status === 401 || e.status === 403)) {
      localStorage.removeItem(SESSION_KEY);
      setSession(null);
      return true;
    }
    return false;
  }, []);
  const [tab, setTab] = useState("hub");
  const [students, setStudents] = useState([]);
  const [attendanceLogs, setAttendanceLogs] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [deptFilter, setDeptFilter] = useState("ALL");
  const [q, setQ] = useState("");
  const [logFilter, setLogFilter] = useState("Logs (All)");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);

  const [telemetry, setTelemetry] = useState({
    phase: "starting", marp_state: "UNINITIALIZED", stage: "UNINITIALIZED",
    model_ready: false, db_connected: false, uptime_s: 0, active_session: {},
  });
  const [ready, setReady] = useState(null);
  const [chaosMsg, setChaosMsg] = useState("");
  const [delay, setDelay] = useState(0);
  const [refuse, setRefuse] = useState(false);
  const [dropRate, setDropRate] = useState(0);
  const [vram, setVram] = useState(false);
  const [modelStall, setModelStall] = useState(false);
  const [sessionName, setSessionName] = useState("Morning Session");
  const [termLog, setTermLog] = useState(() => ([
    { id: 0, time: new Date().toLocaleTimeString("en-GB"), text: "TERMINAL ONLINE — POLLING READINESS EVERY 2S" },
  ]));
  const pushTerm = useCallback((text) => {
    const time = new Date().toLocaleTimeString("en-GB");
    setTermLog((p) => [...p.slice(-119), { id: Date.now() + Math.random(), time, text }]);
  }, []);

  const refreshStudents = useCallback(async () => {
    try {
      setStudents(await api("/api/students"));
    } catch (e) { handleApiError(e); /* loading */ }
  }, [handleApiError]);

  const refreshLogs = useCallback(async () => {
    try {
      const sid = telemetryRef.current?.active_session?.id;
      const url = sid ? `/api/attendance/roster?session_id=${sid}` : "/api/attendance/roster";
      const r = await api(url);
      setAttendanceLogs(r.records || []);
      return;
    } catch (e) { if (handleApiError(e)) return; /* fall through */ }
    try {
      const r = await api("/api/logs?limit=50");
      setAttendanceLogs(
        (Array.isArray(r) ? r : []).map((e) => ({
          student_id: "—", name: e.detection_type || "face", status: "Detected",
          marked_at: e.timestamp, confidence: e.confidence,
        }))
      );
    } catch (e) { handleApiError(e); /* leave */ }
  }, [handleApiError]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api("/api/attendance/sessions?limit=20"));
    } catch (e) { handleApiError(e); /* backend unreachable */ }
  }, [handleApiError]);

  const telemetryRef = useRef(telemetry);
  telemetryRef.current = telemetry;

  useEffect(() => {
    refreshStudents();
    refreshLogs();
    refreshSessions();
    const id = setInterval(() => {
      refreshStudents();
      refreshLogs();
      refreshSessions();
    }, 5000);
    return () => clearInterval(id);
  }, [refreshStudents, refreshLogs, refreshSessions]);

  // Webcam for scanner tab. mediaDevices is absent in some browsers and in
  // insecure contexts — guard it so a missing camera never crashes the app.
  const [cameraError, setCameraError] = useState("");
  useEffect(() => {
    if (role !== "Admin" || tab !== "scanner") return;
    setCameraError("");
    const md = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
    if (!md || typeof md.getUserMedia !== "function") {
      setCameraError("CAMERA UNAVAILABLE IN THIS BROWSER — LIVE DETECTION OFF.");
      return;
    }
    let stream;
    md.getUserMedia({ video: true })
      .then((s) => {
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch(() => setCameraError("CAMERA BLOCKED — ALLOW WEBCAM ACCESS."));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, [role, tab]);

  // Bounding-box overlay: black fill + lime box, mono badges
  useEffect(() => {
    const c = canvasRef.current,
      v = videoRef.current;
    if (!c || !v) return;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    const sx = c.width / (v.videoWidth || 1),
      sy = c.height / (v.videoHeight || 1);
    detections.forEach((d) => {
      const [x, y, w, h] = d.bbox;
      ctx.fillStyle = "#E2FF00";
      ctx.fillRect(x * sx, y * sy, w * sx, h * sy);
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 3;
      ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
      ctx.font = "bold 12px monospace";
      const label = d.label || `${d.name || d.type} ${d.confidence ?? ""}`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "#000";
      ctx.fillRect(x * sx, y * sy - 18, tw + 10, 18);
      ctx.fillStyle = "#E2FF00";
      ctx.fillText(label, x * sx + 5, y * sy - 5);
    });
  }, [detections]);

  // Detection loop
  useEffect(() => {
    if (role !== "Admin" || tab !== "scanner") return;
    const id = setInterval(async () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      try {
        const token = sessionToken();
        const r = await fetch(`${API}/api/detect`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ image: snapshot(v) }),
        });
        if (r.status === 401 || r.status === 403) {
          localStorage.removeItem(SESSION_KEY);
          setSession(null);
          return;
        }
        const data = await r.json();
        if (data.detections) {
          setDetections(data.detections);
          if (data.detections.length) {
            setLogs((p) =>
              [
                ...data.detections.map((d, i) => ({
                  ...d,
                  id: Date.now() + i,
                  time: new Date().toLocaleTimeString(),
                })),
                ...p,
              ].slice(0, 20)
            );
            refreshLogs();
          }
        }
      } catch { /* backend loading */ }
    }, 700);
    return () => clearInterval(id);
  }, [role, tab, refreshLogs]);

  // Telemetry poll (MARP v1 -> legacy fallback). R1: /status endpoints
  // require a valid login, so the poll sends the Bearer token like api().
  // Readiness probes stay open and need no token.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const token = sessionToken();
        const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
        const status = await fetch(`${API}/api/v1/marp/status`, { headers: authHeaders })
          .then(async (r) => {
            if (r.status === 401 || r.status === 403) {
              localStorage.removeItem(SESSION_KEY);
              setSession(null);
              throw new Error("unauthorized");
            }
            return r.json();
          })
          .catch((e) => {
            if (e?.message === "unauthorized") throw e;
            return fetch(`${API}/api/status`, { headers: authHeaders }).then(async (r) => {
              if (r.status === 401 || r.status === 403) {
                localStorage.removeItem(SESSION_KEY);
                setSession(null);
                throw new Error("unauthorized");
              }
              return r.json();
            });
          });
        const h = await fetch(`${API}/api/v1/marp/healthz/readiness`)
          .then(async (r) => {
            let body = {};
            try {
              body = await r.json();
            } catch { /* non-JSON */ }
            return { ok: r.ok, status: r.status, error: body.error || body.phase || "" };
          })
          .catch(() =>
            fetch(`${API}/healthz/readiness`)
              .then(async (r) => {
                let body = {};
                try {
                  body = await r.json();
                } catch { /* non-JSON */ }
                return { ok: r.ok, status: r.status, error: body.error || body.phase || "" };
              })
              .catch(() => null)
          );
        setTelemetry({
          phase: status.phase || "—",
          marp_state: status.marp_state || "—",
          stage: status.stage || status.metrics?.stage || status.marp_state || "—",
          model_ready: !!status.model_ready,
          db_connected: !!(status.db_connected ?? status.db_ready),
          uptime_s: status.uptime_s ?? 0,
          active_session: status.active_session || {},
        });
        setReady(h ? h.ok : false);
        if (!h) pushTerm("HEALTH CHECK: UNREACHABLE — CONNECTION REFUSED");
        else if (h.ok) pushTerm(`HEALTH CHECK: 200 OK (${status.phase || "ready"})`);
        else pushTerm(`HEALTH CHECK: ${h.status} — ${h.error || "failure"}`);
      } catch {
        setReady(false);
        pushTerm("HEALTH CHECK: POLL FAILED");
      }
    }, 2000);
    return () => clearInterval(id);
  }, [pushTerm]);

  const chaos = async (kind) => {
    const endpoints = {
      "db-drop": "/api/chaos/db-drop",
      "unload-model": "/api/chaos/unload-model",
      recover: "/api/chaos/recover",
    };
    pushTerm(`CHAOS INJECT: ${kind.toUpperCase()}...`);
    try {
      const r = await api(endpoints[kind] || "/api/chaos/db-drop", { method: "POST" });
      setChaosMsg(`CHAOS [${kind}] -> ${r.phase}`);
      pushTerm(`BACKEND: ${r.message || r.phase}`);
    } catch (e) {
      if (e && (e.status === 401 || e.status === 403)) {
        localStorage.removeItem(SESSION_KEY);
        setSession(null);
        return;
      }
      setChaosMsg(e?.status === 403
        ? "CHAOS DENIED — OPERATOR PRIVILEGES REQUIRED. PLEASE RE-LOGIN."
        : "CHAOS REQUEST FAILED (BACKEND UNREACHABLE)");
      pushTerm("BACKEND UNREACHABLE — COMMAND FAILED");
    }
  };

  const applyChaos = async () => {
    pushTerm(`CHAOS INJECT: DELAY=${delay}S REFUSE=${refuse} DROP=${dropRate} VRAM=${vram} STALL=${modelStall}`);
    try {
      const r = await api("/api/v1/marp/chaos/inject", {
        method: "POST",
        body: JSON.stringify({
          simulated_latency_sec: Number(delay),
          frame_drop_rate: Number(dropRate),
          simulate_vram_exhaustion: vram,
          artificial_probe_failure: refuse,
          model_stall: modelStall,
        }),
      });
      setChaosMsg(`INJECTED: ${JSON.stringify(r.chaos)}`);
      pushTerm("BACKEND: CHAOS APPLIED LIVE (NO RESTART)");
    } catch (e) {
      if (e && (e.status === 401 || e.status === 403)) {
        localStorage.removeItem(SESSION_KEY);
        setSession(null);
        return;
      }
      setChaosMsg("INJECT FAILED — NEEDS /api/v1 BACKEND");
      pushTerm("INJECT FAILED");
    }
  };

  const startSession = async () => {
    const name = (sessionName || "").trim() || "Morning Session";
    try {
      await api("/api/attendance/start", { method: "POST", body: JSON.stringify({ session_name: name }) });
      refreshLogs();
    } catch (e) { if (!handleApiError(e)) pushTerm(`START FAILED: ${e.message}`); }
  };
  const stopSession = async () => {
    try {
      await api("/api/attendance/stop", { method: "POST" });
      refreshLogs();
    } catch (e) { if (!handleApiError(e)) pushTerm(`STOP FAILED: ${e.message}`); }
  };

  const logout = () => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
    setConfirmLogout(false);
  };
  const [confirmLogout, setConfirmLogout] = useState(false);
  const logoutDialog = confirmLogout && (
    <FaModalFrame
      title="Log out?"
      description="You will need your username and password to sign in again."
      onCancel={() => setConfirmLogout(false)}
      actions={
        <>
          <FaButton variant="secondary" onClick={() => setConfirmLogout(false)}>
            Stay signed in
          </FaButton>
          <FaButton variant="danger" onClick={logout}>
            Log out
          </FaButton>
        </>
      }
    />
  );

  const filteredStudents =
    deptFilter === "ALL" ? students : students.filter((s) => s.branch === deptFilter);
  const rows = filteredStudents.filter(
    (s) => s.name.toLowerCase().includes(q.toLowerCase()) || s.student_id.includes(q)
  );
  const present = attendanceLogs.filter((r) => r.status === "Present").length;

  if (!session) {
    return (
      <main className="fa-page" style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
        <LoginScreen
          onLogin={(s) => {
            localStorage.setItem(SESSION_KEY, JSON.stringify(s));
            setSession(s);
          }}
        />
      </main>
    );
  }

  const marpOnline = ready === true;
  if (session && role === "Student") {
    return (
      <div className="fa-page">
        <div className="w-full space-y-4 p-4 lg:p-6" style={{ maxWidth: 1200, margin: "0 auto" }}>
        <header>
          <FaCard glass>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "center", padding: "12px 16px" }}>
              <p className="fa-brand-gradient" style={{ fontWeight: 800, fontSize: "var(--fa-t-lg)", letterSpacing: "0.04em", margin: 0 }}>FACEATTEND</p>
              <FaButton variant="danger" onClick={() => setConfirmLogout(true)}>
                Log out
              </FaButton>
            </div>
          </FaCard>
        </header>
        {logoutDialog}
        <main>
          <StudentPortal lockedId={session.student_id || session.username} />
        </main>
      </div>
      </div>
    );
  }
  const brandMark = (
    <span
      style={{
        display: "inline-flex", height: 40, width: 40, alignItems: "center", justifyContent: "center",
        borderRadius: "var(--fa-r-sm)", border: "1px solid var(--fa-border)", background: "var(--fa-bg)",
      }}
      aria-hidden="true"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2l8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5l8-3z" fill="#5EDBC6" />
        <path d="M8.5 12l2.5 2.5 4.5-5" stroke="#0B1220" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
    </span>
  );
  return (
    <div className="fa-page">
      <div className="w-full space-y-4 p-4 lg:p-6" style={{ maxWidth: 1200, margin: "0 auto" }}>
        <header>
          <FaCard>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "center", padding: "12px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {brandMark}
                <p className="fa-brand-gradient" style={{ fontWeight: 800, fontSize: "var(--fa-t-lg)", letterSpacing: "0.04em", margin: 0 }}>FACEATTEND</p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FaStatusIndicator tone="info">
                  {role === "Admin" ? "Admin" : `Student ${session.username || ""}`}
                </FaStatusIndicator>
                <FaButton variant="danger" onClick={() => setConfirmLogout(true)}>
                  Log out
                </FaButton>
              </div>
            </div>
          </FaCard>
        </header>
        {logoutDialog}

        {role === "Student" ? (
          <StudentPortal lockedId={session.student_id || session.username} />
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row">
          <FaCard glass className="w-full lg:w-64 shrink-0 self-start lg:sticky lg:top-4" role="complementary" aria-label="Navigation and system status">
            <nav aria-label="Primary" className="flex flex-row lg:flex-col flex-wrap gap-2" style={{ padding: 12 }}>
              {[
                ["hub", "▦ Dashboard"],
                ["enroll", "◉ Students"],
                ["scanner", "▶ Attendance"],
                ["settings", "⚙ Settings"],
              ].map(([key, label]) => (
                <FaButton
                  key={key}
                  variant="secondary"
                  aria-pressed={tab === key}
                  aria-current={tab === key ? "page" : undefined}
                  onClick={() => setTab(key)}
                >
                  {label}
                </FaButton>
              ))}
            </nav>
              <FaCard glass style={{ margin: 12, padding: 12 }}>
                <p style={{ fontSize: "var(--fa-t-xs)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--fa-text-muted)", margin: "0 0 4px" }}>System status</p>
                <FaStatusIndicator tone={marpOnline ? "ok" : "err"}>
                  {marpOnline ? "Online" : "Offline"}
                </FaStatusIndicator>
                <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", margin: "8px 0 0" }}>
                  {marpOnline ? "MARP READY · 200 OK" : `503 · ${String(telemetry.stage || "initializing").toUpperCase()}`}
                </p>
              </FaCard>
            </FaCard>
            <main className="min-w-0 flex-1">
              <div className="fa-page-enter" key={tab}>
        {tab === "hub" ? (
          <HubDashboard students={students} sessions={sessions} telemetry={telemetry} setTab={setTab} logFilter={logFilter} setLogFilter={setLogFilter} />
        ) : tab === "enroll" ? (
          <EnrollTab branches={BRANCHES} angles={ANGLES} onDone={() => { refreshStudents(); setTab("hub"); }} />
        ) : tab === "settings" ? (
          <SettingsView
            telemetry={telemetry} ready={ready} chaosMsg={chaosMsg} chaos={chaos}
            delay={delay} setDelay={setDelay} refuse={refuse} setRefuse={setRefuse}
            dropRate={dropRate} setDropRate={setDropRate} vram={vram} setVram={setVram}
            modelStall={modelStall} setModelStall={setModelStall}
            applyChaos={applyChaos} termLog={termLog}
          />
        ) : (
          <ScannerView
            videoRef={videoRef} canvasRef={canvasRef} logs={logs}
            attendanceLogs={attendanceLogs} present={present}
            telemetry={telemetry} marpOnline={marpOnline}
            cameraError={cameraError}
            sessionName={sessionName} onSessionName={setSessionName}
            onStartSession={startSession} onStopSession={stopSession}
          />
        )}
              </div>
            </main>
          </div>
        )}
      </div>
    </div>
  );
}
