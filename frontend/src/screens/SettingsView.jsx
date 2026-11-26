import { useState } from "react";
import { FaButton, FaCard, FaFormField, FaModalFrame, FaSectionHeader, FaStatusIndicator, FaToast } from "../fa/primitives";

function marpStateInfo(telemetry) {
  // Presentation mapping over the real backend phase/state strings.
  // No states are invented: every branch matches an actual phase prefix
  // or readiness combination returned by the API.
  const phase = telemetry.phase || "";
  const ready = telemetry.model_ready && telemetry.db_connected;
  if (ready) return { tone: "ok", label: "Ready", detail: "Model loaded · database reachable" };
  if (phase.startsWith("timeout")) return { tone: "err", label: "Load timeout", detail: phase };
  if (phase.startsWith("db_failed")) return { tone: "err", label: "Database failure", detail: phase };
  if (phase.startsWith("detector_failed")) return { tone: "err", label: "Model failure", detail: phase };
  if (phase.startsWith("detector_busy")) return { tone: "warn", label: "Detector busy", detail: `${phase} — restart clears a hung detector` };
  if (phase.startsWith("chaos")) return { tone: "warn", label: "Chaos injected", detail: phase };
  if (!telemetry.model_ready) return { tone: "info", label: "Loading", detail: phase || "starting" };
  return { tone: "err", label: "Database down", detail: "Model ready · database unreachable — recovers automatically" };
}

function ChaosPanel({ telemetry, chaosMsg, chaos, delay, setDelay, refuse, setRefuse, dropRate, setDropRate, vram, setVram, modelStall, setModelStall, applyChaos }) {
  const [pending, setPending] = useState(null);
  const info = marpStateInfo(telemetry);
  const confirmAction = () => {
    if (pending) chaos(pending);
    setPending(null);
  };
  const rows = [
    ["Phase", telemetry.phase || "—"],
    ["Stage", telemetry.stage || "—"],
    ["Model", telemetry.model_ready ? "Loaded" : "Not loaded"],
    ["Database", telemetry.db_connected ? "Reachable" : "Unreachable"],
    ["Uptime", `${telemetry.uptime_s ?? 0}s`],
  ];
  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <FaCard>
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <FaStatusIndicator tone={info.tone}>{info.label}</FaStatusIndicator>
            <span style={{ fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)", color: "var(--fa-text-muted)", overflowWrap: "anywhere" }}>{info.detail}</span>
          </div>
          {rows.map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontFamily: "var(--fa-mono)", fontSize: "var(--fa-t-xs)" }}>
              <span style={{ color: "var(--fa-text-muted)" }}>&gt; {k}</span>
              <span style={{ overflowWrap: "anywhere", textAlign: "right" }}>{String(v)}</span>
            </div>
          ))}
        </div>
      </FaCard>
      <FaSectionHeader title="Chaos injection" sub="In-situ drills against the live backend. Destructive actions ask first." />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <FaButton variant="danger" onClick={() => setPending("db-drop")}>DB drop</FaButton>
        <FaButton variant="danger" onClick={() => setPending("unload-model")}>Unload model</FaButton>
        <FaButton variant="secondary" onClick={() => chaos("recover")}>Recover</FaButton>
      </div>
      <FaFormField label={`Simulated probe latency — ${delay}s (0–30)`} errorId="chaos-delay">
        {(describedBy) => (
          <input type="range" min="0" max="30" step="1" value={delay} onChange={(e) => setDelay(Number(e.target.value))} aria-describedby={describedBy} style={{ width: "100%", accentColor: "var(--fa-accent)" }} />
        )}
      </FaFormField>
      <FaButton variant="secondary" aria-pressed={refuse} onClick={() => setRefuse((v) => !v)}>
        {refuse ? "■ Probe refusal on (503)" : "□ Force probe refusal (503)"}
      </FaButton>
      <FaFormField label={`Frame drop rate — ${Math.round(dropRate * 100)}% (0–100)`} errorId="chaos-drop">
        {(describedBy) => (
          <input type="range" min="0" max="1" step="0.05" value={dropRate} onChange={(e) => setDropRate(Number(e.target.value))} aria-describedby={describedBy} style={{ width: "100%", accentColor: "var(--fa-accent)" }} />
        )}
      </FaFormField>
      <FaButton variant="secondary" aria-pressed={vram} onClick={() => setVram((v) => !v)}>
        {vram ? "■ VRAM exhaustion on (503)" : "□ Simulate VRAM exhaustion"}
      </FaButton>
      <FaButton variant="secondary" aria-pressed={modelStall} onClick={() => setModelStall((v) => !v)}>
        {modelStall ? "■ Model stall on (timeout)" : "□ Model stall drill"}
      </FaButton>
      <FaButton variant="primary" onClick={applyChaos}>Apply chaos injection</FaButton>
      {chaosMsg && <FaToast>{chaosMsg}</FaToast>}
      {pending && (
        <FaModalFrame
          title={pending === "db-drop" ? "Drop the database connection?" : "Unload the model?"}
          description={
            pending === "db-drop"
              ? "Simulates a database outage. Readiness goes 503 until you run Recover. Safe on a demo backend; never use against a live service."
              : "Simulates model loss. Readiness goes 503 until you run Recover. In-flight sessions keep their data."
          }
          onCancel={() => setPending(null)}
          actions={
            <>
              <FaButton variant="secondary" onClick={() => setPending(null)}>Cancel</FaButton>
              <FaButton variant="danger" onClick={confirmAction} data-autofocus>Confirm</FaButton>
            </>
          }
        />
      )}
    </div>
  );
}

export default function SettingsView({ telemetry, ready, chaosMsg, chaos, delay, setDelay, refuse, setRefuse, dropRate, setDropRate, vram, setVram, modelStall, setModelStall, applyChaos, termLog }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
    <FaCard>
      <div style={{ padding: "16px 16px 0" }}>
        <FaSectionHeader
          title="Settings & MARP chaos hub"
          sub={`Phase ${telemetry.phase || "—"} · Stage ${telemetry.stage || "—"} · ${ready ? "200 OK" : "503"}`}
        />
      </div>
      <ChaosPanel
        telemetry={telemetry} chaosMsg={chaosMsg} chaos={chaos}
        delay={delay} setDelay={setDelay} refuse={refuse} setRefuse={setRefuse}
        dropRate={dropRate} setDropRate={setDropRate} vram={vram} setVram={setVram}
        modelStall={modelStall} setModelStall={setModelStall}
        applyChaos={applyChaos}
      />
    </FaCard>
    <FaCard>
      <div style={{ padding: 16 }}>
        <FaSectionHeader title="Readiness terminal" sub="Live · newest first" />
        <ul className="fa-log" style={{ marginTop: 12, height: "12rem" }} aria-label="MARP readiness event log">
          {(termLog || []).slice().reverse().map((t) => (
            <li key={t.id}>[{t.time}] {t.text}</li>
          ))}
          {(!termLog || termLog.length === 0) && <li>Waiting for first health check…</li>}
        </ul>
      </div>
    </FaCard>
    </div>
  );
}
