"""Operator credentials table (mock SSO fallback; admin login works without rows)."""
from sqlalchemy import Column, DateTime, Integer, String, func
from ..core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False, default="")
    role = Column(String(20), nullable=False, default="admin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
