import { useEffect, useRef, useState } from "react";
import { FaButton, FaCard, FaFormField, FaSectionHeader, FaStatusIndicator } from "../fa/primitives";
import { SESSION_KEY, api, snapshot } from "../fa/request";

export default function EnrollTab({ branches, angles, onDone }) {
  const enrollVideoRef = useRef(null);
  const [form, setForm] = useState({ student_id: "", name: "", branch: branches[0] || "CSE" });
  const [shots, setShots] = useState([null, null, null, null]);
  const [msg, setMsg] = useState("");
  const [msgTone, setMsgTone] = useState("neutral");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const hasDetails = form.student_id.trim() !== "" && form.name.trim() !== "";
  const doneCount = shots.filter(Boolean).length;
  const step = !hasDetails ? 1 : doneCount < angles.length ? 2 : 3;

  useEffect(() => {
    let stream;
    // mediaDevices is absent in some browsers and insecure contexts: guard
    // it so a missing camera can never crash the form (same rule as scanner).
    const md = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
    if (!md || typeof md.getUserMedia !== "function") {
      setMsg("CAMERA UNAVAILABLE IN THIS BROWSER.");
      setMsgTone("warn");
      return undefined;
    }
    md
      .getUserMedia({ video: true })
      .then((s) => {
        stream = s;
        if (enrollVideoRef.current) enrollVideoRef.current.srcObject = s;
      })
      .catch(() => {
        setMsg("CAMERA BLOCKED — ALLOW WEBCAM ACCESS.");
        setMsgTone("err");
      });
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  const capture = (i) => {
    if (!enrollVideoRef.current?.videoWidth) {
      setMsg("CAMERA NOT READY — WAIT FOR THE VIDEO FEED.");
      setMsgTone("warn");
      return;
    }
    const next = [...shots];
    next[i] = snapshot(enrollVideoRef.current);
    setShots(next);
    setMsg("");
  };

  const submit = async () => {
    if (!form.student_id.trim() || !form.name.trim()) {
      setMsg("STUDENT ID AND FULL NAME ARE REQUIRED.");
      setMsgTone("err");
      return;
    }
    if (doneCount < angles.length) {
      setMsg(`CAPTURE ALL ${angles.length} ANGLES FIRST (${doneCount}/${angles.length} DONE).`);
      setMsgTone("warn");
      return;
    }
    setBusy(true);
    setMsg("UPLOADING STUDENT + EMBEDDINGS…");
    setMsgTone("neutral");
    try {
      const r = await api("/api/students/enroll", {
        method: "POST",
        body: JSON.stringify({ ...form, images: shots }),
      });
      setMsg(`ENROLLED ${r.name} (${r.student_id}) — ${r.angles_used} ANGLES.`);
      setMsgTone("ok");
      setShots([null, null, null, null]);
      onDone();
    } catch (e) {
      if (e && (e.status === 401 || e.status === 403)) {
        localStorage.removeItem(SESSION_KEY);
        window.location.reload();
        return;
      }
      setMsg((e.message || "ENROLL FAILED").toUpperCase());
      setMsgTone("err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <FaCard>
        <div style={{ padding: 16 }}>
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", gap: 8, flexWrap: "wrap" }} aria-label="Enrollment progress">
            {[["1", "Details"], ["2", "Capture"], ["3", "Save"]].map(([n, label]) => {
              const active = Number(n) === step;
              const done = Number(n) < step;
              return (
                <li key={n} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span aria-hidden="true" style={{ width: 26, height: 26, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: "var(--fa-t-xs)", fontWeight: 800, background: done ? "var(--fa-ok)" : active ? "var(--fa-accent)" : "transparent", color: done || active ? "var(--fa-ink)" : "var(--fa-text-muted)", border: done || active ? "none" : "1px solid var(--fa-border)" }}>{done ? "✓" : n}</span>
                  <span style={{ fontSize: "var(--fa-t-sm)", fontWeight: active ? 800 : 400, color: active ? "var(--fa-text)" : "var(--fa-text-muted)" }}>{label}</span>
                </li>
              );
            })}
          </ol>
        </div>
      </FaCard>
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))" }}>
      <FaCard>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <FaSectionHeader title="Student profile" sub="Identity for the new face record" />
          <FaFormField label="Student ID / roll no." errorId="enroll-id">
            {(describedBy) => (
              <input value={form.student_id} onChange={set("student_id")} placeholder="2100030001" className="fa-input" aria-describedby={describedBy} aria-invalid={msgTone === "err" ? true : undefined} />
            )}
          </FaFormField>
          <FaFormField label="Full name" errorId="enroll-name">
            {(describedBy) => (
              <input value={form.name} onChange={set("name")} placeholder="Enter full name" className="fa-input" aria-describedby={describedBy} aria-invalid={msgTone === "err" ? true : undefined} />
            )}
          </FaFormField>
          <FaFormField label="Branch" errorId="enroll-branch">
            {(describedBy) => (
              <select value={form.branch} onChange={set("branch")} className="fa-input" aria-describedby={describedBy}>
                {branches.map((d) => (<option key={d} value={d}>{d}</option>))}
              </select>
            )}
          </FaFormField>
        </div>
      </FaCard>
      <FaCard>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <FaSectionHeader title="4-angle face scan" sub="Capture each angle from the live feed" />
            <FaStatusIndicator tone={doneCount === angles.length ? "ok" : "neutral"}>{doneCount}/{angles.length}</FaStatusIndicator>
          </div>
          <div className="fa-video-frame">
            <video ref={enrollVideoRef} autoPlay muted playsInline aria-label="Enrollment camera feed" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }} role="group" aria-label="Capture angles">
            {angles.map((a, i) => (
              <FaButton key={a} variant="secondary" onClick={() => capture(i)} aria-pressed={!!shots[i]} aria-label={shots[i] ? `Retake ${a} (captured)` : `Capture ${a}`}>
                {shots[i] ? (
                  <img src={shots[i]} alt={`${a} preview`} style={{ width: "100%", aspectRatio: "1", objectFit: "cover", borderRadius: 4 }} />
                ) : (
                  <span aria-hidden="true">◌<br />{a}</span>
                )}
                <span style={{ display: "block", fontSize: "var(--fa-t-xs)" }}>{shots[i] ? `✓ ${a}` : a}</span>
              </FaButton>
            ))}
          </div>
          <FaButton onClick={submit} loading={busy} disabled={busy} style={{ width: "100%" }}>
            {busy ? "Saving…" : "Save student & embeddings"}
          </FaButton>
          {msg && (
            <p className={msgTone === "ok" ? "" : "fa-error"} role={msgTone === "err" ? "alert" : "status"}
               style={msgTone === "ok" ? { color: "var(--fa-ok)", fontSize: "var(--fa-t-xs)", margin: 0 } : { fontSize: "var(--fa-t-sm)", margin: 0 }}>
              {msg}
            </p>
          )}
        </div>
      </FaCard>
    </div>
    </div>
  );
}
