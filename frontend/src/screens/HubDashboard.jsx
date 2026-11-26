import { FaButton, FaCard, FaSectionHeader, FaStatusIndicator } from "../fa/primitives";

export default function HubDashboard({ students, sessions, telemetry, setTab, logFilter, setLogFilter }) {
  const liveId = telemetry && telemetry.active_session ? telemetry.active_session.id : null;
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
  const stats = [
    { value: String(students.length), label: "Total students", sub: "Live · /api/students" },
    { value: String(sessions.length), label: "Sessions held", sub: "Live · /api/attendance/sessions" },
    { value: `${avg}%`, label: "Avg attendance", sub: last ? `Latest session #${last.session_id}` : "No sessions yet" },
  ];
  const statTones = ["var(--fa-accent)", "var(--fa-accent-2)", "var(--fa-ok)"];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <FaCard glass>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "center", padding: 16 }}>
          <FaSectionHeader title="Dashboard" sub="FaceAttend management system" />
          <FaButton variant="secondary" onClick={exportSessions}>
            ⤓ Export sessions
          </FaButton>
        </div>
      </FaCard>
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))" }}>
        {stats.map((m, i) => (
          <FaCard key={m.label} className="fa-lift">
            <div style={{ padding: 16, borderTop: `3px solid ${statTones[i % statTones.length]}`, borderRadius: "var(--fa-r-md) var(--fa-r-md) 0 0" }}>
              <p style={{ fontWeight: 800, fontSize: "var(--fa-t-xl)", margin: 0 }}>{m.value}</p>
              <p style={{ fontSize: "var(--fa-t-xs)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--fa-text-muted)", margin: "4px 0 0" }}>{m.label}</p>
              <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", margin: "4px 0 0" }}>{m.sub}</p>
            </div>
          </FaCard>
        ))}
      </div>
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))" }}>
        <FaCard>
          <div style={{ padding: 16 }}>
            <FaSectionHeader title="Attendance distribution" sub={last ? `Latest — session #${last.session_id}` : "No sessions yet"} />
            <div style={{ display: "flex", height: 160, alignItems: "flex-end", gap: 12, marginTop: 12, padding: 12, background: "var(--fa-bg)", border: "1px solid var(--fa-border)", borderRadius: "var(--fa-r-sm)" }} role="img" aria-label={`Present ${present}, absent ${absent}, enrolled ${students.length}`}>
              {[
                { n: present, label: "Present", color: "var(--fa-ok)" },
                { n: absent, label: "Absent", color: "var(--fa-err)" },
                { n: students.length, label: "Enrolled", color: "var(--fa-accent)" },
              ].map((b) => (
                  <div key={b.label} style={{ flex: 1, height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center" }}>
                    <p style={{ fontWeight: 800, fontSize: "var(--fa-t-lg)", margin: "0 0 4px" }}>{b.n}</p>
                    <div className="fa-stat-bar" style={{ width: "100%", height: `${b.label === "Enrolled" ? 100 : Math.round((b.n / denom) * 100)}%`, minHeight: b.n ? 8 : 0, background: b.color, borderRadius: "var(--fa-r-sm)" }} />
                  <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", textTransform: "uppercase", margin: "4px 0 0" }}>{b.label}</p>
                </div>
              ))}
            </div>
          </div>
        </FaCard>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <FaButton variant="primary" onClick={() => setTab("scanner")} style={{ flex: 1, padding: 20, fontSize: "var(--fa-t-md)" }}>
            ▶ Live session{telemetry.active_session?.id ? ` — #${telemetry.active_session.id} active` : ""}
          </FaButton>
          <FaButton variant="secondary" onClick={() => setTab("enroll")} style={{ flex: 1, padding: 20, fontSize: "var(--fa-t-md)" }}>
            ◉ Students — register new face records
          </FaButton>
        </div>
      </div>
      <FaCard>
        <div style={{ padding: 16 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <FaSectionHeader title="Session log" />
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)" }}>
              Filter
              <select value={logFilter} onChange={(e) => setLogFilter(e.target.value)} className="fa-select" aria-label="Filter sessions">
                {["Logs (All)", "Logs (Present ≥ 50%)", "Logs (Absent-heavy)"].map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>
          </div>
          <div className="fa-table-wrap">
            <table className="fa-table">
              <thead><tr>
                <th>Session</th><th>Date</th><th>Present</th><th>Absent</th><th>Status</th>
              </tr></thead>
              <tbody>
                {visible.map((s) => (
                  <tr key={s.session_id}>
                    <td className="fa-mono">#{s.session_id} {s.session_name}</td>
                    <td className="fa-mono">{s.date || "—"}</td>
                    <td><FaStatusIndicator tone="info">{s.present}/{s.total}</FaStatusIndicator></td>
                    <td><FaStatusIndicator tone={s.absent ? "warn" : "neutral"}>{s.absent}</FaStatusIndicator></td>
                    <td><FaStatusIndicator tone={s.session_id === liveId ? "ok" : "neutral"}>{s.session_id === liveId ? "Live" : "Closed"}</FaStatusIndicator></td>
                  </tr>
                ))}
                {visible.length === 0 && <tr><td colSpan={5}><p className="fa-empty">No sessions match this filter.</p></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </FaCard>
    </div>
  );
}
