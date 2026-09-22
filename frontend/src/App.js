import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// Terminal tone -> color (green 200 OK, red 503/failures, yellow recovering)
const TONE = {
  ok: "text-green-400",
  err: "text-red-400",
  warn: "text-amber-400",
  info: "text-blue-300",
  dim: "text-zinc-500",
};

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [telemetry, setTelemetry] = useState({ phase: "starting", model_ready: false, db_connected: false, uptime_s: 0 });
  const [ready, setReady] = useState(null);
  const [latency, setLatency] = useState(null);
  const [chaosMsg, setChaosMsg] = useState("");

  // ---- DevOps terminal log (timestamped, color-coded, scrollable) ----
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

  // 1. Start webcam
  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ video: true }).then((s) => (videoRef.current.srcObject = s));
  }, []);

  // 2. Draw bounding boxes
  useEffect(() => {
    const c = canvasRef.current, v = videoRef.current;
    if (!c || !v) return;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    const sx = c.width / (v.videoWidth || 1), sy = c.height / (v.videoHeight || 1);
    detections.forEach((d) => {
      const [x, y, w, h] = d.bbox;
      ctx.strokeStyle = "#22ff88"; ctx.lineWidth = 2;
      ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
      ctx.fillStyle = "#22ff88";
      ctx.fillText(`${d.type} ${d.confidence}`, x * sx, y * sy - 4);
    });
  }, [detections]);

  // 3. Detection loop: snapshot -> POST /api/detect (REST; swap to /ws/detect for WS)
  useEffect(() => {
    const id = setInterval(async () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      const off = document.createElement("canvas");
      off.width = 320; off.height = 240;
      off.getContext("2d").drawImage(v, 0, 0, 320, 240);
      const t0 = performance.now();
      try {
        const r = await fetch(`${API}/api/detect`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: off.toDataURL("image/jpeg", 0.7) }),
        });
        const data = await r.json();
        setLatency(Math.round(performance.now() - t0));
        if (data.detections) {
          setDetections(data.detections);
          if (data.detections.length)
            setLogs((p) => [...data.detections.map((d, i) => ({ ...d, id: Date.now() + i, time: new Date().toLocaleTimeString() })), ...p].slice(0, 20));
        }
      } catch { /* backend down / loading */ }
    }, 700);
    return () => clearInterval(id);
  }, []);

  // 4. Telemetry poll: startup phase, latency, postgres status.
  //    Every readiness result is tailed into the DevOps terminal log.
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
                /* non-JSON body */
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

  // Auto-scroll the terminal window to the newest line.
  const termBoxRef = useRef(null);
  useEffect(() => {
    const el = termBoxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [termLog]);

  // 5. Chaos controls -> granular backend endpoints (/api/chaos/db-drop,
  //    /api/chaos/unload-model, /api/chaos/recover). The SYSTEM ADMIN action
  //    line is appended BEFORE the POST so the user sees the command execute
  //    instantly; the backend reply is logged when it arrives.
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
      const r = await fetch(`${API}${endpoints[kind] || "/api/chaos/db-drop"}`, {
        method: "POST",
      }).then((r) => r.json());
      setChaosMsg(`Chaos [${kind}] -> ${r.phase}`);
      pushTerm(`backend: ${r.message || r.phase}`, kind === "recover" ? "warn" : "err");
    } catch {
      setChaosMsg("Chaos request failed (backend unreachable)");
      pushTerm("backend unreachable — command failed", "err");
    }
  };

  const dot = (ok) => (ok ? "bg-emerald-400" : "bg-red-500");
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-4">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">🎥 Real-Time Video Analytics</h1>
        <span className={`px-3 py-1 rounded-full text-xs ${ready ? "bg-emerald-900 text-emerald-300" : "bg-amber-900 text-amber-300"}`}>
          {ready === null ? "…" : ready ? "READY ●" : "LOADING ○"}
        </span>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* LEFT: live feed + logs */}
        <div className="lg:col-span-2 space-y-4">
          <div className="relative rounded-xl overflow-hidden bg-black border border-zinc-800">
            <video ref={videoRef} autoPlay muted playsInline className="w-full" />
            <canvas ref={canvasRef} width={640} height={480} className="absolute inset-0 w-full h-full" />
          </div>
          <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-3">
            <h2 className="text-sm font-semibold mb-2 text-emerald-300">Detection Log (live)</h2>
            <ul className="h-40 overflow-y-auto text-xs font-mono space-y-1">
              {logs.length === 0 && <li className="text-zinc-500">No detections yet…</li>}
              {logs.map((l) => (
                <li key={l.id} className="text-zinc-300">
                  [{l.time}] <span className="text-emerald-400">{l.detection_type || l.type}</span> conf={l.confidence} bbox=[{(l.bbox || []).join(",")}]
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* RIGHT: DevOps Terminal (dark command line) */}
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 overflow-hidden h-fit">
          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-zinc-800 bg-zinc-950">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <span className="ml-1 text-[11px] font-mono text-zinc-500">devops — readiness tail</span>
            <span className={`ml-auto px-2 py-0.5 rounded-full text-[11px] font-bold ${ready ? "bg-green-500/10 text-green-400 border border-green-500/50" : "bg-amber-500/10 text-amber-400 border border-amber-500/50"}`}>
              {ready === null ? "…" : ready ? "READY ●" : "FAILING ○"}
            </span>
            <button onClick={clearTerm} className="text-[11px] font-mono text-zinc-500 hover:text-zinc-200 transition">clear</button>
          </div>
          <ul ref={termBoxRef} className="h-44 overflow-y-auto font-mono text-xs space-y-0.5 p-3 bg-black/60">
            {termLog.map((e) => (
              <li key={e.id} className={TONE[e.tone] || TONE.dim}>[{e.time}] {e.text}</li>
            ))}
          </ul>
          <div className="p-4 space-y-2 border-t border-zinc-800">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span>Startup phase</span><code className="text-amber-300 font-mono text-xs">{telemetry.phase}</code></div>
              <div className="flex justify-between items-center"><span>Model</span><span className={`w-2 h-2 rounded-full ${dot(telemetry.model_ready)}`} /></div>
              <div className="flex justify-between items-center"><span>PostgreSQL</span><span className={`w-2 h-2 rounded-full ${dot(telemetry.db_connected)}`} /></div>
              <div className="flex justify-between"><span>API latency</span><code className="font-mono text-xs">{latency ?? "—"} ms</code></div>
              <div className="flex justify-between"><span>Uptime</span><code className="font-mono text-xs">{telemetry.uptime_s}s</code></div>
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
    </div>
  );
}
