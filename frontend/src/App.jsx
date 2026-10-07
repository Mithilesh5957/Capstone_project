import { useCallback, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { MARPProvider, useMARP } from "./context/MARPContext";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Students from "./pages/Students";
import Attendance from "./pages/Attendance";
import Settings from "./pages/Settings";
import { listStudents } from "./api/students";
import { roster, recentLogs } from "./api/attendance";

function Shell() {
  const { session, role } = useAuth();
  const { telemetry } = useMARP();
  const [tab, setTab] = useState("hub");
  const [students, setStudents] = useState([]);
  const [attendanceLogs, setAttendanceLogs] = useState([]);

  const refreshStudents = useCallback(async () => {
    try { setStudents(await listStudents()); } catch { /* loading */ }
  }, []);

  const refreshLogs = useCallback(async () => {
    try {
      const sid = telemetry?.active_session?.id;
      const r = await roster(sid || undefined);
      setAttendanceLogs(r.records || []);
      return;
    } catch { /* fall through */ }
    try {
      const r = await recentLogs(50);
      setAttendanceLogs((Array.isArray(r) ? r : []).map((e) => ({
        student_id: "—", name: e.detection_type || "face", status: "Detected",
        marked_at: e.timestamp, confidence: e.confidence,
      })));
    } catch { /* leave */ }
  }, [telemetry?.active_session?.id]);

  useEffect(() => { refreshStudents(); refreshLogs(); }, [refreshStudents, refreshLogs]);
  useEffect(() => {
    const id = setInterval(() => { refreshStudents(); refreshLogs(); }, 5000);
    return () => clearInterval(id);
  }, [refreshStudents, refreshLogs]);

  if (!session) return <Login />;

  return (
    <div className="min-h-screen bg-paper font-sans text-black">
      <div className="w-full space-y-4 p-4 lg:p-6">
        <Navbar />
        {role === "Student" ? (
          <Students students={students.filter((s) => s.student_id === (session.student_id || session.username))} onRefresh={refreshStudents} />
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row">
            <Sidebar tab={tab} setTab={setTab} />
            <main className="min-w-0 flex-1">
              {tab === "hub" && <Dashboard students={students} setTab={setTab} />}
              {tab === "students" && <Students students={students} onRefresh={refreshStudents} />}
              {tab === "attendance" && <Attendance students={students} attendanceLogs={attendanceLogs} refreshLogs={refreshLogs} />}
              {tab === "settings" && <Settings />}
            </main>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <MARPProvider>
        <Shell />
      </MARPProvider>
    </AuthProvider>
  );
}
