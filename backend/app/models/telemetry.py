"""MARP research telemetry — persistent state/chaos log (Phase 5)."""
from sqlalchemy import Column, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from ..core.database import Base


class MarpTelemetry(Base):
    __tablename__ = "marp_telemetry"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_type = Column(String(50), nullable=False)
    phase = Column(String(100), nullable=False, default="")
    vram_allocated_mb = Column(Float, nullable=False, default=0.0)
    load_duration_ms = Column(Float, nullable=False, default=0.0)
    active_chaos_params = Column(JSONB, nullable=False, default=dict)
