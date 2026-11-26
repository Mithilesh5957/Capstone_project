import { FaAvatar, FaButton, FaCard, FaFormField, FaSectionHeader, FaStatusIndicator } from "../fa/primitives";

export default function ScannerView({
  videoRef, canvasRef, logs, attendanceLogs, present,
  telemetry, marpOnline, cameraError,
  sessionName, onSessionName, onStartSession, onStopSession,
}) {
  // Note: bounding boxes are painted imperatively onto the canvas by the
  // App-level overlay effect (same as before extraction); this view owns layout only.
  const activeId = telemetry.active_session?.id;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <FaCard>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "center", padding: 16 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            {activeId && <span className="fa-pulse-dot ok" aria-hidden="true" />}
            <FaStatusIndicator tone={activeId ? "ok" : "neutral"}>
              {activeId ? `Session #${activeId} active` : "No active session"}
            </FaStatusIndicator>
            {activeId && (
              <span style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)" }}>
                Present {present}/{attendanceLogs.length}
              </span>
            )}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
            <div style={{ minWidth: 180 }}>
              <FaFormField label="Session name" errorId="scanner-session-name">
                {(describedBy) => (
                  <input
                    value={sessionName || ""}
                    onChange={(e) => onSessionName(e.target.value)}
                    placeholder="Morning Session"
                    className="fa-input"
                    aria-describedby={describedBy}
                  />
                )}
              </FaFormField>
            </div>
            <FaButton variant="primary" onClick={onStartSession}>Start session</FaButton>
            <FaButton variant="secondary" onClick={onStopSession}>End session</FaButton>
          </div>
        </div>
      </FaCard>
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          <FaCard>
            <div style={{ padding: 16 }}>
              <FaSectionHeader title="Live camera view" sub={marpOnline ? "Model ready — streaming detections" : "Waiting for model readiness"} />
          {cameraError && (
            <p role="alert" style={{ fontSize: "var(--fa-t-sm)", color: "var(--fa-warn)", margin: "8px 0 0" }}>
              {cameraError}
            </p>
          )}
              <div className="fa-video-frame" style={{ marginTop: 12 }}>
                <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera feed" />
                <canvas ref={canvasRef} width={640} height={480} aria-hidden="true" />
              </div>
            </div>
          </FaCard>
          <FaCard>
            <div style={{ padding: 16 }}>
              <FaSectionHeader title="Detection log" sub="Live · newest first" />
              <ul className="fa-log" style={{ marginTop: 12 }} aria-live="off">
                {logs.length === 0 && <li>No detections yet…</li>}
                {logs.map((l) => (
                  <li key={l.id}>
                    [{l.time}] <b>{l.label || l.name || l.type}</b> CONF={l.confidence} BBOX=[{(l.bbox || []).join(",")}]
                  </li>
                ))}
              </ul>
            </div>
          </FaCard>
        </div>
        <FaCard>
          <div style={{ padding: 16 }}>
            <FaSectionHeader title="Roll call" sub={`${attendanceLogs.length} on roster`} />
            <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, maxHeight: 288, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
              {attendanceLogs.map((r, i) => (
                <li key={`side-${r.student_id}-${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <div style={{ minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}>
                    <FaAvatar id={r.student_id} name={r.name} size={32} />
                    <div style={{ minWidth: 0 }}>
                      <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--fa-t-sm)", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name || "—"}</p>
                      <p style={{ margin: 0, fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)" }}>{r.student_id || "—"}</p>
                    </div>
                  </div>
                  <FaStatusIndicator tone={r.status === "Present" ? "ok" : "neutral"}>
                    {r.status || "Detected"}
                  </FaStatusIndicator>
                </li>
              ))}
              {attendanceLogs.length === 0 && <li><p className="fa-empty">Empty — face the camera.</p></li>}
            </ul>
          </div>
        </FaCard>
      </div>
      <FaCard>
        <div style={{ padding: 16 }}>
          <FaSectionHeader title={`Live attendance roster (${attendanceLogs.length})`} sub="Authoritative session data" />
          <div className="fa-table-wrap" style={{ marginTop: 12 }}>
            <table className="fa-table">
              <thead><tr><th>ID</th><th>Name</th><th>Status</th></tr></thead>
              <tbody>
                {attendanceLogs.map((r, i) => (
                  <tr key={`${r.student_id}-${i}`}>
                    <td className="fa-mono">{r.student_id || "—"}</td>
                    <td style={{ fontWeight: 700 }}>{r.name || "—"}</td>
                    <td>
                      <FaStatusIndicator tone={r.status === "Present" ? "ok" : r.status === "Absent" ? "err" : "neutral"}>
                        {r.status || "Detected"}
                      </FaStatusIndicator>
                    </td>
                  </tr>
                ))}
                {attendanceLogs.length === 0 && <tr><td colSpan={3}><p className="fa-empty">No records in this session yet.</p></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </FaCard>
    </div>
  );
}
