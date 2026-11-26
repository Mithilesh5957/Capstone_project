import { useCallback, useEffect, useState } from "react";
import { FaAvatar, FaButton, FaCard, FaSectionHeader, FaStatusIndicator } from "../fa/primitives";
import { SESSION_KEY, api } from "../fa/request";

export default function StudentPortal({ lockedId }) {
  const [sid, setSid] = useState(lockedId || "");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // No state reads inside: safe for exhaustive-deps without a disable comment.
  const lookup = useCallback(async (id) => {
    const target = (id || "").trim();
    if (!target) {
      setErr("ENTER YOUR STUDENT ID / ROLL NO.");
      return;
    }
    setBusy(true);
    try {
      setData(await api(`/api/students/${encodeURIComponent(target)}/attendance`));
      setErr("");
    } catch (e) {
      if (e && (e.status === 401 || e.status === 403)) {
        // Session expired or revoked — drop it and return to the login gate.
        localStorage.removeItem(SESSION_KEY);
        window.location.reload();
        return;
      }
      setErr("NO RECORD FOUND.");
      setData(null);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    if (lockedId) {
      setSid(lockedId);
      lookup(lockedId);
    }
  }, [lockedId, lookup]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <FaCard glass>
        <div style={{ padding: 20, display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <FaAvatar id={lockedId} name={lockedId} size={44} />
            <FaSectionHeader title="Student portal" sub={`Roll no. ${lockedId || "—"}`} />
          </div>
          <FaButton variant="secondary" onClick={() => lookup(sid)} loading={busy} disabled={busy}>
            ↻ Refresh
          </FaButton>
        </div>
        {err && <p className="fa-error" role="alert" style={{ margin: "0 20px 16px", fontSize: "var(--fa-t-sm)" }}>{err}</p>}
      </FaCard>
      {data && (
        <FaCard>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: 16, borderBottom: "1px solid var(--fa-border)" }}>
            <FaAvatar id={data.student_id} name={data.name} size={48} />
            <div style={{ minWidth: 0 }}>
              <p className="fa-brand-gradient" style={{ fontWeight: 800, fontSize: "var(--fa-t-lg)", margin: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{data.name}</p>
              <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", margin: "4px 0 0" }}>{data.student_id} • {data.branch}</p>
            </div>
            <div style={{ marginLeft: "auto" }}>
              <FaStatusIndicator tone={data.percentage >= 50 ? "ok" : "warn"}>{data.percentage}%</FaStatusIndicator>
            </div>
          </div>
          <div className="fa-table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="fa-table">
              <thead><tr><th>Session</th><th>Date</th><th>Status</th></tr></thead>
              <tbody>
                {(data.history || []).map((h) => (
                  <tr key={h.session_id}>
                    <td>{h.session_name}</td>
                    <td className="fa-mono">{h.date}</td>
                    <td>
                      <FaStatusIndicator tone={h.status === "Present" ? "ok" : "err"}>
                        {h.status}
                      </FaStatusIndicator>
                    </td>
                  </tr>
                ))}
                {(data.history || []).length === 0 && <tr><td colSpan={3}><p className="fa-empty">No attendance records yet.</p></td></tr>}
              </tbody>
            </table>
          </div>
        </FaCard>
      )}
    </div>
  );
}
