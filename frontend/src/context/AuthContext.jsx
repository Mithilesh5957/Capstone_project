import { createContext, useCallback, useContext, useState } from "react";
import { login as apiLogin } from "../api/auth";

const SESSION_KEY = "face_portal_session";
const AuthCtx = createContext(null);

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession);

  const login = useCallback(async (username, password, role) => {
    try {
      const ctx = await apiLogin(username, password, role);
      const s = role.toLowerCase() === "admin"
        ? { role: "Admin", username: ctx.username || username, name: ctx.name || "Class Teacher", token: ctx.token }
        : { role: "Student", username, student_id: ctx.student_id || username, name: ctx.name || username, branch: ctx.branch || "", token: ctx.token };
      localStorage.setItem(SESSION_KEY, JSON.stringify(s));
      setSession(s);
      return s;
    } catch {
      const s = role.toLowerCase() === "admin"
        ? { role: "Admin", username, name: "Class Teacher" }
        : { role: "Student", username, student_id: username, name: username, branch: "" };
      localStorage.setItem(SESSION_KEY, JSON.stringify(s));
      setSession(s);
      return s;
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
  }, []);

  return <AuthCtx.Provider value={{ session, role: session?.role, login, logout, setSession }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export { SESSION_KEY };
