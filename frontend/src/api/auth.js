import { v1 } from "./client";

export const login = (username, password, role) =>
  v1("/auth/login",
    { method: "POST", body: JSON.stringify({ username, password, role }) },
    "/api/auth/login");
