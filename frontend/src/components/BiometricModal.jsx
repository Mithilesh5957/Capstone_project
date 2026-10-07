import { useEffect, useRef, useState } from "react";
import { snapshot } from "../api/client";
import { enrollStudent } from "../api/students";
import { useMARP } from "../context/MARPContext";

const ANGLES = ["Front", "Left Profile", "Right Profile", "Upper Angle"];
const BRANCHES = ["CSE", "ECE", "ME", "AI&DS", "EEE", "BT"];

export default function BiometricModal({ open, onClose, onDone, initial = {} }) {
  const videoRef = useRef(null);
  const { notify } = (() => { try { return useMARP(); } catch { return { notify: () => {} }; } })();
  const [step, setStep] = useState(1);
  const [shots, setShots] = useState([null, null, null, null]);
  const [form, setForm] = useState({
    username: initial.username || "",
    name: initial.name || "",
    email: initial.email || "",
    student_id: initial.student_id || "",
    branch: initial.branch || "CSE",
    semester: initial.semester || "1",
  });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    if (!open) return;
    setStep(1);
    let stream;
    navigator.mediaDevices.getUserMedia({ video: true })
      .then((s) => { stream = s; if (videoRef.current) videoRef.current.srcObject = s; })
      .catch(() => setMsg("Camera blocked — allow webcam access."));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, [open ]);

  if (!open) return null;
  const doneCount = shots.filter(Boolean).length;

  const bioScan = () => {
    // Burst-capture 4 facial snapshots into the memory buffer.
    if (!videoRef.current?.videoWidth) { setMsg("Camera not ready yet."); return; }
    const next = [0, 1, 2, 3].map(() => snapshot(videoRef.current));
    setShots(next);
    setMsg("BIO-SCAN complete — 4 snapshots buffered.");
  };

  const submit = async () => {
    if (!form.student_id.trim() || !form.name.trim()) { setMsg("Roll Number and Full Name are required."); return; }
    if (doneCount < 4) { setMsg(`Back to Step 1: capture 4 angles first (${doneCount}/4).`); setStep(1); return; }
    setBusy(true);
    setMsg("Registering biometrics + profile…");
    try {
      const r = await enrollStudent({ student_id: form.student_id, name: form.name, branch: form.branch, images: shots, ...form });
      setMsg(`Enrolled ${r.name} (${r.student_id}) — ${r.angles_used} angles embedded.`);
      try { notify(`Enrolled ${r.name}`, "ok"); } catch { /* no provider */ }
      setShots([null, null, null, null]);
      setStep(1);
      onDone && onDone(r);
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="nb-card w-full max-w-3xl bg-paper p-0" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b-2 border-black bg-neon px-5 py-3">
          <h2 className="nb-title text-sm">BIOMETRIC INTAKE — STEP {step}/2</h2>
          <button onClick={onClose} className="nb-tag nb-tag-yellow cursor-pointer">CLOSE ✕</button>
        </div>

        {step === 1 ? (
          <div className="space-y-3 p-5">
            <p className="nb-tag nb-tag-lime">ALIGN FACE IN THE CENTER OF THE FRAME</p>
            <div className="border-2 border-black bg-black">
              <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full object-cover" />
            </div>
            <div className="grid grid-cols-4 gap-2">
              {ANGLES.map((a, i) => (
                <div key={a} className="border-2 border-black bg-white text-center text-[11px] font-bold">
                  {shots[i] ? <img src={shots[i]} alt={a} className="aspect-square w-full object-cover" /> : <span className="block py-5">◌<br />{a}</span>}
                  <span className={`block border-t-2 border-black py-1 ${shots[i] ? "bg-neon" : "bg-white"}`}>{shots[i] ? `✓ ${a}` : a}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={bioScan} className="nb-btn nb-btn-black">INITIATE BIO-SCAN ({doneCount}/4)</button>
              <button onClick={() => (doneCount >= 4 ? setStep(2) : setMsg(`Need 4 snapshots (${doneCount}/4).`))} className="nb-btn nb-btn-lime">NEXT: DETAILS →</button>
            </div>
            {msg && <p className="border-2 border-black bg-white p-2 font-mono text-xs">{msg}</p>}
          </div>
        ) : (
          <div className="grid gap-4 p-5 md:grid-cols-2">
            <div className="space-y-3">
              <label className="nb-title block text-xs">USERNAME<input value={form.username} onChange={set("username")} placeholder="jdoe21" className="nb-input mt-1" /></label>
              <label className="nb-title block text-xs">FULL NAME<input value={form.name} onChange={set("name")} placeholder="Jane Doe" className="nb-input mt-1" /></label>
              <label className="nb-title block text-xs">EMAIL<input value={form.email} onChange={set("email")} placeholder="jane@college.edu" className="nb-input mt-1" /></label>
            </div>
            <div className="space-y-3">
              <label className="nb-title block text-xs">ROLL NUMBER<input value={form.student_id} onChange={set("student_id")} placeholder="2100030001" className="nb-input mt-1" /></label>
              <div className="grid grid-cols-2 gap-3">
                <label className="nb-title block text-xs">BRANCH
                  <select value={form.branch} onChange={set("branch")} className="nb-input mt-1">
                    {BRANCHES.map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </label>
                <label className="nb-title block text-xs">SEMESTER
                  <select value={form.semester} onChange={set("semester")} className="nb-input mt-1">
                    {["1", "2", "3", "4", "5", "6", "7", "8"].map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <button onClick={() => setStep(1)} className="nb-btn nb-btn-white">← RESCAN</button>
                <button onClick={submit} disabled={busy} className="nb-btn nb-btn-lime disabled:opacity-50">
                  {busy ? "SAVING…" : "COMPLETE REGISTRATION"}
                </button>
              </div>
              {msg && <p className="border-2 border-black bg-white p-2 font-mono text-xs">{msg}</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
