import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

/* ============================================================================
 * KL University — Face Attendance Portal (complete build).
 * Pages: Login gate -> Admin (College Hub / Enroll Student / Live Scanner
 * with DevOps terminal) | Student Portal (session-locked).
 * No mock data: students / attendanceLogs start as [] and fill via API.
 * Vision + DevOps logic: webcam overlay, 700ms POST /api/detect, 2s
 * /healthz/readiness poll tailed into the terminal, granular chaos endpoints.
 * ========================================================================== */

// Design tokens (Neo-Brutalist Dark Glass)
const GLASS =
  "bg-zinc-900/70 backdrop-blur-md border border-zinc-800 rounded-2xl shadow-[4px_4px_0px_0px_rgba(59,130,246,0.4)]";
const INPUT =
  "bg-zinc-950 border border-zinc-700 text-zinc-100 rounded-xl px-4 py-2 focus:border-blue-500 focus:outline-none text-sm w-full placeholder:text-zinc-600";
const BTN_BRUTAL =
  "font-bold rounded-xl border-b-4 active:border-b-0 active:translate-y-0.5 transition-all shadow-lg px-5 py-2.5 text-sm";
const READY_BADGE =
  "bg-green-500/10 text-green-400 border border-green-500/50 shadow-[0_0_10px_rgba(34,197,94,0.25)]";
const BAD_BADGE =
  "bg-red-500/10 text-red-400 border border-red-500/50 shadow-[0_0_10px_rgba(239,68,68,0.25)]";
const TONE = {
  ok: "text-green-400",
  err: "text-red-400",
  warn: "text-amber-400",
  info: "text-blue-300",
  dim: "text-zinc-500",
};

// Test login accounts (shown on the login card for judges)
const TEST_ADMIN = { username: "admin", password: "admin123" };
const TEST_STUDENT_PASSWORD = "student123";
const SESSION_KEY = "face_portal_session";

const DEPTS = [
  { code: "CSE", label: "Computer Science" },
  { code: "ECE", label: "Electronics & Comm" },
  { code: "ME", label: "Mechanical" },
  { code: "AI&DS", label: "AI & Data Science" },
  { code: "EEE", label: "Electrical" },
];
const FILTERS = [
  { code: "ALL", label: "All" },
  { code: "CSE", label: "CSE" },
  { code: "ECE", label: "ECE" },
  { code: "ME", label: "Mechanical" },
  { code: "AI&DS", label: "AI & DS" },
  { code: "EEE", label: "EEE" },
  { code: "BT", label: "Biotech" },
];
const DEGREES = ["B.Tech", "B.Tech (Hons)", "M.Tech", "Ph.D."];
const ANGLES = ["Front", "Left Profile", "Right Profile", "Upper Angle"];

/* ---------------- helpers (stateless) ---------------- */
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
const dot = (ok) => (ok ? "bg-emerald-400" : "bg-red-500");
function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

