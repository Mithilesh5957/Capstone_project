-- FACEATTEND MARP — database setup (mirrors database/schema.sql; also applied via create_all).
\connect analytics;

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    branch VARCHAR(100) NOT NULL DEFAULT 'CSE',
    embeddings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_students_student_id ON students (student_id);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id SERIAL PRIMARY KEY,
    session_name VARCHAR(200) NOT NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id VARCHAR(50) NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'Absent' CHECK (status IN ('Present', 'Absent')),
    marked_at TIMESTAMPTZ,
    UNIQUE (session_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_records_session ON attendance_records (session_id);
CREATE INDEX IF NOT EXISTS idx_records_student ON attendance_records (student_id);

CREATE TABLE IF NOT EXISTS detection_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detection_type VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1)
);
CREATE INDEX IF NOT EXISTS idx_detection_events_timestamp ON detection_events (timestamp DESC);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL DEFAULT 'admin',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS marp_telemetry (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    phase VARCHAR(100) NOT NULL DEFAULT '',
    vram_allocated_mb DOUBLE PRECISION NOT NULL DEFAULT 0,
    load_duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    active_chaos_params JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_marp_telemetry_timestamp ON marp_telemetry (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_marp_telemetry_event ON marp_telemetry (event_type);
