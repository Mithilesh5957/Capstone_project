import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { chaosStatus, injectChaos, marpReadiness, marpStatus, resetChaos } from "../api/marp";

const MARPCtx = createContext(null);

export function MARPProvider({ children, intervalMs = 2000 }) {
  const [telemetry, setTelemetry] = useState({
    phase: "starting", marp_state: "UNINITIALIZED", stage: "UNINITIALIZED",
    model_ready: false, db_connected: false, uptime_s: 0, active_session: {},
    metrics: null, chaos: null,
  });
  const [ready, setReady] = useState(null);
  const [toast, setToast] = useState(null);
  const [termLog, setTermLog] = useState(() => ([
    { id: 0, time: new Date().toLocaleTimeString("en-GB"), text: "terminal online — polling readiness every 2s", tone: "dim" },
  ]));
  const ref = useRef(telemetry);
  ref.current = telemetry;

  const pushTerm = useCallback((text, tone = "info") => {
    const time = new Date().toLocaleTimeString("en-GB");
    setTermLog((p) => [...p.slice(-119), { id: Date.now() + Math.random(), time, text, tone }]);
  }, []);

  const clearTerm = useCallback(() => setTermLog([]), []);

  const notify = useCallback((text, tone = "info") => {
    setToast({ id: Date.now(), text, tone });
    setTimeout(() => setToast((t) => (t && Date.now() - t.id > 2800 ? null : t)), 3000);
  }, []);

  const poll = useCallback(async () => {
    try {
      const [s, h, c] = await Promise.all([
        marpStatus().catch(() => null),
        marpReadiness(),
        chaosStatus().catch(() => null),
      ]);
      if (s) {
        setTelemetry({
          phase: s.phase || "—",
          marp_state: s.marp_state || s.stage || "—",
          stage: s.stage || s.metrics?.stage || s.marp_state || "—",
          model_ready: !!s.model_ready,
          db_connected: !!(s.db_connected ?? s.db_ready),
          uptime_s: s.uptime_s ?? s.metrics?.uptime_s ?? 0,
          active_session: s.active_session || {},
          metrics: s.metrics || null,
          chaos: c?.chaos || s.chaos || null,
        });
      }
      setReady(h ? h.ok : false);
      if (!h) pushTerm("Health Check: unreachable — connection refused", "err");
      else if (h.ok) pushTerm(`Health Check: 200 OK (${s?.phase || s?.marp_state || "ready"})`, "ok");
      else if (/reload/i.test(`${h.body?.error || ""} ${s?.phase || ""}`))
        pushTerm(`Health Check: ${h.status} — recovering (${s?.phase || h.body?.error})`, "warn");
      else pushTerm(`Health Check: ${h.status} — ${h.body?.error || h.body?.phase || "failure"}`, "err");
      return { s, h };
    } catch {
      setReady(false);
      pushTerm("Health Check: poll failed", "err");
      return null;
    }
  }, [pushTerm]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, intervalMs);
    return () => clearInterval(id);
  }, [poll, intervalMs]);

  const applyChaos = useCallback(async (cfg) => {
    pushTerm(`CHAOS INJECT: ${JSON.stringify(cfg)}`, "info");
    try {
      const r = await injectChaos(cfg);
      pushTerm(`backend: ${r.message || "chaos applied"}`, "err");
      notify("Chaos injection applied live", "err");
      await poll();
      return r;
    } catch (e) {
      pushTerm(`inject failed: ${e.message}`, "err");
      notify(`Inject failed: ${e.message}`, "err");
      throw e;
    }
  }, [poll, pushTerm, notify]);

  const clearChaos = useCallback(async () => {
    pushTerm("CHAOS RESET: restoring standard operations…", "info");
    try {
      const r = await resetChaos();
      pushTerm("backend: chaos cleared", "warn");
      notify("Chaos cleared — recovering", "warn");
      await poll();
      return r;
    } catch (e) {
      pushTerm(`reset failed: ${e.message}`, "err");
      throw e;
    }
  }, [poll, pushTerm, notify]);

  return (
    <MARPCtx.Provider value={{ telemetry, ready, termLog, toast, notify, pushTerm, clearTerm, poll, refresh: poll, applyChaos, clearChaos }}>
      {children}
      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] border-2 border-black bg-[#E2FF00] px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
          {toast.text}
        </div>
      )}
    </MARPCtx.Provider>
  );
}

export const useMARP = () => useContext(MARPCtx);
