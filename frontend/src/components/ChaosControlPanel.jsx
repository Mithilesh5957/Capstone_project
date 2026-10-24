import { useState } from "react";
import { chaos, exportTelemetryCsv } from "../api/marp";
import { useMARP } from "../context/MARPContext";

export default function ChaosControlPanel() {
  const { telemetry, pushTerm, applyChaos, clearChaos } = useMARP();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [delay, setDelay] = useState(0);
  const [drop, setDrop] = useState(0);
  const [refuse, setRefuse] = useState(false);
  const [vram, setVram] = useState(false);

  const run = async (kind) => {
    const labels = { "db-drop": "DB Drop", "unload-model": "Model Unload", recover: "Recovery" };
    pushTerm(`SYSTEM ADMIN: Initiating ${labels[kind] || kind}...`, "info");
    try {
      const r = await chaos(kind);
      setMsg(`Chaos [${kind}] -> ${r.phase}`);
      pushTerm(`backend: ${r.message || r.phase}`, kind === "recover" ? "warn" : "err");
    } catch {
      setMsg("Chaos request failed (backend unreachable)");
      pushTerm("backend unreachable — command failed", "err");
    }
  };

  const apply = async () => {
    setBusy(true);
    try {
      const r = await applyChaos({
        simulated_latency_sec: Number(delay),
        frame_drop_rate: Number(drop),
        artificial_probe_failure: refuse,
        simulate_vram_exhaustion: vram,
      });
      setMsg(`Injected: delay ${delay}s / drop ${drop} / refuse ${String(refuse)} / vram ${String(vram)}`);
      return r;
    } finally {
      setBusy(false);
    }
  };

  const m = telemetry.metrics || {};
  const diag = [
    ["STAGE", telemetry.stage || telemetry.marp_state || "—"],
    ["PHASE", telemetry.phase],
    ["MODEL", telemetry.model_ready ? "LOADED" : "LOADING"],
    ["LOAD MS", m.model_load_duration_ms ?? "—"],
    ["VRAM MB", m.vram_allocated_mb ?? "—"],
    ["CHECKS", m.total_health_checks_served ?? "—"],
    ["UPTIME", `${telemetry.uptime_s}s`],
  ];

  return (
    <div className="border-t-2 border-black">
      <div className="border-b-2 border-black bg-black px-4 py-2">
        <p className="nb-title text-xs text-neon">MARP IN-SITU CHAOS CONTROL</p>
      </div>
      <div className="space-y-3 p-4">
        <div className="nb-card-black p-3 font-mono text-xs">
          {diag.map(([k, v]) => (
            <div key={k} className="flex justify-between py-0.5">
              <span className="opacity-70">&gt; {k.toLowerCase()}</span>
              <span className={`font-bold ${k === "STAGE" ? "nb-pulse" : ""}`}>{String(v)}</span>
            </div>
          ))}
          <div className="mt-2 flex items-center gap-2 border-t border-neon/30 pt-2">
            <span className={`inline-block h-3 w-3 rounded-none border border-neon ${telemetry.model_ready ? "bg-neon" : "bg-transparent nb-pulse"}`} />
            <span className="text-[11px] uppercase tracking-wider">health pulse: {telemetry.model_ready ? "steady" : "warming"}</span>
          </div>
        </div>

        <div>
          <label className="nb-title text-xs">ARTIFICIAL MODEL LOAD DELAY — {delay}s (0–30)</label>
          <input type="range" min="0" max="30" step="1" value={delay} onChange={(e) => setDelay(Number(e.target.value))}
            className="w-full accent-black" />
        </div>
        <div>
          <label className="nb-title text-xs">FRAME DROP RATE — {drop}</label>
          <input type="range" min="0" max="1" step="0.1" value={drop} onChange={(e) => setDrop(Number(e.target.value))}
            className="w-full accent-black" />
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setRefuse((v) => !v)}
            className={`nb-tag cursor-pointer ${refuse ? "nb-tag-red" : "nb-tag-white"}`}>
            {refuse ? "■ PROBE REFUSAL ON (503)" : "□ FORCE PROBE REFUSAL (503)"}
          </button>
          <button onClick={() => setVram((v) => !v)}
            className={`nb-tag cursor-pointer ${vram ? "nb-tag-red" : "nb-tag-white"}`}>
            {vram ? "■ VRAM EXHAUSTION ON" : "□ SIMULATE VRAM EXHAUSTION"}
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <button onClick={apply} disabled={busy} className="nb-btn nb-btn-lime disabled:opacity-50">
            {busy ? "INJECTING…" : "APPLY CHAOS INJECTION"}
          </button>
          <button onClick={async () => { await clearChaos(); setMsg("Chaos cleared — standard ops restored."); }} className="nb-btn nb-btn-white">
            RESET
          </button>
        </div>

        <div className="flex flex-wrap gap-2 border-t-2 border-black pt-3">
          <button onClick={() => run("db-drop")} className="nb-btn nb-btn-red text-xs">DB DROP</button>
          <button onClick={() => run("unload-model")} className="nb-btn nb-btn-black text-xs">UNLOAD MODEL</button>
          <button onClick={() => run("recover")} className="nb-btn nb-btn-white text-xs">RECOVER</button>
        </div>
        <div className="border-t-2 border-black pt-3">
          <button
            onClick={async () => {
              try {
                pushTerm("EXPORT: downloading marp_research_data.csv…", "info");
                await exportTelemetryCsv();
                setMsg("Telemetry exported → marp_research_data.csv");
                pushTerm("EXPORT: marp_research_data.csv saved", "ok");
              } catch (e) {
                setMsg(`Export failed: ${e.message}`);
                pushTerm(`EXPORT failed: ${e.message}`, "err");
              }
            }}
            className="brutal-btn w-full border-4 border-black bg-black px-6 py-3 text-[#E2FF00] shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
            ⤓ EXPORT TELEMETRY (CSV)
          </button>
          <p className="mt-1 font-mono text-[11px] uppercase">Research dump: state changes + flattened chaos knobs</p>
        </div>
        {msg && <p className="border-2 border-black bg-paper p-2 font-mono text-xs">{msg}</p>}
      </div>
    </div>
  );
}
