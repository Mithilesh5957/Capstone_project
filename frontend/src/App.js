import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

/* ============================================================================
 * KL University — Face Attendance Portal (STRICT NEO-BRUTALISM).
 * #E2FF00 on #F4F4F0, border-4 black, rounded-none, 8px hard shadows.
 * Login gate -> Admin (Hub / Enroll / Live Scanner + MARP chaos) | Student.
 * No mock data: everything loads from the live API.
 * ========================================================================== */

const SESSION_KEY = "face_portal_session";
const ANGLES = ["Front", "Left Profile", "Right Profile", "Upper Angle"];
const BRANCHES = ["CSE", "ECE", "ME", "AI&DS", "EEE", "BT"];
const FILTERS = ["ALL", ...BRANCHES];

async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
  return data;
}
const snapshot = (video, w = 320, h = 240) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  c.getContext("2d").drawImage(video, 0, 0, w, h);
  return c.toDataURL("image/jpeg", 0.8);
};
function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(loadSession);
  const role = session?.role || "Admin";
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
    } catch { /* loading */ }
  }, []);

  const refreshLogs = useCallback(async () => {
    try {
      const sid = telemetryRef.current?.active_session?.id;
      const url = sid ? `/api/attendance/roster?session_id=${sid}` : "/api/attendance/roster";
      const r = await api(url);
      setAttendanceLogs(r.records || []);
      return;
    } catch { /* fall through */ }
    try {
      const r = await api("/api/logs?limit=50");
      setAttendanceLogs(
        (Array.isArray(r) ? r : []).map((e) => ({
          student_id: "—", name: e.detection_type || "face", status: "Detected",
          marked_at: e.timestamp, confidence: e.confidence,
        }))
      );
    } catch { /* leave */ }
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api("/api/attendance/sessions?limit=20"));
    } catch { /* legacy backend without sessions endpoint */ }
  }, []);

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

  // Webcam for scanner tab
  useEffect(() => {
    if (role !== "Admin" || tab !== "scanner") return;
    let stream;
    navigator.mediaDevices
      .getUserMedia({ video: true })
      .then((s) => {
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch(() => {});
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
        const r = await fetch(`${API}/api/detect`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: snapshot(v) }),
        });
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

  // Telemetry poll (MARP v1 -> legacy fallback)
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const status = await fetch(`${API}/api/v1/marp/status`)
          .then((r) => r.json())
          .catch(() => fetch(`${API}/api/status`).then((r) => r.json()));
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
    } catch {
      setChaosMsg("CHAOS REQUEST FAILED (BACKEND UNREACHABLE)");
      pushTerm("BACKEND UNREACHABLE — COMMAND FAILED");
    }
  };

  const applyChaos = async () => {
    pushTerm(`CHAOS INJECT: DELAY=${delay}S REFUSE=${refuse}`);
    try {
      const r = await api("/api/v1/marp/chaos/inject", {
        method: "POST",
        body: JSON.stringify({
          simulated_latency_sec: Number(delay),
          frame_drop_rate: 0,
          simulate_vram_exhaustion: false,
          artificial_probe_failure: refuse,
          model_stall: false,
        }),
      });
      setChaosMsg(`INJECTED: ${JSON.stringify(r.chaos)}`);
      pushTerm("BACKEND: CHAOS APPLIED LIVE (NO RESTART)");
    } catch {
      setChaosMsg("INJECT FAILED — NEEDS /api/v1 BACKEND");
      pushTerm("INJECT FAILED");
    }
  };

  const logout = () => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  const filteredStudents =
    deptFilter === "ALL" ? students : students.filter((s) => s.branch === deptFilter);
  const rows = filteredStudents.filter(
    (s) => s.name.toLowerCase().includes(q.toLowerCase()) || s.student_id.includes(q)
  );
  const present = attendanceLogs.filter((r) => r.status === "Present").length;

  if (!session) {
    return (
      <div className="min-h-screen bg-[#F4F4F0] text-black font-sans flex items-center justify-center p-4">
        <LoginScreen
          onLogin={(s) => {
            localStorage.setItem(SESSION_KEY, JSON.stringify(s));
            setSession(s);
          }}
        />
      </div>
    );
  }

  const marpOnline = ready === true;
  if (session && role === "Student") {
    return (
      <div className="min-h-screen bg-[#F4F4F0] text-black font-sans">
        <div className="w-full space-y-4 p-4 lg:p-6">
          <header className="bg-white border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none px-4 py-3 flex flex-wrap gap-3 justify-between items-center">
            <p className="font-extrabold text-xl tracking-wider uppercase">FACEATTEND</p>
            <button onClick={logout} className="rounded-none border-2 border-black bg-[#DC2626] px-3 py-1.5 font-mono text-xs font-bold uppercase text-white">Logout</button>
          </header>
          <StudentPortal lockedId={session.student_id || session.username} />
        </div>
      </div>
    );
  }
  return (
    <div className="min-h-screen bg-[#F4F4F0] text-black font-sans">
      <div className="w-full space-y-4 p-4 lg:p-6">
        <header className="bg-white border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none px-4 py-3 flex flex-wrap gap-3 justify-between items-center">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-none border-2 border-[#E2FF00] bg-black">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 2l8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5l8-3z" fill="#E2FF00" />
                <path d="M8.5 12l2.5 2.5 4.5-5" stroke="#000" strokeWidth="2" fill="none" strokeLinecap="square" />
              </svg>
            </span>
            <p className="font-extrabold text-xl tracking-wider uppercase">FACEATTEND</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-none border-2 border-black bg-white px-3 py-1.5 font-mono text-xs font-bold uppercase">
              {role === "Admin" ? "Admin [ADMIN]" : `Student [${session.username}]`}
            </span>
            <button onClick={logout} className="rounded-none border-2 border-black bg-[#DC2626] px-3 py-1.5 font-mono text-xs font-bold uppercase text-white hover:translate-x-1 hover:translate-y-1 transition-all">
              Logout
            </button>
          </div>
        </header>

        {role === "Student" ? (
          <StudentPortal lockedId={session.student_id || session.username} />
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row">
            <aside className="flex w-full lg:w-64 shrink-0 flex-col gap-2 self-start lg:sticky lg:top-4 rounded-none border-4 border-black bg-white p-3 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
              <nav className="flex flex-row lg:flex-col flex-wrap gap-2">
                {[
                  ["hub", "▦ DASHBOARD"],
                  ["enroll", "◉ STUDENTS"],
                  ["scanner", "▶ ATTENDANCE"],
                  ["settings", "⚙ SETTINGS"],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={`rounded-none border-2 border-black px-4 py-2.5 text-left text-sm font-extrabold uppercase tracking-wider transition-all hover:translate-x-1 hover:translate-y-1 hover:shadow-none ${
                      tab === key ? "bg-[#E2FF00] text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]" : "bg-white text-black hover:bg-[#F4F4F0]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </nav>
              <div className="mt-auto rounded-none border-4 border-black bg-black p-3 text-[#E2FF00]">
                <p className="font-mono text-[11px] font-bold uppercase tracking-wider opacity-70">System Status</p>
                <p className="mt-1 flex items-center gap-2 font-extrabold uppercase tracking-wider text-sm">
                  <span className={`inline-block h-3 w-3 rounded-none border-2 border-[#E2FF00] ${marpOnline ? "bg-[#E2FF00]" : "bg-transparent"}`} />
                  {marpOnline ? "ONLINE" : "OFFLINE"}
                </p>
                <p className="mt-1 font-mono text-[11px] font-bold">
                  {marpOnline ? "MARP READY 200 OK" : `503 ${String(telemetry.stage || "INITIALIZING").toUpperCase()}`}
                </p>
              </div>
            </aside>
            <main className="min-w-0 flex-1">
        {tab === "hub" ? (
          <HubDashboard students={students} sessions={sessions} telemetry={telemetry} setTab={setTab} logFilter={logFilter} setLogFilter={setLogFilter} />
        ) : tab === "hub-legacy-removed" ? (
          <div className="space-y-4">
            <div className="grid md:grid-cols-3 gap-4">
              {[
                { label: "TOTAL STUDENTS", value: String(students.length), sub: "LIVE /api/students", hot: true },
                { label: "SESSIONS HELD", value: String(sessions.length), sub: "LIVE /attendance/sessions", hot: false },
                {
                  label: "AVG ATTENDANCE",
                  value: sessions[0] && sessions[0].total ? `${Math.round((sessions[0].present / sessions[0].total) * 100)}%` : "—",
                  sub: sessions[0] ? `SESSION #${sessions[0].session_id} ${sessions[0].present}/${sessions[0].total}` : "NO SESSIONS YET",
                  hot: true,
                },
              ].map((m) => (
                <div key={m.label} className={`${m.hot ? "bg-[#E2FF00]" : "bg-white"} border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none p-5`}>
                  <p className="font-extrabold uppercase tracking-wider text-xs">{m.label}</p>
                  <p className="font-extrabold uppercase tracking-wider text-4xl">{m.value}</p>
                  <p className="mt-1 font-mono text-xs">{m.sub}</p>
                </div>
              ))}
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <button onClick={() => setTab("scanner")} className="bg-[#E2FF00] border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none p-4 text-left font-extrabold uppercase tracking-wider hover:translate-x-1 hover:translate-y-1 hover:shadow-none transition-all">
                ▶ LIVE SESSION{telemetry.active_session?.id ? ` — #${telemetry.active_session.id} ACTIVE` : ""}
              </button>
              <button onClick={() => setTab("enroll")} className="bg-white border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none p-4 text-left font-extrabold uppercase tracking-wider hover:translate-x-1 hover:translate-y-1 hover:shadow-none transition-all">
                ◉ STUDENTS — {students.length} ENROLLED
              </button>
            </div>
            <div className="brutal-card p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <p className="font-extrabold uppercase tracking-wider text-xs">SESSION LOG — FILTER</p>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="SEARCH NAME / ROLL…" className="brutal-input max-w-xs" />
                <div className="flex flex-wrap gap-1">
                  {FILTERS.map((f) => (
                    <button key={f} onClick={() => setDeptFilter(f)}
                      className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${deptFilter === f ? "bg-black text-[#E2FF00]" : "bg-white text-black"}`}>{f}</button>
                  ))}
                </div>
              </div>
              <table className="w-full text-sm bg-white">
                <thead><tr className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs">
                  <th className="text-left p-3">SESSION</th><th className="text-left p-3">DATE</th><th className="text-left p-3">PRESENT</th><th className="text-left p-3">STATUS</th>
                </tr></thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.session_id} className="border-t-4 border-black bg-white">
                      <td className="p-3 font-mono text-xs">#{s.session_id} {s.session_name}</td>
                      <td className="p-3 font-mono text-xs">{s.date || "—"}</td>
                      <td className="p-3"><span className="rounded-none border-2 border-black bg-[#E2FF00] px-2 py-0.5 font-mono text-[11px] font-bold">{s.present}/{s.total}</span></td>
                      <td className="p-3"><span className="rounded-none border-2 border-black bg-white px-2 py-0.5 font-mono text-[11px] font-bold">CLOSED</span></td>
                    </tr>
                  ))}
                  {sessions.length === 0 && <tr><td colSpan={4} className="p-4 text-center font-mono text-xs bg-white">NO SESSIONS YET</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="brutal-card overflow-hidden">
              <h3 className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs px-4 py-2">STUDENT DIRECTORY ({rows.length})</h3>
              <table className="w-full text-sm bg-white">
                <thead><tr className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs">
                  <th className="text-left p-3">ROLL NO</th><th className="text-left p-3">NAME</th><th className="text-left p-3">BRANCH</th>
                </tr></thead>
                <tbody>
                  {rows.map((s) => (
                    <tr key={s.student_id} className="border-t-4 border-black bg-white">
                      <td className="p-3 font-mono text-xs">{s.student_id}</td>
                      <td className="p-3 font-bold">{s.name}</td>
                      <td className="p-3">{s.branch}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : tab === "enroll" ? (
          <EnrollTab onDone={() => { refreshStudents(); setTab("hub"); }} />
        ) : tab === "settings" ? (
          <div className="brutal-card p-0">
            <div className="border-b-4 border-black bg-[#E2FF00] px-5 py-3">
              <h2 className="font-extrabold uppercase tracking-wider text-sm">SETTINGS & MARP CHAOS HUB</h2>
              <p className="font-mono text-xs">PHASE {telemetry.phase} • STAGE {telemetry.stage} • {ready ? "200 OK" : "503"}</p>
            </div>
            <ChaosPanel
              telemetry={telemetry} chaosMsg={chaosMsg} chaos={chaos}
              delay={delay} setDelay={setDelay} refuse={refuse} setRefuse={setRefuse}
              applyChaos={applyChaos}
            />
          </div>
        ) : (
          <div className="space-y-4">
            <div className={`flex flex-wrap items-center justify-between gap-2 border-4 border-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] rounded-none p-3 ${telemetry.active_session?.id ? "bg-[#E2FF00]" : "bg-white"}`}>
              <p className="font-extrabold uppercase tracking-wider text-sm">
                {telemetry.active_session?.id
                  ? `SESSION #${telemetry.active_session.id} ACTIVE — PRESENT ${present}/${attendanceLogs.length}`
                  : "NO ACTIVE SESSION — START ONE BELOW"}
              </p>
              <div className="flex flex-wrap gap-2">
                <button onClick={async () => { await api("/api/attendance/start", { method: "POST", body: JSON.stringify({ session_name: "Morning Session" }) }); refreshLogs(); }} className="brutal-btn text-xs">START SESSION</button>
                <button onClick={async () => { await api("/api/attendance/stop", { method: "POST" }); refreshLogs(); }} className="bg-white text-black font-extrabold tracking-wider uppercase border-4 border-black px-4 py-2 text-xs hover:translate-x-1 hover:translate-y-1 transition-all">END SESSION</button>
              </div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <div className="brutal-card p-4">
                  <h2 className="font-extrabold uppercase tracking-wider text-sm mb-3">LIVE CAMERA VIEW</h2>
                  <div className="relative border-4 border-black overflow-hidden bg-black">
                    <video ref={videoRef} autoPlay muted playsInline className="w-full" />
                    <canvas ref={canvasRef} width={640} height={480} className="absolute inset-0 w-full h-full" />
                  </div>
                </div>
                <div className="brutal-card p-4">
                  <h2 className="font-extrabold uppercase tracking-wider text-sm mb-2">DETECTION LOG (LIVE)</h2>
                  <ul className="h-40 overflow-y-auto font-mono text-xs space-y-1 border-4 border-black bg-[#F4F4F0] p-2">
                    {logs.length === 0 && <li>NO DETECTIONS YET…</li>}
                    {logs.map((l) => (
                      <li key={l.id}>
                        [{l.time}] <b>{l.label || l.name || l.type}</b> CONF={l.confidence} BBOX=[{(l.bbox || []).join(",")}]
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="brutal-card overflow-hidden h-fit">
                <div className="border-b-4 border-black bg-black text-[#E2FF00] px-3 py-2 font-mono text-[11px] font-bold uppercase">ROLL CALL</div>
                <ul className="max-h-72 divide-y-4 divide-black overflow-y-auto bg-white">
                  {attendanceLogs.map((r, i) => (
                    <li key={`side-${r.student_id}-${i}`} className="flex items-center justify-between p-2">
                      <div>
                        <p className="text-sm font-extrabold">{r.name || "—"}</p>
                        <p className="font-mono text-[11px]">{r.student_id || "—"}</p>
                      </div>
                      <span className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${r.status === "Present" ? "bg-[#E2FF00] text-black" : "bg-white text-black"}`}>
                        {r.status || "DETECTED"}
                      </span>
                    </li>
                  ))}
                  {attendanceLogs.length === 0 && <li className="p-4 font-mono text-xs">EMPTY — FACE THE CAMERA.</li>}
                </ul>
              </div>
            </div>
            <div className="brutal-card overflow-hidden">
              <h2 className="font-extrabold uppercase tracking-wider text-sm p-4 border-b-4 border-black bg-[#E2FF00]">
                LIVE ATTENDANCE ROSTER ({attendanceLogs.length})
              </h2>
              <table className="w-full text-sm bg-white">
                <thead><tr className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs">
                  <th className="text-left p-2">ID</th><th className="text-left p-2">NAME</th><th className="text-left p-2">STATUS</th>
                </tr></thead>
                <tbody>
                  {attendanceLogs.map((r, i) => (
                    <tr key={`${r.student_id}-${i}`} className="border-t-4 border-black bg-white">
                      <td className="p-2 font-mono text-xs">{r.student_id || "—"}</td>
                      <td className="p-2 font-bold">{r.name || "—"}</td>
                      <td className="p-2">
                        <span className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${r.status === "Present" ? "bg-[#E2FF00] text-black" : r.status === "Absent" ? "bg-[#DC2626] text-white" : "bg-white text-black"}`}>
                          {r.status || "DETECTED"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
            </main>
          </div>
        )}
      </div>
    </div>
  );
}

function HubDashboard({ students, sessions, telemetry, setTab, logFilter, setLogFilter }) {
  const withTotal = sessions.filter((s) => s.total > 0);
  const avg = withTotal.length
    ? Math.round(withTotal.reduce((a, s) => a + (s.present / s.total) * 100, 0) / withTotal.length)
    : 0;
  const last = sessions[0];
  const present = last ? last.present : 0;
  const absent = last ? last.absent : 0;
  const denom = Math.max(1, present + absent);
  const visible = sessions.filter((s) => {
    if (logFilter === "Logs (Present ≥ 50%)") return s.total > 0 && s.present / s.total >= 0.5;
    if (logFilter === "Logs (Absent-heavy)") return s.total > 0 && s.absent > s.present;
    return true;
  });
  const exportSessions = () => {
    const head = "session_id,session_name,date,total,present,absent";
    const lines = visible.map((s) =>
      [s.session_id, `"${(s.session_name || "").replace(/"/g, '""')}"`, s.date || "", s.total, s.present, s.absent].join(","));
    const blob = new Blob([[head, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "faceattend_sessions.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-none border-4 border-black bg-white p-4 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div>
          <h1 className="font-extrabold uppercase tracking-wider text-2xl">DASHBOARD</h1>
          <p className="font-mono text-xs font-bold uppercase tracking-wider">FaceAttend Management System</p>
        </div>
        <button onClick={exportSessions} className="rounded-none border-4 border-black bg-black px-5 py-2.5 font-extrabold uppercase tracking-wider text-sm text-[#E2FF00] hover:translate-x-1 hover:translate-y-1 hover:bg-[#E2FF00] hover:text-black hover:shadow-none transition-all">
          ⤓ EXPORT SESSIONS
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {[
          { icon: "◉", value: String(students.length), label: "TOTAL STUDENTS" },
          { icon: "▦", value: String(sessions.length), label: "SESSIONS HELD" },
          { icon: "✔", value: `${avg}%`, label: "AVG ATTENDANCE" },
        ].map((m) => (
          <div key={m.label} className="flex items-center gap-4 rounded-none border-4 border-black bg-white p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
            <span className="flex h-12 w-12 items-center justify-center rounded-none border-2 border-black bg-[#E2FF00] text-xl font-extrabold">{m.icon}</span>
            <div>
              <p className="font-extrabold uppercase tracking-wider text-3xl">{m.value}</p>
              <p className="font-mono text-xs font-bold uppercase tracking-wider">{m.label}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-none border-4 border-black bg-white p-5 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] lg:col-span-3">
          <h2 className="font-extrabold uppercase tracking-wider text-sm">ATTENDANCE DISTRIBUTION</h2>
          <p className="mt-1 font-mono text-xs font-bold uppercase">{last ? `LATEST — SESSION #${last.session_id}` : "NO SESSIONS YET"}</p>
          <div className="mt-4 flex h-40 items-end gap-3 border-4 border-black bg-[#F4F4F0] p-3">
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{present}</p>
              <div className="w-full border-2 border-black bg-[#E2FF00]" style={{ height: `${Math.round((present / denom) * 100)}%`, minHeight: present ? 8 : 0 }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Present</p>
            </div>
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{absent}</p>
              <div className="w-full border-2 border-black bg-[#DC2626]" style={{ height: `${Math.round((absent / denom) * 100)}%`, minHeight: absent ? 8 : 0 }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Absent</p>
            </div>
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{students.length}</p>
              <div className="w-full border-2 border-black bg-black" style={{ height: "100%" }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Enrolled</p>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <button onClick={() => setTab("scanner")} className="flex flex-1 items-center justify-between rounded-none border-4 border-black bg-[#E2FF00] p-5 text-left shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] hover:translate-x-1 hover:translate-y-1 hover:shadow-none transition-all">
            <span><span className="block font-extrabold uppercase tracking-wider text-lg">▶ LIVE SESSION</span>
            <span className="block font-mono text-xs font-bold uppercase">Start new face recognition{telemetry.active_session?.id ? ` — #${telemetry.active_session.id} ACTIVE` : ""}</span></span>
          </button>
          <button onClick={() => setTab("enroll")} className="flex flex-1 items-center justify-between rounded-none border-4 border-black bg-white p-5 text-left shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] hover:translate-x-1 hover:translate-y-1 hover:shadow-none transition-all">
            <span><span className="block font-extrabold uppercase tracking-wider text-lg">◉ STUDENTS</span>
            <span className="block font-mono text-xs font-bold uppercase">Register new face records</span></span>
          </button>
        </div>
      </div>
      <div className="rounded-none border-4 border-black bg-white p-4 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-extrabold uppercase tracking-wider text-sm">SESSION LOG</h2>
          <select value={logFilter} onChange={(e) => setLogFilter(e.target.value)} className="rounded-none border-4 border-black bg-[#F4F4F0] px-3 py-1.5 font-mono text-xs font-bold uppercase focus:outline-none">
            {["Logs (All)", "Logs (Present ≥ 50%)", "Logs (Absent-heavy)"].map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto border-4 border-black">
          <table className="w-full bg-white text-sm">
            <thead><tr className="bg-black font-extrabold uppercase tracking-wider text-xs text-[#E2FF00]">
              <th className="text-left p-3">Session</th><th className="text-left p-3">Date</th><th className="text-left p-3">Present</th><th className="text-left p-3">Absent</th><th className="text-left p-3">Status</th>
            </tr></thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.session_id} className="border-t-4 border-black bg-white">
                  <td className="p-3 font-mono text-xs font-bold">#{s.session_id} {s.session_name}</td>
                  <td className="p-3 font-mono text-xs">{s.date || "—"}</td>
                  <td className="p-3"><span className="rounded-none border-2 border-black bg-[#E2FF00] px-2 py-0.5 font-mono text-[11px] font-bold text-black">{s.present}/{s.total}</span></td>
                  <td className="p-3"><span className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-[11px] font-bold ${s.absent ? "bg-[#DC2626] text-white" : "bg-white text-black"}`}>{s.absent}</span></td>
                  <td className="p-3"><span className="rounded-none border-2 border-black bg-white px-2 py-0.5 font-mono text-[11px] font-bold">CLOSED</span></td>
                </tr>
              ))}
              {visible.length === 0 && <tr><td colSpan={5} className="bg-white p-4 text-center font-mono text-xs font-bold">NO SESSIONS MATCH THIS FILTER</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ChaosPanel({ telemetry, chaosMsg, chaos, delay, setDelay, refuse, setRefuse, applyChaos }) {
  const dot = (ok) => (ok ? "bg-black" : "bg-[#DC2626]");
  return (
    <div className="p-4 space-y-3">
      <div className="space-y-1 font-mono text-xs border-4 border-black bg-black text-[#E2FF00] p-3 rounded-none">
        <div className="flex justify-between"><span>&gt; PHASE</span><code>{telemetry.phase}</code></div>
        <div className="flex justify-between"><span>&gt; STAGE</span><code>{telemetry.stage}</code></div>
        <div className="flex justify-between items-center">
          <span>&gt; MODEL</span>
          <span className="flex items-center gap-2"><span className={`w-3 h-3 rounded-none border-2 border-[#E2FF00] ${dot(telemetry.model_ready)}`} />{telemetry.model_ready ? "LOADED" : "LOADING"}</span>
        </div>
        <div className="flex justify-between"><span>&gt; UPTIME</span><code>{telemetry.uptime_s}s</code></div>
      </div>
      <p className="font-extrabold uppercase tracking-wider text-xs">$ CHAOS_INJECT --</p>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => chaos("db-drop")} className="bg-[#DC2626] text-white font-extrabold uppercase tracking-wider text-xs border-4 border-black px-3 py-1.5 hover:translate-x-1 hover:translate-y-1 transition-all">DB DROP</button>
        <button onClick={() => chaos("unload-model")} className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs border-4 border-black px-3 py-1.5 hover:translate-x-1 hover:translate-y-1 transition-all">UNLOAD MODEL</button>
        <button onClick={() => chaos("recover")} className="bg-[#E2FF00] text-black font-extrabold uppercase tracking-wider text-xs border-4 border-black px-3 py-1.5 hover:translate-x-1 hover:translate-y-1 transition-all">RECOVER</button>
      </div>
      <label className="block font-extrabold uppercase tracking-wider text-xs">MODEL LOAD DELAY — {delay}S (0–30)
        <input type="range" min="0" max="30" step="1" value={delay} onChange={(e) => setDelay(Number(e.target.value))} className="w-full accent-black" />
      </label>
      <button onClick={() => setRefuse((v) => !v)} className={`rounded-none border-2 border-black px-2 py-1 font-mono text-[11px] font-bold uppercase ${refuse ? "bg-[#DC2626] text-white" : "bg-white text-black"}`}>
        {refuse ? "■ PROBE REFUSAL ON (503)" : "□ FORCE PROBE REFUSAL (503)"}
      </button>
      <button onClick={applyChaos} className="brutal-btn w-full">APPLY CHAOS INJECTION</button>
      {chaosMsg && <p className="font-mono text-xs border-4 border-black bg-[#F4F4F0] p-2 rounded-none">{chaosMsg}</p>}
    </div>
  );
}

function LoginScreen({ onLogin }) {
  const [mode, setMode] = useState("Admin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const canonical = (v) => {
    const raw = (v || "").trim();
    if (raw.includes("@")) return raw.split("@")[0].trim() || raw;
    return raw;
  };
  const doLogin = async (u, pw) => {
    setBusy(true);
    try {
      const ctx = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: u, password: pw, role: mode.toLowerCase() }),
      });
      onLogin(
        mode === "Admin"
          ? { role: "Admin", username: ctx.username || "admin", name: ctx.name || "Class Teacher" }
          : { role: "Student", username: u, student_id: ctx.student_id || u, name: ctx.name || u, branch: ctx.branch || "" }
      );
    } catch {
      onLogin(
        mode === "Admin"
          ? { role: "Admin", username: "admin", name: "Class Teacher" }
          : { role: "Student", username: u, student_id: u, name: u, branch: "" }
      );
    } finally {
      setBusy(false);
    }
  };
  const submit = async (e) => {
    e?.preventDefault();
    setErr("");
    const u = username.trim();
    if (mode === "Admin" && (canonical(u).toLowerCase() !== "admin" || password !== "admin123")) {
      setErr("INVALID OPERATOR CREDENTIALS — USE THE DEMO PILL BELOW.");
      return;
    }
    if (mode === "Student" && (!u || password !== "student123")) {
      setErr("STUDENT: ANY ROLL NO. + PASSWORD student123.");
      return;
    }
    await doLogin(u, password);
  };
  const fillDemo = async () => {
    setMode("Admin");
    setUsername("admin@college.edu");
    setPassword("admin123");
    setErr("");
    await doLogin("admin@college.edu", "admin123");
  };

  return (
    <div className="brutal-card w-full max-w-md p-0">
      <div className="border-b-4 border-black bg-[#E2FF00] px-6 py-4 rounded-none">
        <p className="font-extrabold uppercase tracking-wider text-xl">KL UNIVERSITY</p>
        <p className="font-mono text-xs uppercase">FACE ATTENDANCE — SIGN IN</p>
      </div>
      <div className="p-6 space-y-3">
        <div className="grid grid-cols-2 gap-2 border-4 border-black bg-white p-1 rounded-none">
          {["Admin", "Student"].map((m) => (
            <button key={m} type="button" onClick={() => { setMode(m); setErr(""); }}
              className={`font-extrabold uppercase tracking-wider px-4 py-2 text-xs rounded-none ${mode === m ? "bg-black text-[#E2FF00]" : "bg-white text-black"}`}>{m}</button>
          ))}
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder={mode === "Admin" ? "admin@college.edu" : "2100030001"} className="brutal-input" />
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="••••••••" className="brutal-input" />
          {err && <p className="rounded-none border-2 border-black bg-[#DC2626] text-white px-3 py-2 font-mono text-xs font-bold">{err}</p>}
          <button type="submit" disabled={busy} className="brutal-btn w-full disabled:opacity-50">
            {busy ? "SIGNING IN…" : `LOGIN AS ${mode.toUpperCase()}`}
          </button>
        </form>
        <button type="button" onClick={fillDemo} disabled={busy}
          className="w-full rounded-none border-2 border-black bg-[#E2FF00] px-2 py-2 font-mono text-[11px] font-bold uppercase text-black disabled:opacity-50">
          ADM&nbsp;&nbsp;admin@college.edu / admin123 — TAP TO LOGIN
        </button>
      </div>
    </div>
  );
}

function EnrollTab({ onDone }) {
  const enrollVideoRef = useRef(null);
  const [form, setForm] = useState({ student_id: "", name: "", branch: "CSE" });
  const [shots, setShots] = useState([null, null, null, null]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    let stream;
    navigator.mediaDevices
      .getUserMedia({ video: true })
      .then((s) => {
        stream = s;
        if (enrollVideoRef.current) enrollVideoRef.current.srcObject = s;
      })
      .catch(() => setMsg("CAMERA BLOCKED — ALLOW WEBCAM ACCESS."));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  const capture = (i) => {
    if (!enrollVideoRef.current?.videoWidth) return;
    const next = [...shots];
    next[i] = snapshot(enrollVideoRef.current);
    setShots(next);
  };
  const doneCount = shots.filter(Boolean).length;

  const submit = async () => {
    if (!form.student_id.trim() || !form.name.trim()) {
      setMsg("STUDENT ID AND FULL NAME ARE REQUIRED.");
      return;
    }
    if (doneCount < 4) {
      setMsg(`CAPTURE ALL 4 ANGLES FIRST (${doneCount}/4 DONE).`);
      return;
    }
    setBusy(true);
    setMsg("UPLOADING STUDENT + EMBEDDINGS…");
    try {
      const r = await api("/api/students/enroll", {
        method: "POST",
        body: JSON.stringify({ ...form, images: shots }),
      });
      setMsg(`ENROLLED ${r.name} (${r.student_id}) — ${r.angles_used} ANGLES.`);
      setShots([null, null, null, null]);
      onDone();
    } catch (e) {
      setMsg(e.message.toUpperCase());
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="brutal-card p-5 space-y-3">
        <h2 className="font-extrabold uppercase tracking-wider">STUDENT PROFILE</h2>
        <label className="block font-extrabold uppercase tracking-wider text-xs">STUDENT ID / ROLL NO.
          <input value={form.student_id} onChange={set("student_id")} placeholder="2100030001" className="brutal-input mt-1" />
        </label>
        <label className="block font-extrabold uppercase tracking-wider text-xs">FULL NAME
          <input value={form.name} onChange={set("name")} placeholder="ENTER FULL NAME" className="brutal-input mt-1" />
        </label>
        <label className="block font-extrabold uppercase tracking-wider text-xs">BRANCH
          <select value={form.branch} onChange={set("branch")} className="brutal-input mt-1">
            {BRANCHES.map((d) => (<option key={d} value={d}>{d}</option>))}
          </select>
        </label>
      </div>
      <div className="brutal-card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-extrabold uppercase tracking-wider">4-ANGLE FACE SCAN</h2>
          <span className="rounded-none border-2 border-black bg-[#E2FF00] px-2 py-0.5 font-mono text-xs font-bold">{doneCount}/4</span>
        </div>
        <video ref={enrollVideoRef} autoPlay muted playsInline className="w-full bg-black aspect-video object-cover border-4 border-black rounded-none" />
        <div className="grid grid-cols-4 gap-2">
          {ANGLES.map((a, i) => (
            <button key={a} onClick={() => capture(i)}
              className={`rounded-none border-4 overflow-hidden text-[11px] font-bold uppercase ${shots[i] ? "border-black" : "border-dashed border-black"}`}>
              {shots[i] ? (
                <img src={shots[i]} alt={a} className="w-full aspect-square object-cover" />
              ) : (
                <span className="block py-5">◌<br />{a}</span>
              )}
              <span className={`block py-1 border-t-4 border-black ${shots[i] ? "bg-[#E2FF00] text-black" : "bg-white text-black"}`}>
                {shots[i] ? `✓ ${a}` : a}
              </span>
            </button>
          ))}
        </div>
        <button onClick={submit} disabled={busy} className="brutal-btn w-full disabled:opacity-50">
          {busy ? "SAVING…" : "SAVE STUDENT & EMBEDDINGS"}
        </button>
        {msg && <p className="font-mono text-xs border-4 border-black bg-[#F4F4F0] p-2 rounded-none">{msg}</p>}
      </div>
    </div>
  );
}

function StudentPortal({ lockedId }) {
  const [sid, setSid] = useState(lockedId || "");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const lookup = async (id) => {
    const target = (id ?? sid).trim();
    if (!target) {
      setErr("ENTER YOUR STUDENT ID / ROLL NO.");
      return;
    }
    try {
      setData(await api(`/api/students/${encodeURIComponent(target)}/attendance`));
      setErr("");
    } catch {
      setErr("NO RECORD FOUND.");
      setData(null);
    }
  };
  useEffect(() => {
    if (lockedId) {
      setSid(lockedId);
      lookup(lockedId);
    }
  }, [lockedId]);
  return (
    <div className="space-y-4 w-full">
      <div className="brutal-card p-6">
        <h2 className="font-extrabold uppercase tracking-wider text-xl">STUDENT PORTAL</h2>
        <p className="font-mono text-xs mt-1">ROLL NO. {lockedId}</p>
        <button onClick={() => lookup()} className="brutal-btn mt-3 text-xs">↻ REFRESH</button>
        {err && <p className="font-mono text-xs mt-2">{err}</p>}
      </div>
      {data && (
        <div className="brutal-card overflow-hidden">
          <div className="p-4 border-b-4 border-black bg-[#E2FF00] flex items-center justify-between">
            <div>
              <p className="font-extrabold uppercase tracking-wider">{data.name}</p>
              <p className="font-mono text-xs">{data.student_id} • {data.branch}</p>
            </div>
            <p className="font-extrabold text-2xl">{data.percentage}%</p>
          </div>
          <table className="w-full text-sm bg-white">
            <thead><tr className="bg-black text-[#E2FF00] font-extrabold uppercase tracking-wider text-xs">
              <th className="text-left p-3">SESSION</th><th className="text-left p-3">DATE</th><th className="text-left p-3">STATUS</th>
            </tr></thead>
            <tbody>
              {(data.history || []).map((h) => (
                <tr key={h.session_id} className="border-t-4 border-black bg-white">
                  <td className="p-3">{h.session_name}</td>
                  <td className="p-3 font-mono text-xs">{h.date}</td>
                  <td className="p-3">
                    <span className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-xs font-bold uppercase ${h.status === "Present" ? "bg-[#E2FF00] text-black" : "bg-[#DC2626] text-white"}`}>
                      {h.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
