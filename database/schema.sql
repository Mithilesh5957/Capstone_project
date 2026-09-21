-- ============================================================================
-- AI Face Detection Attendance System — PostgreSQL schema
-- Retains DevOps detection_events table; adds students / sessions / records.
-- This file is auto-applied on first `docker compose up` via:
--   ./database/schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
-- Backend also runs Base.metadata.create_all() so tables exist even if the
-- volume already existed before this schema was added (no manual migration).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Students registry with 4-angle face embeddings
-- embeddings: JSONB list of floats (mean vector of Front/Left/Right/Up scans).
-- Computed backend-side with OpenCV (64x64 gray, L2-normalized, ~4096 dims).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id          SERIAL PRIMARY KEY,
    student_id  VARCHAR(50)  NOT NULL UNIQUE,   -- e.g. '2100030001'
    name        VARCHAR(100) NOT NULL,
    branch      VARCHAR(100) NOT NULL DEFAULT 'CSE',
    embeddings  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_students_student_id ON students (student_id);

-- ----------------------------------------------------------------------------
-- 2. Attendance sessions (one per class / lab / day)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id           SERIAL PRIMARY KEY,
    session_name VARCHAR(200) NOT NULL,
    date         DATE         NOT NULL DEFAULT CURRENT_DATE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 3. Attendance records — one row per (session, student).
-- status: 'Present' | 'Absent' (default Absent on session start).
-- ReID safeguard: backend marks Present once; repeats are no-ops (no dup rows
-- because of UNIQUE(session_id, student_id)).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance_records (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER      NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id  VARCHAR(50)  NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    status      VARCHAR(20)  NOT NULL DEFAULT 'Absent' CHECK (status IN ('Present', 'Absent')),
    marked_at   TIMESTAMPTZ,
    UNIQUE (session_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_records_session ON attendance_records (session_id);
CREATE INDEX IF NOT EXISTS idx_records_student ON attendance_records (student_id);

-- ----------------------------------------------------------------------------
-- 4. DevOps detection log (RETAINED — powers telemetry + fault-injection AC-2)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detection_events (
    id             SERIAL PRIMARY KEY,
    timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detection_type VARCHAR(50) NOT NULL,          -- e.g. 'face', 'person'
    confidence     DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS idx_detection_events_timestamp ON detection_events (timestamp DESC);
