import { useMARP } from "../context/MARPContext";

export default function SystemStatusBadge({ ready }) {
  const ctx = (() => { try { return useMARP(); } catch { return null; } })();
  const live = ready ?? ctx?.ready ?? null;
  const stage = ctx?.telemetry?.stage || ctx?.telemetry?.marp_state || "";
  if (live === null) return <span className="nb-tag nb-tag-white">… PROBING</span>;
  return (
    <span className={`nb-tag ${live ? "nb-tag-yellow" : "nb-tag-red"}`}>
      <span className={`mr-1 inline-block h-2 w-2 rounded-none border border-black ${live ? "bg-black" : "bg-white nb-pulse"}`} />
      {live ? `READY ● ${stage}` : `FAULT ● ${stage || "UNHEALTHY"}`}
    </span>
  );
}
