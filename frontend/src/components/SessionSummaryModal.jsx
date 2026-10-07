import { exportCsvUrl } from "../api/attendance";

export default function SessionSummaryModal({ summary, onClose }) {
  if (!summary) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="nb-card w-full max-w-2xl bg-paper p-0" onClick={(e) => e.stopPropagation()}>
        <div className="border-b-2 border-black bg-neon px-5 py-3">
          <h2 className="nb-title text-sm">SESSION #{summary.session_id} — {summary.session_name}</h2>
          <p className="font-mono text-xs">TOTAL {summary.total} • PRESENT {summary.present} • ABSENT {summary.absent}</p>
        </div>
        <div className="max-h-64 overflow-y-auto p-4">
          <table className="nb-table w-full bg-white text-sm">
            <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Marked</th></tr></thead>
            <tbody>
              {(summary.records || []).map((r) => (
                <tr key={r.student_id} className="bg-white">
                  <td className="font-mono text-xs">{r.student_id}</td>
                  <td className="font-bold">{r.name}</td>
                  <td><span className={`nb-tag ${r.status === "Present" ? "nb-tag-yellow" : "nb-tag-red"}`}>{r.status}</span></td>
                  <td className="font-mono text-xs">{r.marked_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex gap-2 border-t-2 border-black p-4">
          <a href={exportCsvUrl(summary.session_id)} className="nb-btn nb-btn-lime">EXPORT CSV</a>
          <button onClick={onClose} className="nb-btn nb-btn-white">CLOSE</button>
        </div>
      </div>
    </div>
  );
}
