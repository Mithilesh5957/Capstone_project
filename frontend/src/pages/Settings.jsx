import { useEffect, useState } from "react";
import { detectionSettings, updateDetectionSettings } from "../api/marp";
import { useMARP } from "../context/MARPContext";
import ChaosControlPanel from "../components/ChaosControlPanel";

export default function Settings() {
  const { telemetry, ready, termLog, notify } = useMARP();
  const [cfg, setCfg] = useState(null);
  const [threshold, setThreshold] = useState(0.85);
  const [fps, setFps] = useState(15);
  const [burst, setBurst] = useState(700);
  const [boxes, setBoxes] = useState(true);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    detectionSettings().then((c) => { setCfg(c); if (c.reid_threshold) setThreshold(c.reid_threshold); }).catch(() => setCfg(null));
  }, []);

  const save = async () => {
    try {
      const r = await updateDetectionSettings({ reid_threshold: threshold, min_neighbors: cfg?.min_neighbors ?? 6 });
      setMsg(`SAVED: threshold ${r.reid_threshold}, neighbors ${r.min_neighbors}`);
      notify && notify("Recognition settings saved", "ok");
      try { localStorage.setItem("faceattend_cam", JSON.stringify({ fps, burst, boxes })); } catch { /* ignore */ }
    } catch (e) {
      setMsg(e.message);
    }
  };

  useEffect(() => {
    try {
      const s = JSON.parse(localStorage.getItem("faceattend_cam") || "null");
      if (s) { setFps(s.fps ?? 15); setBurst(s.burst ?? 700); setBoxes(s.boxes ?? true); }
    } catch { /* ignore */ }
  }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="nb-card p-0">
        <div className="border-b-2 border-black bg-neon px-5 py-3">
          <h2 className="nb-title text-sm">SETTINGS & MARP CHAOS HUB</h2>
          <p className="font-mono text-xs">PHASE {telemetry.phase} • STAGE {telemetry.stage || telemetry.marp_state} • {ready ? "200 OK" : "503"}</p>
        </div>
        <ChaosControlPanel />
        <ul className="h-32 overflow-y-auto border-t-2 border-black bg-black p-3 font-mono text-[11px] text-neon">
          {termLog.slice(-30).map((e) => <li key={e.id}>[{e.time}] {e.text}</li>)}
        </ul>
      </div>

      <div className="space-y-4">
        <div className="nb-card p-5">
          <h2 className="nb-title text-sm">RECOGNITION SETTINGS</h2>
          <label className="nb-title mt-3 block text-xs">CONFIDENCE THRESHOLD — {Number(threshold).toFixed(2)} (0.0–1.0)</label>
          <input type="range" min="0" max="1" step="0.01" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} className="w-full accent-black" />
          <div className="mt-1 flex justify-between font-mono text-[11px]"><span>0.0 LOOSE</span><span>1.0 STRICT</span></div>
          {!cfg && <p className="mt-2 font-mono text-xs">BACKEND THRESHOLD SYNC NEEDS /api/v1 (USING LOCAL {threshold}).</p>}
        </div>
        <div className="nb-card p-5">
          <h2 className="nb-title text-sm">CAMERA STREAM SETTINGS</h2>
          <label className="nb-title mt-3 block text-xs">MAX FPS CAP — {fps}</label>
          <input type="range" min="1" max="30" step="1" value={fps} onChange={(e) => setFps(Number(e.target.value))} className="w-full accent-black" />
          <label className="nb-title mt-3 block text-xs">AUTO-CAPTURE BURST DELAY — {burst}ms</label>
          <input type="range" min="200" max="3000" step="100" value={burst} onChange={(e) => setBurst(Number(e.target.value))} className="w-full accent-black" />
          <button onClick={() => setBoxes((v) => !v)} className={`nb-tag mt-3 cursor-pointer ${boxes ? "nb-tag-yellow" : "nb-tag-white"}`}>
            {boxes ? "■ DRAW BOUNDING BOXES ON" : "□ DRAW BOUNDING BOXES OFF"}
          </button>
          <div className="mt-3">
            <button onClick={save} className="nb-btn nb-btn-black">SAVE SETTINGS</button>
            {msg && <p className="mt-2 border-2 border-black bg-paper p-2 font-mono text-xs">{msg}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
