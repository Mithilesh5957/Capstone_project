from sqlalchemy import Column, DateTime, Float, Integer, String, func
from ..core.database import Base


class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    detection_type = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
