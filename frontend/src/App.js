import { useEffect, useRef, useState } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [telemetry, setTelemetry] = useState({ phase: "starting", model_ready: false, db_connected: false, uptime_s: 0 });
  const [ready, setReady] = useState(null);
  const [latency, setLatency] = useState(null);
  const [chaosMsg, setChaosMsg] = useState("");

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

  // 4. Telemetry poll: startup phase, latency, postgres status
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const t0 = performance.now();
        const [s, h] = await Promise.all([
          fetch(`${API}/api/status`).then((r) => r.json()),
          fetch(`${API}/healthz/readiness`).then((r) => ({ ok: r.ok, body: r.json() })).catch(() => null),
        ]);
        setTelemetry(s);
        setLatency((l) => l ?? Math.round(performance.now() - t0));
        setReady(h ? h.ok : false);
      } catch { setReady(false); }
    }, 2000);
    return () => clearInterval(id);
  }, []);

  const chaos = async (failure) => {
    const r = await fetch(`${API}/api/chaos`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ failure }),
    }).then((r) => r.json()).catch(() => ({ phase: "unreachable" }));
    setChaosMsg(`Chaos [${failure}] -> ${r.phase}`);
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

        {/* RIGHT: DevOps Telemetry Monitor */}
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4 space-y-4 h-fit">
          <h2 className="text-sm font-semibold text-cyan-300">DevOps Telemetry Monitor</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>Startup phase</span><code className="text-amber-300">{telemetry.phase}</code></div>
            <div className="flex justify-between items-center"><span>Model</span><span className={`w-2 h-2 rounded-full ${dot(telemetry.model_ready)}`} /></div>
            <div className="flex justify-between items-center"><span>PostgreSQL</span><span className={`w-2 h-2 rounded-full ${dot(telemetry.db_connected)}`} /></div>
            <div className="flex justify-between"><span>API latency</span><code>{latency ?? "—"} ms</code></div>
            <div className="flex justify-between"><span>Uptime</span><code>{telemetry.uptime_s}s</code></div>
          </div>
          <div className="pt-2 border-t border-zinc-800 space-y-2">
            <p className="text-xs text-zinc-400">Simulate failures:</p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => chaos("db_drop")} className="px-3 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500">Trigger Chaos: DB drop</button>
              <button onClick={() => chaos("model_unload")} className="px-3 py-1.5 text-xs rounded bg-orange-600 hover:bg-orange-500">Unload model</button>
              <button onClick={() => chaos("recover")} className="px-3 py-1.5 text-xs rounded bg-emerald-600 hover:bg-emerald-500">Recover</button>
            </div>
            {chaosMsg && <p className="text-xs text-zinc-400">{chaosMsg}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
