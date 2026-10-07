import { v1 } from "./client";

export const listStudents = () => v1("/students", {}, "/api/students");

export const enrollStudent = (payload) =>
  v1("/students/enroll",
    { method: "POST", body: JSON.stringify(payload) },
    "/api/students/enroll");

export const studentAttendance = (id) =>
  v1(`/students/${encodeURIComponent(id)}/attendance`, {},
    `/api/students/${encodeURIComponent(id)}/attendance`);
