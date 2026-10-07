from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from ..core.database import Base

try:
    _EMB = JSONB
except Exception:  # pragma: no cover
    from sqlalchemy import JSON as _EMB  # type: ignore


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    branch = Column(String(100), nullable=False, default="CSE")
    embeddings = Column(_EMB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
