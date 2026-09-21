-- PostgreSQL schema for real-time video analytics detection logs.
CREATE TABLE IF NOT EXISTS detection_events (
    id             SERIAL PRIMARY KEY,
    timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detection_type VARCHAR(50) NOT NULL,          -- e.g. 'face', 'person'
    confidence     DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS idx_detection_events_timestamp ON detection_events (timestamp DESC);
