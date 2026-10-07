import { useAuth } from "../context/AuthContext";

function Shield() {
  return (
    <span className="flex h-10 w-10 items-center justify-center rounded-none border-2 border-[#E2FF00] bg-black">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2l8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5l8-3z" fill="#E2FF00" />
        <path d="M8.5 12l2.5 2.5 4.5-5" stroke="#000" strokeWidth="2" fill="none" strokeLinecap="square" />
      </svg>
    </span>
  );
}

export default function Navbar() {
  const { session, role, logout } = useAuth();
  if (!session) return null;
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 rounded-none border-4 border-black bg-white px-4 py-3 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
      <div className="flex items-center gap-3">
        <Shield />
        <p className="font-extrabold uppercase tracking-wider text-xl">FACEATTEND</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="rounded-none border-2 border-black bg-white px-3 py-1.5 font-mono text-xs font-bold uppercase">
          {role === "Admin" ? `Admin [ADMIN]` : `Student [${session.username}]`}
        </span>
        <button onClick={logout}
          className="rounded-none border-2 border-black bg-[#DC2626] px-3 py-1.5 font-mono text-xs font-bold uppercase text-white transition-all hover:translate-x-1 hover:translate-y-1">
          Logout
        </button>
      </div>
    </header>
  );
}