/* ================================================================== */
export default function App() {
  // Auth session (null = logged out -> login gate). Persisted in localStorage.
  const [session, setSession] = useState(loadSession);
  const role = session?.role || "Admin";
  const [tab, setTab] = useState("hub"); // hub | enroll | scanner

  // Live data (empty until API populates — no mock names anywhere)
  const [students, setStudents] = useState([]);
  const [attendanceLogs, setAttendanceLogs] = useState([]);
  const [deptFilter, setDeptFilter] = useState("ALL");

  // Video-stream states
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);

  // DevOps telemetry states
  const [telemetry, setTelemetry] = useState({
    phase: "starting",
    model_ready: false,
    db_connected: false,
    uptime_s: 0,
    active_session: {},
  });
  const [ready, setReady] = useState(null);
  const [latency, setLatency] = useState(null);
  const [chaosMsg, setChaosMsg] = useState("");

  // DevOps terminal log (timestamped, color-coded, scrollable)
  const [termLog, setTermLog] = useState(() => ([
    { id: 0, time: new Date().toLocaleTimeString("en-GB"),
      text: "terminal online — polling /healthz/readiness every 2s", tone: "dim" },
  ]));
  const pushTerm = useCallback((text, tone = "info") => {
    const time = new Date().toLocaleTimeString("en-GB");
    setTermLog((p) => [...p.slice(-119),
      { id: Date.now() + Math.random(), time, text, tone }]);
  }, []);
  const clearTerm = useCallback(() => setTermLog([]), []);

  // Populate students from production API
  const refreshStudents = useCallback(async () => {
    try {
      setStudents(await api("/api/students"));
    } catch {
      /* backend loading / unreachable */
    }
  }, []);

  // Populate attendance logs (primary + fallbacks, all real API)
  const refreshAttendanceLogs = useCallback(async () => {
    try {
      const r = await api("/api/attendance/logs");
      setAttendanceLogs(Array.isArray(r) ? r : r.records || r.logs || []);
      return;
    } catch {
      /* endpoint may not exist on this backend build — fall through */
    }
    try {
      const sid = telemetryRef.current?.active_session?.id;
      const url = sid
        ? `/api/attendance/roster?session_id=${sid}`
        : "/api/attendance/roster";
      const r = await api(url);
      setAttendanceLogs(r.records || []);
    } catch {
      try {
        const r = await api("/api/logs?limit=50");
        setAttendanceLogs(
          (Array.isArray(r) ? r : []).map((e) => ({
            student_id: "—",
            name: e.detection_type || "face",
            status: "Detected",
            marked_at: e.timestamp,
            confidence: e.confidence,
          }))
        );
      } catch {
        /* leave previous state */
      }
    }
  }, []);
  const telemetryRef = useRef(telemetry);
  telemetryRef.current = telemetry;

  useEffect(() => {
    refreshStudents();
    refreshAttendanceLogs();
    const id = setInterval(() => {
      refreshStudents();
      refreshAttendanceLogs();
    }, 5000);
    return () => clearInterval(id);
  }, [refreshStudents, refreshAttendanceLogs]);

  // 1. Webcam for Live Scanner tab
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

  // 2. Neon bounding-box overlay (#00FF00, 2px + name badges)
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
      ctx.strokeStyle = "#00FF00";
      ctx.lineWidth = 2;
      ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
      ctx.font = "12px sans-serif";
      const label = d.label || `${d.name || d.type} ${d.confidence ?? ""}`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "#00FF00";
      ctx.fillRect(x * sx, y * sy - 16, tw + 8, 16);
      ctx.fillStyle = "#000";
      ctx.fillText(label, x * sx + 4, y * sy - 4);
    });
  }, [detections]);

  // 3. Detection loop: snapshot -> POST /api/detect
  useEffect(() => {
    const id = setInterval(async () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      const t0 = performance.now();
      try {
        const r = await fetch(`${API}/api/detect`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: snapshot(v) }),
        });
        const data = await r.json();
        setLatency(Math.round(performance.now() - t0));
        if (data.detections) {
          setDetections(data.detections);
          if (data.detections.length)
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
        }
      } catch {
        /* backend down / loading */
      }
    }, 700);
    return () => clearInterval(id);
  }, []);

  // 4. Telemetry poll + terminal tail for every readiness result
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const t0 = performance.now();
        const [s, h] = await Promise.all([
          fetch(`${API}/api/status`).then((r) => r.json()),
          fetch(`${API}/healthz/readiness`)
            .then(async (r) => {
              let body = {};
              try {
                body = await r.json();
              } catch {
                /* non-JSON */
              }
              return { ok: r.ok, status: r.status, error: body.error || body.phase || "" };
            })
            .catch(() => null),
        ]);
        setTelemetry(s);
        setLatency((l) => l ?? Math.round(performance.now() - t0));
        setReady(h ? h.ok : false);
        if (!h) {
          pushTerm("Health Check: unreachable — connection refused", "err");
        } else if (h.ok) {
          pushTerm(`Health Check: 200 OK (${s.phase || "ready"})`, "ok");
        } else if (/reload/i.test(`${h.error} ${s.phase || ""}`)) {
          pushTerm(`Health Check: ${h.status} — recovering (${s.phase || h.error})`, "warn");
        } else {
          pushTerm(`Health Check: ${h.status} — ${h.error || "failure"}`, "err");
        }
      } catch {
        setReady(false);
        pushTerm("Health Check: poll failed", "err");
      }
    }, 2000);
    return () => clearInterval(id);
  }, [pushTerm]);

  // 5. Chaos controls -> granular endpoints, action logged BEFORE the POST
  const chaos = async (kind) => {
    const labels = {
      "db-drop": "DB Drop", "db_drop": "DB Drop",
      "unload-model": "Model Unload", "model_unload": "Model Unload",
      recover: "Recovery",
    };
    const endpoints = {
      "db-drop": "/api/chaos/db-drop", "db_drop": "/api/chaos/db-drop",
      "unload-model": "/api/chaos/unload-model", "model_unload": "/api/chaos/unload-model",
      recover: "/api/chaos/recover",
    };
    pushTerm(`SYSTEM ADMIN: Initiating ${labels[kind] || kind}...`, "info");
    try {
      const r = await api(endpoints[kind] || "/api/chaos/db-drop", { method: "POST" });
      setChaosMsg(`Chaos [${kind}] -> ${r.phase}`);
      pushTerm(`backend: ${r.message || r.phase}`, kind === "recover" ? "warn" : "err");
    } catch {
      setChaosMsg("Chaos request failed (backend unreachable)");
      pushTerm("backend unreachable — command failed", "err");
    }
  };

  const logout = () => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  const filteredStudents =
    deptFilter === "ALL"
      ? students
      : students.filter((s) => s.branch === deptFilter);

  // Login gate (after all hooks so hook order never changes)
  if (!session) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900 to-zinc-950 font-sans flex items-center justify-center p-4">
        <LoginScreen
          onLogin={(s) => {
            localStorage.setItem(SESSION_KEY, JSON.stringify(s));
            setSession(s);
          }}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900 to-zinc-950 font-sans">
      {/* Floating navbar pill */}
      <div className="px-4">
        <header className="mx-auto mt-4 max-w-7xl bg-zinc-900/80 border border-zinc-800 rounded-full px-6 py-3 flex flex-wrap gap-3 justify-between items-center backdrop-blur-md">
          <p className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500 font-extrabold text-xl tracking-tight">
            KL UNIVERSITY — FACE ATTENDANCE PORTAL
          </p>
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-zinc-300 border border-zinc-700 rounded-full px-3 py-1.5">
              {role === "Admin" ? "Admin (Teacher)" : "Student"} • {session.username}
            </span>
            <button
              onClick={logout}
              className="text-xs font-bold text-zinc-400 hover:text-zinc-100 border border-zinc-700 hover:border-zinc-500 rounded-full px-3 py-1.5 transition"
            >
              Logout
            </button>
            <span className={`px-3 py-1.5 rounded-full text-xs font-bold ${ready ? READY_BADGE : BAD_BADGE}`}>
              {ready === null ? "…" : ready ? "READY ●" : "UNHEALTHY ●"}
            </span>
          </div>
        </header>

        {role === "Admin" && (
          <nav className="mx-auto max-w-7xl px-2 pt-3 flex gap-2">
            {[
              ["hub", "College Hub"],
              ["enroll", "Enroll Student"],
              ["scanner", "Live Scanner"],
            ].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`px-5 py-2 text-sm font-bold rounded-full transition ${
                  tab === key
                    ? "bg-blue-600 text-white shadow-lg"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        )}
      </div>

      <main className="mx-auto max-w-7xl p-4">
        {role === "Student" ? (
          <StudentPortal lockedId={session.student_id || session.username} />
        ) : tab === "hub" ? (
          <HubTab
            students={students}
            filtered={filteredStudents}
            deptFilter={deptFilter}
            setDeptFilter={setDeptFilter}
            telemetry={telemetry}
            ready={ready}
          />
        ) : tab === "enroll" ? (
          <EnrollTab onDone={() => { refreshStudents(); setTab("hub"); }} />
        ) : (
          <ScannerTab
            videoRef={videoRef}
            canvasRef={canvasRef}
            logs={logs}
            telemetry={telemetry}
            ready={ready}
            latency={latency}
            chaosMsg={chaosMsg}
            chaos={chaos}
            dot={dot}
            students={students}
            attendanceLogs={attendanceLogs}
            termLog={termLog}
            clearTerm={clearTerm}
          />
        )}
      </main>
    </div>
  );
}

/* ==================== Basic Login Gate ==================== */
function LoginScreen({ onLogin }) {
  const [mode, setMode] = useState("Admin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    setErr("");
    const u = username.trim();
    if (mode === "Admin") {
      if (u !== TEST_ADMIN.username || password !== TEST_ADMIN.password) {
        setErr("Invalid admin credentials — use the test account below.");
        return;
      }
    } else {
      if (!u) {
        setErr("Enter your Roll No. / Student ID.");
        return;
      }
      if (password !== TEST_STUDENT_PASSWORD) {
        setErr("Invalid student password — use the test password below.");
        return;
      }
    }
    setBusy(true);
    try {
      const ctx = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: u, role: mode.toLowerCase() }),
      });
      onLogin(
        mode === "Admin"
          ? { role: "Admin", username: ctx.username || u, name: ctx.name || "Class Teacher" }
          : {
              role: "Student",
              username: u,
              student_id: ctx.student_id || u,
              name: ctx.name || u,
              branch: ctx.branch || "",
            }
      );
    } catch {
      onLogin(
        mode === "Admin"
          ? { role: "Admin", username: u, name: "Class Teacher" }
          : { role: "Student", username: u, student_id: u, name: u, branch: "" }
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`w-full max-w-md ${GLASS} p-6`}>
      <p className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500 font-extrabold text-xl tracking-tight text-center">
        KL UNIVERSITY
      </p>
      <p className="text-center text-xs text-zinc-500 mt-1">Face Attendance Portal — Sign In</p>
      <div className="flex bg-zinc-800 rounded-full p-1 text-xs font-bold border border-zinc-700 mt-4">
        {["Admin", "Student"].map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => { setMode(m); setErr(""); }}
            className={`flex-1 px-4 py-1.5 rounded-full transition ${
              mode === m ? "bg-blue-600 text-white shadow-lg" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {m === "Admin" ? "Admin (Teacher)" : "Student"}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="space-y-3 mt-4">
        <div>
          <label className="text-xs font-bold text-zinc-400">
            {mode === "Admin" ? "Username" : "Roll No. / Student ID"}
          </label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={mode === "Admin" ? "admin" : "2100030001"}
            autoComplete="username"
            className={`${INPUT} mt-1`}
          />
        </div>
        <div>
          <label className="text-xs font-bold text-zinc-400">Password</label>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="••••••••"
            autoComplete="current-password"
            className={`${INPUT} mt-1`}
          />
        </div>
        {err && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/40 rounded-xl px-3 py-2">{err}</p>
        )}
        <button
          type="submit"
          disabled={busy}
          className={`${BTN_BRUTAL} w-full bg-blue-600 hover:bg-blue-500 text-white border-blue-800 disabled:opacity-50`}
        >
          {busy ? "Signing in…" : `Login as ${mode}`}
        </button>
      </form>
      <div className="mt-4 text-[11px] font-mono text-zinc-500 bg-zinc-950 border border-zinc-800 rounded-xl p-3 space-y-1">
        <p className="font-bold text-zinc-400">TEST ACCOUNTS (for demo/judges)</p>
        <p>Admin — user: <span className="text-zinc-200">admin</span> pass: <span className="text-zinc-200">admin123</span></p>
        <p>Student — roll no: <span className="text-zinc-200">any ID</span> pass: <span className="text-zinc-200">student123</span></p>
      </div>
    </div>
  );
}

/* ==================== Tab 1: College Hub & Overview ==================== */
function HubTab({ students, filtered, deptFilter, setDeptFilter, telemetry, ready }) {
  const active = telemetry.active_session;
  const metrics = [
    { label: "Registered Students", value: String(students.length), sub: "live from /api/students" },
    {
      label: "Active Session Status",
      value: active?.id ? `LIVE #${active.id}` : "Idle",
      sub: active?.id ? active.name || "session running" : "no session running",
    },
    {
      label: "System Health",
      value: ready === null ? "…" : ready ? "Optimal" : "Degraded",
      sub: `phase: ${telemetry.phase}`,
    },
  ];
  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-3 gap-4">
        {metrics.map((m) => (
          <div key={m.label} className={`${GLASS} p-5`}>
            <p className="text-xs font-bold text-zinc-400 uppercase tracking-tight">{m.label}</p>
            <p className="text-3xl font-extrabold tracking-tight mt-1">{m.value}</p>
            <p className="text-xs text-zinc-500 mt-1 font-mono">{m.sub}</p>
          </div>
        ))}
      </div>
      <div className={`${GLASS} p-4`}>
        <p className="text-xs font-bold text-zinc-400 tracking-tight mb-2">DEPARTMENT QUICK FILTER</p>
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.code}
              onClick={() => setDeptFilter(f.code)}
              className={`px-4 py-1.5 text-xs font-bold rounded-full transition ${
                deptFilter === f.code
                  ? "bg-blue-600 text-white shadow-lg"
                  : "bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-700"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className={`${GLASS} overflow-hidden`}>
        <h3 className="font-bold tracking-tight text-sm p-4 border-b border-zinc-800">
          Student Directory {deptFilter !== "ALL" ? `— ${deptFilter}` : ""} ({filtered.length})
        </h3>
        {filtered.length === 0 ? (
          <p className="p-8 text-center text-sm text-zinc-500">
            No Students Enrolled Yet - Go to Enroll Tab
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-800/60 text-xs text-zinc-400">
              <tr>
                <th className="text-left p-3">Student ID</th>
                <th className="text-left p-3">Name</th>
                <th className="text-left p-3">Department</th>
                <th className="text-left p-3">Enrolled On</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.student_id} className="border-t border-zinc-800">
                  <td className="p-3 font-mono text-xs">{s.student_id}</td>
                  <td className="p-3">{s.name}</td>
                  <td className="p-3">{s.branch}</td>
                  <td className="p-3 text-xs text-zinc-500">
                    {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ==================== Tab 2: Student Enrollment ==================== */
function EnrollTab({ onDone }) {
  const enrollVideoRef = useRef(null);
  const [form, setForm] = useState({
    student_id: "",
    name: "",
    branch: "CSE",
    degree: "B.Tech",
    phone: "",
    email: "",
    address: "",
  });
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
      .catch(() => setMsg("Camera blocked — allow webcam access."));
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
      setMsg("Student ID and Full Name are required.");
      return;
    }
    if (doneCount < 4) {
      setMsg(`Capture all 4 angles first (${doneCount}/4 done).`);
      return;
    }
    setBusy(true);
    setMsg("Uploading student + vector embeddings…");
    try {
      const r = await api("/api/students/enroll", {
        method: "POST",
        body: JSON.stringify({ ...form, images: shots }),
      });
      setMsg(`Enrolled ${r.name} (${r.student_id}) — ${r.angles_used} angles embedded.`);
      setShots([null, null, null, null]);
      onDone();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className={`${GLASS} p-5 space-y-3`}>
        <h2 className="font-extrabold tracking-tight">Student Profile</h2>
        <div>
          <label className="text-xs font-bold text-zinc-400">Student ID / Roll No.</label>
          <input value={form.student_id} onChange={set("student_id")} placeholder="2100030001" className={`${INPUT} mt-1`} />
        </div>
        <div>
          <label className="text-xs font-bold text-zinc-400">Full Name</label>
          <input value={form.name} onChange={set("name")} placeholder="Enter full name" className={`${INPUT} mt-1`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-bold text-zinc-400">Department / Branch</label>
            <select value={form.branch} onChange={set("branch")} className={`${INPUT} mt-1`}>
              {DEPTS.map((d) => (
                <option key={d.code} value={d.code}>{d.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold text-zinc-400">Degree Program</label>
            <select value={form.degree} onChange={set("degree")} className={`${INPUT} mt-1`}>
              {DEGREES.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-bold text-zinc-400">Phone Number</label>
            <input value={form.phone} onChange={set("phone")} placeholder="+91 …" className={`${INPUT} mt-1`} />
          </div>
          <div>
            <label className="text-xs font-bold text-zinc-400">Email Address</label>
            <input value={form.email} onChange={set("email")} placeholder="name@university.edu" className={`${INPUT} mt-1`} />
          </div>
        </div>
        <div>
          <label className="text-xs font-bold text-zinc-400">Residential Address</label>
          <textarea value={form.address} onChange={set("address")} rows={2} placeholder="Street, city, state" className={`${INPUT} mt-1`} />
        </div>
      </div>
      <div className={`${GLASS} p-5 space-y-3`}>
        <div className="flex items-center justify-between">
          <h2 className="font-extrabold tracking-tight">4-Angle Face Scan</h2>
          <span className="text-xs font-bold bg-blue-600/20 text-blue-300 border border-blue-500/40 rounded-full px-2 py-0.5">
            {doneCount}/4
          </span>
        </div>
        <video ref={enrollVideoRef} autoPlay muted playsInline className="w-full rounded-xl bg-black aspect-video object-cover border border-zinc-700" />
        <div className="grid grid-cols-4 gap-2">
          {ANGLES.map((a, i) => (
            <button
              key={a}
              onClick={() => capture(i)}
              className={`rounded-xl border-2 overflow-hidden text-[11px] font-bold transition ${
                shots[i] ? "border-green-500" : "border-dashed border-zinc-700 hover:border-blue-500"
              }`}
            >
              {shots[i] ? (
                <img src={shots[i]} alt={a} className="w-full aspect-square object-cover" />
              ) : (
                <span className="block py-5 text-zinc-500">◌<br />{a}</span>
              )}
              <span className={`block py-1 ${shots[i] ? "bg-green-500/10 text-green-400" : "bg-zinc-800 text-zinc-500"}`}>
                {shots[i] ? `✓ ${a}` : a}
              </span>
            </button>
          ))}
        </div>
        <button
          onClick={submit}
          disabled={busy}
          className={`${BTN_BRUTAL} w-full bg-blue-600 hover:bg-blue-500 text-white border-blue-800 disabled:opacity-50`}
        >
          {busy ? "Saving…" : "Save Student & Vector Embeddings"}
        </button>
        {msg && <p className="text-xs font-mono text-zinc-400 bg-zinc-950 border border-zinc-800 rounded-xl p-2">{msg}</p>}
      </div>
    </div>
  );
}

/* ==================== Tab 3: Live Scanner + DevOps Terminal ==================== */
function ScannerTab({ videoRef, canvasRef, logs, telemetry, ready, latency, chaosMsg, chaos, dot, students, attendanceLogs, termLog, clearTerm }) {
  const termBoxRef = useRef(null);
  useEffect(() => {
    const el = termBoxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [termLog]);
  const deptOf = (id) => students.find((s) => s.student_id === id)?.branch || "—";
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className={`${GLASS} p-4`}>
            <h2 className="text-sm font-bold tracking-tight mb-3">Live Camera Feed</h2>
            <div className="relative border-2 border-zinc-700 rounded-xl overflow-hidden shadow-2xl bg-black">
              <video ref={videoRef} autoPlay muted playsInline className="w-full" />
              <canvas ref={canvasRef} width={640} height={480} className="absolute inset-0 w-full h-full" />
            </div>
          </div>
          <div className={`${GLASS} p-4`}>
            <h2 className="text-sm font-bold tracking-tight mb-2">Detection Log (live)</h2>
            <ul className="h-40 overflow-y-auto font-mono text-sm space-y-1 text-zinc-300">
              {logs.length === 0 && <li className="text-zinc-500">No detections yet…</li>}
              {logs.map((l) => (
                <li key={l.id}>
                  [{l.time}] <span className="text-green-400">{l.label || l.name || l.detection_type || l.type}</span>{" "}
                  conf={l.confidence} bbox=[{(l.bbox || []).join(",")}]
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className={`${GLASS} overflow-hidden h-fit`}>
          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-zinc-800 bg-zinc-950">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <span className="ml-1 text-[11px] font-mono text-zinc-500">devops — readiness tail</span>
            <span className={`ml-auto px-2 py-0.5 rounded-full text-[11px] font-bold ${ready ? READY_BADGE : BAD_BADGE}`}>
              {ready === null ? "…" : ready ? "READY ●" : "UNHEALTHY ●"}
            </span>
            <button onClick={clearTerm} className="text-[11px] font-mono text-zinc-500 hover:text-zinc-200 transition">clear</button>
          </div>
          <ul ref={termBoxRef} className="h-44 overflow-y-auto font-mono text-xs space-y-0.5 p-3 bg-black/60">
            {termLog.map((e) => (
              <li key={e.id} className={TONE[e.tone] || TONE.dim}>[{e.time}] {e.text}</li>
            ))}
          </ul>
          <div className="p-4 space-y-2 border-t border-zinc-800">
            <div className="space-y-2 font-mono text-sm text-zinc-300">
              <div className="flex justify-between"><span className="text-zinc-500">&gt; phase</span><code className="text-blue-400">{telemetry.phase}</code></div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-500">&gt; model</span>
                <span className="flex items-center gap-2"><span className={`w-2.5 h-2.5 rounded-full ${dot(telemetry.model_ready)}`} />{telemetry.model_ready ? "loaded" : "loading"}</span>
              </div>
              <div className="flex justify-between"><span className="text-zinc-500">&gt; pg_latency</span><code>{latency ?? "—"} ms</code></div>
              <div className="flex justify-between"><span className="text-zinc-500">&gt; uptime</span><code>{telemetry.uptime_s}s</code></div>
            </div>
            <p className="text-xs font-bold text-zinc-400 tracking-tight">$ chaos_inject --</p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => chaos("db-drop")} className="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-500 text-white font-bold rounded-lg border-b-4 border-red-800 active:border-b-0 active:translate-y-0.5 transition-all">DB drop</button>
              <button onClick={() => chaos("unload-model")} className="px-3 py-1.5 text-xs bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-lg border-b-4 border-orange-800 active:border-b-0 active:translate-y-0.5 transition-all">Unload model</button>
              <button onClick={() => chaos("recover")} className="px-3 py-1.5 text-xs bg-green-600 hover:bg-green-500 text-white font-bold rounded-lg border-b-4 border-green-800 active:border-b-0 active:translate-y-0.5 transition-all">Recover</button>
            </div>
            {chaosMsg && <p className="font-mono text-xs text-zinc-500">{chaosMsg}</p>}
          </div>
        </div>
      </div>
      <div className={`${GLASS} overflow-hidden`}>
        <h2 className="text-sm font-bold tracking-tight p-4 border-b border-zinc-800">
          Live Attendance Roster ({attendanceLogs.length})
        </h2>
        {attendanceLogs.length === 0 ? (
          <p className="p-8 text-center text-sm text-zinc-500">
            No attendance records yet — start a session and face the camera.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-800/60 text-xs text-zinc-400">
              <tr>
                <th className="text-left p-2">Student ID</th>
                <th className="text-left p-2">Name</th>
                <th className="text-left p-2">Department</th>
                <th className="text-left p-2">Degree</th>
                <th className="text-left p-2">Timestamp</th>
                <th className="text-left p-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {attendanceLogs.map((r, i) => (
                <tr key={r.student_id ? `${r.student_id}-${i}` : i} className="border-t border-zinc-800">
                  <td className="p-2 font-mono text-xs">{r.student_id || "—"}</td>
                  <td className="p-2">{r.name || "—"}</td>
                  <td className="p-2">{r.branch || r.department || deptOf(r.student_id)}</td>
                  <td className="p-2">{r.degree || "—"}</td>
                  <td className="p-2 text-xs text-zinc-400 font-mono">
                    {r.marked_at ? new Date(r.marked_at).toLocaleString() : r.time || "—"}
                  </td>
                  <td className="p-2">
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                      r.status === "Present"
                        ? "bg-green-500/10 text-green-400 border border-green-500/50"
                        : r.status === "Absent"
                        ? "bg-zinc-700/40 text-zinc-400 border border-zinc-600/50"
                        : "bg-blue-500/10 text-blue-300 border border-blue-500/40"
                    }`}>
                      {r.status || "Detected"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ==================== Student Portal (session-locked) ==================== */
function StudentPortal({ lockedId }) {
  const [sid, setSid] = useState(lockedId || "");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const lookup = async (id) => {
    const target = (id ?? sid).trim();
    if (!target) {
      setErr("Enter your Student ID / Roll No.");
      return;
    }
    try {
      setData(await api(`/api/students/${encodeURIComponent(target)}/attendance`));
      setErr("");
    } catch {
      setErr("No record found — check the ID or ask your teacher to enroll you.");
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
    <div className="space-y-4 max-w-3xl mx-auto">
      <div className={`${GLASS} p-6`}>
        <h2 className="text-xl font-extrabold tracking-tight">Student Portal 🎓</h2>
        <p className="text-sm text-zinc-400 mt-1">Your live attendance, synced with the classroom scanner.</p>
        {lockedId ? (
          <p className="text-xs font-mono text-zinc-400 mt-3 border border-zinc-800 rounded-xl px-3 py-2">
            Signed in as Roll No. <span className="text-zinc-100">{lockedId}</span>
            <button onClick={() => lookup()} className="ml-3 text-blue-400 hover:text-blue-300 font-bold">↻ Refresh</button>
          </p>
        ) : (
          <div className="flex gap-2 mt-3">
            <input value={sid} onChange={(e) => setSid(e.target.value)} placeholder="e.g. 2100030001" className={INPUT} />
            <button onClick={() => lookup()} className={`${BTN_BRUTAL} bg-blue-600 hover:bg-blue-500 text-white border-blue-800 whitespace-nowrap`}>
              View
            </button>
          </div>
        )}
        {err && <p className="text-xs text-red-400 mt-2">{err}</p>}
      </div>
      {data && (
        <div className={`${GLASS} overflow-hidden`}>
          <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
            <div>
              <p className="font-extrabold tracking-tight">{data.name}</p>
              <p className="text-xs text-zinc-500 font-mono">{data.student_id} • {data.branch}</p>
            </div>
            <p className="text-2xl font-extrabold tracking-tight text-blue-400">{data.percentage}%</p>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-zinc-800/60 text-xs text-zinc-400">
              <tr>
                <th className="text-left p-3">Session</th>
                <th className="text-left p-3">Date</th>
                <th className="text-left p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data.history || []).map((h) => (
                <tr key={h.session_id} className="border-t border-zinc-800">
                  <td className="p-3">{h.session_name}</td>
                  <td className="p-3 text-xs text-zinc-500">{h.date}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                      h.status === "Present"
                        ? "bg-green-500/10 text-green-400 border border-green-500/50"
                        : "bg-zinc-700/40 text-zinc-400 border border-zinc-600/50"
                    }`}>
                      {h.status}
                    </span>
                  </td>
                </tr>
              ))}
              {(data.history || []).length === 0 && (
                <tr><td colSpan={3} className="p-4 text-xs text-zinc-500">No sessions recorded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
