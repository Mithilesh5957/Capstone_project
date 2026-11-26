import { useState } from "react";
import { FaAvatar, FaButton, FaCard, FaFormField } from "../fa/primitives";
import { api } from "../fa/request";

const ORG_NAME = process.env.REACT_APP_ORG_NAME || "KL University";

export default function LoginScreen({ onLogin }) {
  const [mode, setMode] = useState("Admin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // R1: credentials are verified server-side. No client-side credential
  // checks, no demo bypass, and no offline session is ever created.
  const doLogin = async (u, pw) => {
    setBusy(true);
    setErr("");
    try {
      const ctx = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: u, password: pw, role: mode.toLowerCase() }),
      });
      if (!ctx.token) {
        setErr("LOGIN FAILED — SERVER RETURNED NO SESSION TOKEN.");
        return;
      }
      // R1: the displayed role comes from the server (ctx.role), never from
      // the client-side mode toggle. A mismatched mode still yields a usable
      // session, but backend 403s would block every admin call.
      const serverRole = (ctx.role || "").toLowerCase() === "student" ? "Student" : "Admin";
      onLogin(
        serverRole === "Admin"
          ? { role: "Admin", username: ctx.username || u, name: ctx.name || "Class Teacher", token: ctx.token }
          : { role: "Student", username: ctx.student_id || u, student_id: ctx.student_id || u, name: ctx.name || u, branch: ctx.branch || "", token: ctx.token }
      );
    } catch (e) {
      if (e?.status === 401) setErr("INVALID CREDENTIALS — CHECK USERNAME AND PASSWORD.");
      else if (e?.status === 503) setErr("ACCOUNT NOT PROVISIONED — CONTACT YOUR ADMINISTRATOR.");
      else if (e?.status === 422) setErr("USERNAME AND PASSWORD ARE REQUIRED.");
      else setErr("LOGIN FAILED — BACKEND UNREACHABLE. TRY AGAIN.");
    } finally {
      setBusy(false);
    }
  };
  const submit = async (e) => {
    e?.preventDefault();
    setErr("");
    const u = username.trim();
    if (!u || !password) {
      setErr("USERNAME AND PASSWORD ARE REQUIRED.");
      return;
    }
    await doLogin(u, password);
  };

  return (
    <div className="fa-page-enter" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 24, alignItems: "stretch", width: "100%", maxWidth: 880 }}>
      <FaCard glass>
        <div style={{ padding: "28px 24px", display: "flex", flexDirection: "column", gap: 16, height: "100%", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <FaAvatar id="faceattend-brand" name="Face Attend" size={48} />
            <p style={{ fontWeight: 800, fontSize: "var(--fa-t-xl)", letterSpacing: "0.04em", margin: 0 }} className="fa-brand-gradient">FACEATTEND</p>
          </div>
          <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", margin: "4px 0 0", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {ORG_NAME} · Classroom attendance
          </p>
          <ul style={{ listStyle: "none", margin: "8px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 10, fontSize: "var(--fa-t-sm)" }}>
            {[
              ["Live roll call", "Camera frames marked present exactly once per session."],
              ["Model-aware health", "Readiness reflects loaded AI weights, not just an open socket."],
              ["Operator controls", "Enroll faces, run sessions, export CSV — audited per role."],
            ].map(([t, d]) => (
              <li key={t} style={{ display: "flex", gap: 10 }}>
                <span aria-hidden="true" style={{ color: "var(--fa-accent-2)", fontWeight: 800 }}>✓</span>
                <span><strong>{t}</strong><br /><span style={{ color: "var(--fa-text-muted)" }}>{d}</span></span>
              </li>
            ))}
          </ul>
        </div>
      </FaCard>
      <FaCard glass={false} style={{ width: "100%", maxWidth: 420, padding: 0, overflow: "hidden", alignSelf: "center", justifySelf: "center" }}>
      <div style={{ padding: "20px 24px 16px", borderBottom: "1px solid var(--fa-border)" }}>
        <p style={{ fontWeight: 800, fontSize: "var(--fa-t-lg)", letterSpacing: "0.04em", margin: 0 }}>Sign in</p>
        <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", margin: "4px 0 0", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {ORG_NAME} · Face attendance sign in
        </p>
      </div>
      <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <div role="group" aria-label="Sign in as" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {["Admin", "Student"].map((m) => (
            <FaButton
              key={m}
              type="button"
              variant="secondary"
              aria-pressed={mode === m}
              onClick={() => { setMode(m); setErr(""); }}
            >
              {m}
            </FaButton>
          ))}
        </div>
        <form onSubmit={submit} noValidate>
          <FaFormField label="Username" hint={mode === "Admin" ? "Operator username" : "Roll number, e.g. 2100030001"} errorId="login-username">
            {(describedBy) => (
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={mode === "Admin" ? "operator username" : "2100030001"}
                className="fa-input"
                autoComplete="username"
                aria-describedby={describedBy}
                aria-invalid={err ? true : undefined}
              />
            )}
          </FaFormField>
          <FaFormField label="Password" errorId="login-password">
            {(describedBy) => (
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type={showPw ? "text" : "password"}
                placeholder="••••••••"
                className="fa-input"
                autoComplete="current-password"
                aria-describedby={describedBy}
                aria-invalid={err ? true : undefined}
              />
            )}
          </FaFormField>
          <div style={{ display: "flex", justifyContent: "flex-end", margin: "-4px 0 12px" }}>
            <FaButton
              type="button"
              variant="secondary"
              aria-pressed={showPw}
              aria-label={showPw ? "Hide password" : "Show password"}
              onClick={() => setShowPw((v) => !v)}
            >
              {showPw ? "Hide" : "Show"}
            </FaButton>
          </div>
          {err && (
            <p className="fa-error" role="alert" style={{ fontSize: "var(--fa-t-sm)", margin: "0 0 12px" }}>
              {err}
            </p>
          )}
          <FaButton type="submit" loading={busy} disabled={busy} style={{ width: "100%" }}>
            {busy ? "Signing in…" : `Login as ${mode}`}
          </FaButton>
        </form>
        <p style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", margin: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Student accounts are provisioned by your administrator.
        </p>
        </div>
      </FaCard>
    </div>
  );
}
