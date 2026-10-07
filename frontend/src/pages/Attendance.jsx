import { useEffect, useRef, useState } from "react";
import { snapshot } from "../api/client";
import { detect, roster, startSession, stopSession } from "../api/attendance";
import { useMARP } from "../context/MARPContext";
import SessionSummaryModal from "../components/SessionSummaryModal";

export default function Attendance({ students, attendanceLogs, refreshLogs }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [stream, setStream] = useState(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const [drawBoxes, setDrawBoxes] = useState(true);
  const { telemetry, ready, notify } = useMARP();

  const startCamera = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) videoRef.current.srcObject = s;
      setStream(s);
      setCameraOn(true);
    } catch {
      notify && notify("Camera blocked — allow webcam access", "err");
    }
  };
  const stopCamera = () => {
    stream?.getTracks().forEach((t) => t.stop());
    setStream(null);
    setCameraOn(false);
  };
  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream]);

  useEffect(() => {
    const c = canvasRef.current, v = videoRef.current;
    if (!c || !v) return;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    if (!drawBoxes) return;
    const sx = c.width / (v.videoWidth || 1), sy = c.height / (v.videoHeight || 1);
    detections.forEach((d) => {
      const [x, y, w, h] = d.bbox;
      ctx.strokeStyle = "#000"; ctx.lineWidth = 4;
      ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
      ctx.fillStyle = "#E2FF00";
      ctx.fillRect(x * sx, y * sy, w * sx, h * sy);
      ctx.strokeStyle = "#000"; ctx.lineWidth = 2;
      ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
      const label = d.label || `${d.name || d.type} ${d.confidence ?? ""}`;
      ctx.font = "bold 12px monospace";
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "#000";
      ctx.fillRect(x * sx, y * sy - 18, tw + 10, 18);
      ctx.fillStyle = "#E2FF00";
      ctx.fillText(label, x * sx + 5, y * sy - 5);
    });
  }, [detections, drawBoxes]);

  useEffect(() => {
    if (!cameraOn) return;
    const id = setInterval(async () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      try {
        const data = await detect(snapshot(v));
        if (data.detections) {
          setDetections(data.detections);
          if (data.detections.length) {
            setLogs((p) => [...data.detections.map((d, i) => ({ ...d, id: Date.now() + i, time: new Date().toLocaleTimeString() })), ...p].slice(0, 20));
            refreshLogs && refreshLogs();
          }
        }
      } catch { /* backend loading */ }
    }, 700);
    return () => clearInterval(id);
  }, [cameraOn, refreshLogs]);

  const present = attendanceLogs.filter((r) => r.status === "Present").length;
  const absent = attendanceLogs.length - present;
  const deptOf = (id) => students.find((s) => s.student_id === id)?.branch || "—";

  return (
    <div className="space-y-4">
      <div className={`flex flex-wrap items-center justify-between gap-2 border-2 border-black p-3 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] ${telemetry.active_session?.id ? "bg-neon" : "bg-white"}`}>
        <p className="nb-title text-sm">
          {telemetry.active_session?.id
            ? `SESSION #${telemetry.active_session.id} ACTIVE — STARTED ${startedAt || "…"} — PRESENT ${present} / ABSENT ${absent}`
            : "NO ACTIVE SESSION — PRESS START CAMERA, THEN END SESSION"}
        </p>
        <div className="flex gap-2">
          {!cameraOn
            ? <button onClick={startCamera} className="nb-btn nb-btn-black text-xs">START CAMERA</button>
            : <button onClick={stopCamera} className="nb-btn nb-btn-white text-xs">STOP CAMERA</button>}
          <button onClick={async () => {
            const r = await startSession("Morning Session");
            setStartedAt(new Date().toLocaleTimeString());
            refreshLogs && refreshLogs();
            notify && notify(`Session #${r.session_id} started`, "ok");
          }} className="nb-btn nb-btn-black text-xs">START SESSION</button>
          <button onClick={async () => {
            const r = await stopSession();
            setSummary(r.summary);
            refreshLogs && refreshLogs();
          }} className="nb-btn nb-btn-red text-xs">END SESSION</button>
          <button onClick={() => setDrawBoxes((v) => !v)} className="nb-tag nb-tag-white cursor-pointer self-center">
            {drawBoxes ? "■ BOXES ON" : "□ DRAW BOXES"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="nb-card p-4">
            <h2 className="nb-title mb-3 text-sm">LIVE CAMERA VIEW {ready === false && <span className="nb-tag nb-tag-red ml-2">MARP 503</span>}</h2>
            <div className="relative overflow-hidden border-2 border-black bg-black">
              {cameraOn
                ? <><video ref={videoRef} autoPlay muted playsInline className="w-full" />
                    <canvas ref={canvasRef} width={640} height={480} className="absolute inset-0 h-full w-full" /></>
                : <button onClick={startCamera} className="flex aspect-video w-full items-center justify-center bg-paper font-mono text-xs font-bold uppercase tracking-wider">
                    ▷ CAMERA OFF — CLICK TO START
                  </button>}
              <video ref={cameraOn ? undefined : videoRef} autoPlay muted playsInline className="hidden" />
              <canvas ref={cameraOn ? undefined : canvasRef} width={640} height={480} className="hidden" />
            </div>
          </div>
          <div className="nb-card p-4">
            <h2 className="nb-title mb-2 text-sm">DETECTION LOG (LIVE)</h2>
            <ul className="h-40 overflow-y-auto border-2 border-black bg-white p-2 font-mono text-xs">
              {logs.length === 0 && <li>NO DETECTIONS YET…</li>}
              {logs.map((l) => <li key={l.id}>[{l.time}] <b>{l.label || l.name}</b> conf={l.confidence} bbox=[{(l.bbox || []).join(",")}]</li>)}
            </ul>
          </div>
        </div>

        <div className="space-y-4">
          <div className="nb-card overflow-hidden">
            <h2 className="border-b-2 border-black bg-black px-4 py-2 nb-title text-xs text-neon">
              REAL-TIME ROLL CALL ({attendanceLogs.length})
            </h2>
            <ul className="max-h-72 divide-y-2 divide-black overflow-y-auto bg-white">
              {attendanceLogs.map((r, i) => (
                <li key={`${r.student_id}-${i}`} className="flex items-center justify-between p-2">
                  <div>
                    <p className="text-sm font-extrabold">{r.name || "—"}</p>
                    <p className="font-mono text-[11px]">{r.student_id} • {r.branch || deptOf(r.student_id)}</p>
                  </div>
                  <span className={`nb-tag ${r.status === "Present" ? "nb-tag-yellow" : "nb-tag-red"}`}>
                    {r.status}{r.confidence ? ` ${(Number(r.confidence) * 100).toFixed(0)}%` : ""}
                  </span>
                </li>
              ))}
              {attendanceLogs.length === 0 && <li className="p-4 font-mono text-xs">EMPTY — FACE THE CAMERA.</li>}
            </ul>
          </div>
        </div>
      </div>

      <SessionSummaryModal summary={summary} onClose={() => setSummary(null)} />
    </div>
  );
}
export { roster };
