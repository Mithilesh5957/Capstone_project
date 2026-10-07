import { useState } from "react";
import BiometricModal from "../components/BiometricModal";

const BRANCHES = ["ALL BRANCHES", "CSE", "ECE", "ME", "AI&DS", "EEE", "BT"];

export default function Students({ students, onRefresh }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [branch, setBranch] = useState("ALL BRANCHES");
  const rows = students.filter((s) =>
    (branch === "ALL BRANCHES" || s.branch === branch) &&
    (s.name.toLowerCase().includes(q.toLowerCase()) || s.student_id.includes(q)));

  return (
    <div className="space-y-4">
      <div className="nb-card-black flex flex-wrap items-center justify-between gap-2 p-4">
        <h2 className="nb-title text-lg">BIOMETRIC INTAKE PIPELINE ({students.length})</h2>
        <button onClick={() => setOpen(true)} className="nb-btn nb-btn-lime">+ BIOMETRIC INTAKE (ADD STUDENT)</button>
      </div>
      <div className="nb-card flex flex-wrap gap-2 p-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search roll / name…" className="nb-input max-w-xs" />
        <select value={branch} onChange={(e) => setBranch(e.target.value)} className="nb-input max-w-xs">
          {BRANCHES.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <span className="nb-tag nb-tag-white self-center">{rows.length} SHOWN</span>
      </div>
      <div className="nb-card overflow-hidden">
        <table className="nb-table w-full bg-white text-sm">
          <thead><tr><th>Roll No</th><th>Branch</th><th>Sem</th><th>Snapshot</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.student_id} className="bg-white">
                <td className="font-mono text-xs font-bold">{s.student_id}<br /><span className="font-sans">{s.name}</span></td>
                <td><span className="nb-tag nb-tag-white">{s.branch}</span></td>
                <td className="font-mono">—</td>
                <td><span className="nb-tag nb-tag-yellow">● ENROLLED</span></td>
                <td><span className="font-mono text-xs">VIEW</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="bg-white p-8 text-center font-mono text-xs">NO STUDENTS — HIT BIOMETRIC INTAKE.</p>}
      </div>
      <BiometricModal open={open} onClose={() => setOpen(false)} onDone={() => { setOpen(false); onRefresh && onRefresh(); }} />
    </div>
  );
}
