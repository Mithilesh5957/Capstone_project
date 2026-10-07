import { useEffect, useMemo, useState } from "react";
import { listSessions } from "../api/attendance";

const HARD = "shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]";
const LOG_FILTERS = ["Logs (All)", "Logs (Present ≥ 50%)", "Logs (Absent-heavy)"];

function toCSV(rows) {
  const head = "session_id,session_name,date,total,present,absent";
  const lines = rows.map((s) =>
    [s.session_id, `"${(s.session_name || "").replace(/"/g, '""')}"`, s.date || "", s.total, s.present, s.absent].join(","));
  return [head, ...lines].join("\n");
}

export default function Dashboard({ students, setTab }) {
  const [sessions, setSessions] = useState([]);
  const [logFilter, setLogFilter] = useState(LOG_FILTERS[0]);

  useEffect(() => {
    listSessions(20).then(setSessions).catch(() => setSessions([]));
    const id = setInterval(() => listSessions(20).then(setSessions).catch(() => {}), 8000);
    return () => clearInterval(id);
  }, []);

  const totalStudents = students.length;
  const sessionsHeld = sessions.length;
  const avg = useMemo(() => {
    const withTotal = sessions.filter((s) => s.total > 0);
    if (!withTotal.length) return 0;
    const pct = withTotal.reduce((a, s) => a + (s.present / s.total) * 100, 0) / withTotal.length;
    return Math.round(pct);
  }, [sessions]);

  const last = sessions[0];
  const present = last ? last.present : 0;
  const absent = last ? last.absent : 0;
  const denom = Math.max(1, present + absent);

  const visibleSessions = sessions.filter((s) => {
    if (logFilter === LOG_FILTERS[1]) return s.total > 0 && s.present / s.total >= 0.5;
    if (logFilter === LOG_FILTERS[2]) return s.total > 0 && s.absent > s.present;
    return true;
  });

  const exportSessions = () => {
    const blob = new Blob([toCSV(visibleSessions)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "faceattend_sessions.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const cards = [
    { icon: "◉", value: String(totalStudents), label: "TOTAL STUDENTS" },
    { icon: "▦", value: String(sessionsHeld), label: "SESSIONS HELD" },
    { icon: "✔", value: `${avg}%`, label: "AVG ATTENDANCE" },
  ];

  return (
    <div className="space-y-4 bg-paper font-sans text-black">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-none border-4 border-black bg-white p-4 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div>
          <h1 className="font-extrabold uppercase tracking-wider text-2xl">DASHBOARD</h1>
          <p className="font-mono text-xs font-bold uppercase tracking-wider">FaceAttend Management System</p>
        </div>
        <button onClick={exportSessions}
          className="rounded-none border-4 border-black bg-black px-5 py-2.5 font-extrabold uppercase tracking-wider text-sm text-neon transition-all hover:translate-x-1 hover:translate-y-1 hover:bg-neon hover:text-black hover:shadow-none">
          ⤓ EXPORT SESSIONS
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {cards.map((m) => (
          <div key={m.label} className={`flex items-center gap-4 rounded-none border-4 border-black bg-white p-5 ${HARD}`}>
            <span className="flex h-12 w-12 items-center justify-center rounded-none border-2 border-black bg-neon text-xl font-extrabold">{m.icon}</span>
            <div>
              <p className="font-extrabold uppercase tracking-wider text-3xl">{m.value}</p>
              <p className="font-mono text-xs font-bold uppercase tracking-wider">{m.label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-none border-4 border-black bg-white p-5 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] lg:col-span-3">
          <h2 className="font-extrabold uppercase tracking-wider text-sm">ATTENDANCE DISTRIBUTION</h2>
          <p className="mt-1 font-mono text-xs font-bold uppercase">
            {last ? `LATEST — SESSION #${last.session_id} ${last.session_name}` : "NO SESSIONS YET"}
          </p>
          <div className="mt-4 flex h-40 items-end gap-3 border-4 border-black bg-paper p-3">
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{present}</p>
              <div className="w-full border-2 border-black bg-neon" style={{ height: `${Math.round((present / denom) * 100)}%`, minHeight: present ? 8 : 0 }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Present</p>
            </div>
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{absent}</p>
              <div className="w-full border-2 border-black bg-[#DC2626]" style={{ height: `${Math.round((absent / denom) * 100)}%`, minHeight: absent ? 8 : 0 }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Absent</p>
            </div>
            <div className="flex h-full flex-1 flex-col justify-end">
              <p className="mb-1 text-center font-extrabold text-lg">{totalStudents}</p>
              <div className="w-full border-2 border-black bg-black" style={{ height: "100%" }} />
              <p className="mt-1 text-center font-mono text-[11px] font-bold uppercase">Enrolled</p>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <button onClick={() => setTab && setTab("attendance")}
            className="flex flex-1 items-center justify-between rounded-none border-4 border-black bg-neon p-5 text-left shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-1 hover:translate-y-1 hover:shadow-none">
            <span>
              <span className="block font-extrabold uppercase tracking-wider text-lg">▶ LIVE SESSION</span>
              <span className="block font-mono text-xs font-bold uppercase">Start new face recognition</span>
            </span>
            <span className="rounded-none border-2 border-black bg-black px-2 py-1 font-mono text-[11px] font-bold text-neon">GO</span>
          </button>
          <button onClick={() => setTab && setTab("students")}
            className="flex flex-1 items-center justify-between rounded-none border-4 border-black bg-white p-5 text-left shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-1 hover:translate-y-1 hover:shadow-none">
            <span>
              <span className="block font-extrabold uppercase tracking-wider text-lg">◉ STUDENTS</span>
              <span className="block font-mono text-xs font-bold uppercase">Register new face records</span>
            </span>
            <span className="rounded-none border-2 border-black bg-neon px-2 py-1 font-mono text-[11px] font-bold text-black">GO</span>
          </button>
        </div>
      </div>

      <div className="rounded-none border-4 border-black bg-white p-4 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-extrabold uppercase tracking-wider text-sm">SESSION LOG</h2>
          <select value={logFilter} onChange={(e) => setLogFilter(e.target.value)}
            className="rounded-none border-4 border-black bg-paper px-3 py-1.5 font-mono text-xs font-bold uppercase focus:outline-none">
            {LOG_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto border-4 border-black">
          <table className="w-full bg-white text-sm">
            <thead><tr className="bg-black font-extrabold uppercase tracking-wider text-xs text-neon">
              <th className="p-3 text-left">Session</th><th className="p-3 text-left">Date</th><th className="p-3 text-left">Present</th><th className="p-3 text-left">Absent</th><th className="p-3 text-left">Status</th>
            </tr></thead>
            <tbody>
              {visibleSessions.map((s) => (
                <tr key={s.session_id} className="border-t-4 border-black bg-white">
                  <td className="p-3 font-mono text-xs font-bold">#{s.session_id} {s.session_name}</td>
                  <td className="p-3 font-mono text-xs">{s.date || "—"}</td>
                  <td className="p-3"><span className="rounded-none border-2 border-black bg-neon px-2 py-0.5 font-mono text-[11px] font-bold text-black">{s.present}/{s.total}</span></td>
                  <td className="p-3"><span className={`rounded-none border-2 border-black px-2 py-0.5 font-mono text-[11px] font-bold ${s.absent ? "bg-[#DC2626] text-white" : "bg-white text-black"}`}>{s.absent}</span></td>
                  <td className="p-3"><span className="rounded-none border-2 border-black bg-white px-2 py-0.5 font-mono text-[11px] font-bold">CLOSED</span></td>
                </tr>
              ))}
              {visibleSessions.length === 0 && <tr><td colSpan={5} className="bg-white p-4 text-center font-mono text-xs font-bold">NO SESSIONS MATCH THIS FILTER</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
