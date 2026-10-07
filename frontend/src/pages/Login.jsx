import { useState } from "react";
import { useAuth } from "../context/AuthContext";

const ADMIN_EMAIL = "admin@college.edu";
const ADMIN_USER = "admin";
const ADMIN_PASSWORD = "admin123";

const canonical = (v) => {
  const raw = (v || "").trim();
  if (raw.includes("@")) return raw.split("@")[0].trim() || raw;
  return raw;
};

export default function Login() {
  const { login } = useAuth();
  const [mode, setMode] = useState("Admin");
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const doLogin = async (idValue, pwValue) => {
    setBusy(true);
    try {
      await login(idValue, pwValue, mode);
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e) => {
    e?.preventDefault();
    setErr("");
    const u = identity.trim();
    if (mode === "Admin") {
      if (canonical(u).toLowerCase() !== ADMIN_USER || password !== ADMIN_PASSWORD) {
        setErr("Invalid operator credentials — use the demo override pill below.");
        return;
      }
      await doLogin(u, password);
      return;
    }
    if (!u || password !== "student123") {
      setErr("Student: any Roll No. + password student123.");
      return;
    }
    await doLogin(u, password);
  };

  const fillDemo = async () => {
    setMode("Admin");
    setIdentity(ADMIN_EMAIL);
    setPassword(ADMIN_PASSWORD);
    setErr("");
    await doLogin(ADMIN_EMAIL, ADMIN_PASSWORD);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper p-4 font-sans text-black">
      <div className="w-full max-w-md rounded-none border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div className="border-b-4 border-black bg-neon px-6 py-4">
          <p className="font-extrabold uppercase tracking-wider text-xl">FACEATTEND</p>
          <p className="font-mono text-xs font-bold uppercase tracking-wider">Operator Sign In — /login</p>
        </div>
        <div className="space-y-3 p-6">
          <div className="grid grid-cols-2 gap-2 border-4 border-black bg-paper p-1">
            {["Admin", "Student"].map((m) => (
              <button key={m} type="button" onClick={() => { setMode(m); setErr(""); }}
                className={`px-4 py-2 text-xs font-extrabold uppercase tracking-wider ${mode === m ? "bg-black text-neon" : "bg-white text-black hover:bg-paper"}`}>{m}</button>
            ))}
          </div>
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-xs font-extrabold uppercase tracking-wider">
              {mode === "Admin" ? "EMAIL OR USERNAME" : "ROLL NO. / STUDENT ID"}
              <input value={identity} onChange={(e) => setIdentity(e.target.value)}
                placeholder={mode === "Admin" ? "admin@college.edu" : "2100030001"}
                autoComplete="username"
                className="mt-1 w-full rounded-none border-4 border-black bg-paper p-3 font-mono text-sm font-bold focus:bg-white focus:outline-none" />
            </label>
            <label className="block text-xs font-extrabold uppercase tracking-wider">PASSWORD
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password"
                placeholder="••••••••" autoComplete="current-password"
                className="mt-1 w-full rounded-none border-4 border-black bg-paper p-3 font-mono text-sm font-bold focus:bg-white focus:outline-none" />
            </label>
            {err && <p className="rounded-none border-2 border-black bg-[#DC2626] px-3 py-2 font-mono text-xs font-bold text-white">{err}</p>}
            <button type="submit" disabled={busy}
              className="w-full rounded-none border-4 border-black bg-black px-6 py-3 font-extrabold uppercase tracking-wider text-neon transition-all duration-150 hover:translate-x-1 hover:translate-y-1 hover:bg-neon hover:text-black hover:shadow-none disabled:opacity-50">
              {busy ? "SIGNING IN…" : `LOGIN AS ${mode.toUpperCase()}`}
            </button>
          </form>
          <button type="button" onClick={fillDemo} disabled={busy}
            className="w-full cursor-pointer rounded-none border-2 border-black bg-neon px-2 py-2 text-center font-mono text-[11px] font-bold uppercase text-black disabled:opacity-50">
            ADM&nbsp;&nbsp;{ADMIN_EMAIL} / {ADMIN_PASSWORD} — TAP TO LOGIN
          </button>
          <p className="font-mono text-[11px] uppercase tracking-wider">Student — any ID / student123</p>
        </div>
      </div>
    </div>
  );
}

export { ADMIN_EMAIL, ADMIN_USER, ADMIN_PASSWORD, canonical };
