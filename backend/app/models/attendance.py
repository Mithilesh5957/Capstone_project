from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, func
from datetime import date as _date
from ..core.database import Base


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id = Column(Integer, primary_key=True)
    session_name = Column(String(200), nullable=False)
    date = Column(Date, nullable=False, default=_date.today)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(50), ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="Absent")
    marked_at = Column(DateTime(timezone=True), nullable=True)
