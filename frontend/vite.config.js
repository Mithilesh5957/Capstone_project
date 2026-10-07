import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Optional Vite entry (`npm run dev:vite`) — CRA `npm run build` remains the Docker path.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000", "/healthz": "http://localhost:8000" } },
  preview: { port: 3000 },
});
