import { useCallback, useEffect, useRef, useState } from "react";
import { API, snapshot } from "../api/client";
import { detect, roster, startSession, stopSession } from "../api/attendance";
import { useAuth } from "../context/AuthContext";
import { useMARP } from "../context/MARPContext";
import SessionSummaryModal from "../components/SessionSummaryModal";

function getJwt(session) {
  if (session?.token) return session.token;
  try {
    const raw = localStorage.getItem("face_portal_session");
    const s = JSON.parse(raw || "null");
    return s?.token || "";
  } catch {
    return "";
  }
}

function buildWsUrl(apiBase, token) {
  const base = (apiBase || "http://localhost:8000").replace(/\/$/, "");
  const wsBase = base.replace(/^http/, "ws");
  const path = base.endsWith("/api/v1")
    ? `${wsBase}/attendance/ws/detect`
    : `${wsBase}/api/v1/attendance/ws/detect`;
  return `${path}?token=${encodeURIComponent(token || "")}`;
}

export default function Attendance({ students, attendanceLogs, refreshLogs }) {
  const { session } = useAuth();
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const awaitingAck = useRef(false);
  const ackTimer = useRef(null);
  const nextTimer = useRef(null);
  const httpTimer = useRef(null);

  const [cameraOn, setCameraOn] = useState(false);
  const [stream, setStream] = useState(null);
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [liveRoster, setLiveRoster] = useState({});
  const [wsStatus, setWsStatus] = useState("OFF");
  const [useHttp, setUseHttp] = useState(false);
  const [summary, setSummary] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const [drawBoxes, setDrawBoxes] = useState(true);
  const { telemetry, ready, notify } = useMARP();

  const clearTimers = () => {
    if (ackTimer.current) clearTimeout(ackTimer.current);
    if (nextTimer.current) clearTimeout(nextTimer.current);
    if (httpTimer.current) clearInterval(httpTimer.current);
    ackTimer.current = nextTimer.current = httpTimer.current = null;
  };

  const closeWs = () => {
    try {
      wsRef.current?.close();
    } catch { /* ignore */ }
    wsRef.current = null;
    awaitingAck.current = false;
  };

  // ---- frame sender with adaptive backpressure ----
  const sendNextFrame = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (awaitingAck.current) return; // wait for ack or 1s timeout
    const v = videoRef.current;
    if (!v || !v.videoWidth) {
      nextTimer.current = setTimeout(sendNextFrame, 250);
      return;
    }
    try {
      ws.send(JSON.stringify({ image: snapshot(v, 320, 240) }));
      awaitingAck.current = true;
      if (ackTimer.current) clearTimeout(ackTimer.current);
      ackTimer.current = setTimeout(() => {
        // 1s ack timeout: drop the stale frame, allow the next one.
        awaitingAck.current = false;
        sendNextFrame();
      }, 1000);
    } catch {
      awaitingAck.current = false;
    }
  }, []);

  const handleDetections = useCallback((dets, newlyMarked) => {
    setDetections(dets || []);
    if ((dets || []).length) {
      const now = new Date();
      setLogs((p) => [...dets.map((d, i) => ({
        ...d, id: Date.now() + i, time: now.toLocaleTimeString(),
      })), ...p].slice(0, 20));
    }
    const fresh = {};
    const t = Date.now();
    for (const d of dets || []) {
      if (!d.student_id) continue;
      const dist = d.distance;
      const matchPct = dist == null ? Math.round((d.confidence || 0) * 100)
        : Math.max(0, Math.round((1 - Math.min(1.5, Number(dist)) / 1.5) * 100));
      fresh[d.student_id] = {
        student_id: d.student_id, name: d.name || "Unknown",
        matchPct, distance: dist, confidence: d.confidence,
        lastSeen: t, isNew: (newlyMarked || []).includes(d.student_id),
      };
    }
    if (Object.keys(fresh).length) {
      setLiveRoster((prev) => {
        const next = { ...prev };
        for (const [k, v] of Object.entries(fresh)) next[k] = { ...(next[k] || {}), ...v };
        return next;
      });
      if ((newlyMarked || []).length && refreshLogs) refreshLogs();
    }
  }, [refreshLogs]);

  const connectWs = useCallback(() => {
    closeWs();
    clearTimers();
    const token = getJwt(session);
    if (!token) {
      setWsStatus("DENIED");
      notify && notify("Missing JWT — login again to enable live feed", "err");
      return;
    }
    setWsStatus("CONNECTING");
    setUseHttp(false);
    let ws;
    try {
      ws = new WebSocket(buildWsUrl(API, token));
    } catch {
      setWsStatus("ERROR");
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => {
      setWsStatus("LIVE");
      awaitingAck.current = false;
      sendNextFrame();
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.error && !data.detections) return; // nack, keep waiting for timeout
        if (ackTimer.current) clearTimeout(ackTimer.current);
        awaitingAck.current = false;
        handleDetections(data.detections || [], data.newly_marked || []);
        if (nextTimer.current) clearTimeout(nextTimer.current);
        nextTimer.current = setTimeout(sendNextFrame, 80);
      } catch {
        awaitingAck.current = false;
      }
    };
    ws.onerror = () => { /* onclose handles fallback */ };
    ws.onclose = (ev) => {
      if (ackTimer.current) clearTimeout(ackTimer.current);
      awaitingAck.current = false;
      if (ev.code === 4401) {
        setWsStatus("DENIED");
        notify && notify("WS auth rejected (4401) — invalid token", "err");
        return;
      }
      // Graceful HTTP fallback so the tab never locks up.
      if (videoRef.current?.videoWidth) {
        setWsStatus("HTTP-FALLBACK");
        setUseHttp(true);
      } else {
        setWsStatus("ERROR");
      }
    };
  }, [session, notify, sendNextFrame, handleDetections]);

  const startCamera = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) videoRef.current.srcObject = s;
      setStream(s);
      setCameraOn(true);
      connectWs();
    } catch {
      notify && notify("Camera blocked — allow webcam access", "err");
    }
  };

  const stopCamera = () => {
    closeWs();
    clearTimers();
    setWsStatus("OFF");
    setUseHttp(false);
    stream?.getTracks().forEach((t) => t.stop());
    setStream(null);
    setCameraOn(false);
    setDetections([]);
  };

  useEffect(() => () => {
    closeWs();
    clearTimers();
    stream?.getTracks().forEach((t) => t.stop());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconnect WS if JWT arrives after login refresh.
  useEffect(() => {
    if (cameraOn && (wsStatus === "DENIED" || wsStatus === "ERROR") && session?.token) connectWs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.token]);

  // HTTP fallback polling (only when WS unavailable).
  useEffect(() => {
    if (!cameraOn || !useHttp) return;
    httpTimer.current = setInterval(async () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      try {
        const data = await detect(snapshot(v, 320, 240));
        if (data.detections) handleDetections(data.detections, []);
      } catch { /* backend loading */ }
    }, 900);
    return () => { if (httpTimer.current) clearInterval(httpTimer.current); };
  }, [cameraOn, useHttp, handleDetections]);

  // ---- bounding-box overlay (canvas synced to video resolution) ----
  useEffect(() => {
    const c = canvasRef.current, v = videoRef.current;
    if (!c || !v) return;
    const vw = v.videoWidth || 640, vh = v.videoHeight || 480;
    if (c.width !== vw) c.width = vw;
    if (c.height !== vh) c.height = vh;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    if (!drawBoxes) return;
    // Backend bboxes are in 640x480 canonical space (stretched resize).
    const sx = c.width / 640, sy = c.height / 480;
    detections.forEach((d) => {
      if (!d.bbox) return;
      const [x, y, w, h] = d.bbox.map(Number);
      const dx = x * sx, dy = y * sy, dw = w * sx, dh = h * sy;
      ctx.strokeStyle = "#000"; ctx.lineWidth = Math.max(3, c.width / 160);
      ctx.strokeRect(dx, dy, dw, dh);
      ctx.fillStyle = "#E2FF00";
      ctx.fillRect(dx, dy, dw, Math.max(18, 8 * sy + 10));
      ctx.strokeStyle = "#000"; ctx.lineWidth = 2;
      ctx.strokeRect(dx, dy, dw, dh);
      const label = d.label || `${d.name || d.type || "face"} ${d.confidence ?? ""}`;
      ctx.font = `bold ${Math.max(12, c.width / 53)}px monospace`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "#000";
      ctx.fillRect(dx, Math.max(0, dy - 20), tw + 10, 20);
      ctx.fillStyle = "#E2FF00";
      ctx.fillText(label, dx + 5, Math.max(14, dy - 6));
    });
  }, [detections, drawBoxes, cameraOn]);

  const present = attendanceLogs.filter((r) => r.status === "Present").length;
  const absent = attendanceLogs.length - present;
  const deptOf = (id) => students.find((s) => s.student_id === id)?.branch || "—";
  const liveList = Object.values(liveRoster).sort((a, b) => b.lastSeen - a.lastSeen);
  const wsBadge = wsStatus === "LIVE"
    ? <span className="nb-tag nb-tag-yellow ml-2">WS LIVE</span>
    : wsStatus === "HTTP-FALLBACK"
      ? <span className="nb-tag nb-tag-white ml-2">HTTP FALLBACK</span>
      : wsStatus === "DENIED"
        ? <span className="nb-tag nb-tag-red ml-2">WS 4401 DENIED</span>
        : wsStatus === "CONNECTING"
          ? <span className="nb-tag nb-tag-white ml-2">WS CONNECTING…</span>
          : null;

  return (
    <div className="space-y-4">
      <div className={`flex flex-wrap items-center justify-between gap-2 border-2 border-black p-3 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] ${telemetry.active_session?.id ? "bg-neon" : "bg-white"}`}>
        <p className="nb-title text-sm">
          {telemetry.active_session?.id
            ? `SESSION #${telemetry.active_session.id} ACTIVE — STARTED ${startedAt || "…"} — PRESENT ${present} / ABSENT ${absent}`
            : "NO ACTIVE SESSION — PRESS START CAMERA, THEN END SESSION"}
        </p>
        <div className="flex flex-wrap gap-2">
          {!cameraOn
            ? <button onClick={startCamera} className="nb-btn nb-btn-black text-xs">START CAMERA</button>
            : <button onClick={stopCamera} className="nb-btn nb-btn-white text-xs">STOP CAMERA</button>}
          <button onClick={async () => {
            try {
              const r = await startSession("Morning Session");
              setStartedAt(new Date().toLocaleTimeString());
              refreshLogs && refreshLogs();
              notify && notify(`Session #${r.session_id} started`, "ok");
            } catch (e) { notify && notify(e.message, "err"); }
          }} className="nb-btn nb-btn-black text-xs">START SESSION</button>
          <button onClick={async () => {
            try {
              const r = await stopSession();
              setSummary(r.summary);
              refreshLogs && refreshLogs();
            } catch (e) { notify && notify(e.message, "err"); }
          }} className="nb-btn nb-btn-red text-xs">END SESSION</button>
          <button onClick={() => setDrawBoxes((v) => !v)} className="nb-tag nb-tag-white cursor-pointer self-center">
            {drawBoxes ? "■ BOXES ON" : "□ DRAW BOXES"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="nb-card p-4">
            <h2 className="nb-title mb-3 text-sm">LIVE CAMERA VIEW {ready === false && <span className="nb-tag nb-tag-red ml-2">MARP 503</span>}{wsBadge}</h2>
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
            <p className="mt-2 font-mono text-[11px] uppercase">WS {wsStatus} • backpressure: ack-or-1s • {detections.length} box(es)</p>
          </div>

          {/* Live roll-call — Neo-brutalist highlight for newly recognized faces */}
          <div className="brutal-card p-4">
            <h2 className="nb-title mb-2 text-sm">LIVE ROLL CALL — RECOGNIZED THIS STREAM ({liveList.length})</h2>
            {liveList.length === 0
              ? <p className="font-mono text-xs">NO FACES RECOGNIZED YET — FACE THE CAMERA.</p>
              : <ul className="grid gap-2 sm:grid-cols-2">
                {liveList.map((r) => (
                  <li key={r.student_id}
                    className={`rounded-none border-4 border-black p-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] ${r.isNew ? "bg-[#E2FF00]" : "bg-white"}`}>
                    <p className="font-extrabold text-sm">{r.isNew ? "● " : ""}{r.name}</p>
                    <p className="font-mono text-[11px]">{r.student_id} • {deptOf(r.student_id)}</p>
                    <p className="font-mono text-[11px] font-bold">MATCH {r.matchPct}%{r.distance != null ? ` • d=${Number(r.distance).toFixed(3)}` : ""}</p>
                  </li>
                ))}
              </ul>}
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
