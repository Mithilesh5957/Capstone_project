import { useMARP } from "../context/MARPContext";

const LINKS = [
  ["hub", "▦ DASHBOARD"],
  ["students", "◉ STUDENTS"],
  ["attendance", "▶ ATTENDANCE"],
  ["settings", "⚙ SETTINGS"],
];

export default function Sidebar({ tab, setTab }) {
  let marp = null;
  try {
    marp = useMARP();
  } catch {
    marp = null;
  }
  const ready = marp?.ready ?? null;
  const stage = marp?.telemetry?.stage || marp?.telemetry?.marp_state || "…";

  return (
    <aside className="flex w-64 shrink-0 flex-col gap-2 self-start lg:sticky lg:top-4 rounded-none border-4 border-black bg-white p-3 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
      <nav className="flex flex-col gap-2">
        {LINKS.map(([k, label]) => {
          const active = tab === k;
          return (
            <button key={k} onClick={() => setTab(k)}
              className={`rounded-none border-2 border-black px-4 py-2.5 text-left text-sm font-extrabold uppercase tracking-wider transition-all hover:translate-x-1 hover:translate-y-1 hover:shadow-none ${
                active
                  ? "bg-[#E2FF00] text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
                  : "bg-white text-black hover:bg-[#F4F4F0]"
              }`}>
              {label}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto rounded-none border-4 border-black bg-black p-3 text-[#E2FF00]">
        <p className="font-mono text-[11px] font-bold uppercase tracking-wider opacity-70">System Status</p>
        <p className="mt-1 flex items-center gap-2 font-extrabold uppercase tracking-wider text-sm">
          <span className={`inline-block h-3 w-3 rounded-none border-2 border-[#E2FF00] ${ready ? "bg-[#E2FF00]" : "bg-transparent animate-pulse"}`} />
          {ready ? "ONLINE" : "OFFLINE"}
        </p>
        <p className="mt-1 font-mono text-[11px] font-bold">
          {ready ? "MARP READY 200 OK" : `503 ${String(stage).toUpperCase()}`}
        </p>
      </div>
    </aside>
  );
}
