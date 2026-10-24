# ARCHITECTURE — FACEATTEND Data Flow & MARP Probe Mapping

## 1. Request lifecycle (live frame)

```
1. Browser <video> (getUserMedia)
2. <canvas> snapshot 320×240 → dataURL JPEG base64
3. WS send {image}  ── /api/v1/attendance/ws/detect?token=JWT ──▶ FastAPI
4. verify_token(query param) → 4401 close on failure (no headers on WS)
5. MARP-ready guard: if !model_ready → {error:model loading, phase} (socket stays open)
6. svc.process_live_frame(image):
     fd.decode_frame → fr.detect_and_identify (YOLO→MediaPipe→Haar 640×480,
       embedding_for_bbox, match_student ≤0.85 → maybe_mark_present w/ marked_memory)
     → fr.log_detections → {detections, newly_marked, active_session}
7. WS ack → frontend: setDetections (canvas overlay) + liveRoster update
   + roster refresh only if newly_marked non-empty
8. Backpressure: next frame sent only after ack or 1s timeout (80ms pacing)
```

HTTP fallback (`POST /detect`) shares `detect_and_identify` but has no ack pacing; WS is the primary path. Bounding boxes are backend-canonical 640×480; frontend syncs `canvas.width=video.videoWidth` and scales `sx=W/640, sy=H/480`.

## 2. MARP state machine → K8s probes

```
UNINITIALIZED --(lifespan start_background_load)--> LOADING_WEIGHTS
  --(MODEL_LOAD_SECONDS + chaos delay, 1s slices)--> warming_up_detector
  --(FaceDetector.load: yolo→mediapipe→haar)--> DB_CONNECTED
  --(Base.create_all + SELECT 1)--> READY (model_load_duration_ms, vram_allocated_mb)
  --(any exception / simulate_vram_exhaustion / model_stall)--> FAILED / chaos phases
```

Endpoints:
- `GET /api/v1/marp/healthz/liveness` → `{status:alive, marp_state, stage}` (process alive; K8s `initialDelay 15, period 20`).
- `GET /api/v1/marp/healthz/readiness` → `ENGINE.readiness()` → 503 unless `model_ready && db_ready` (+ chaos overrides: probe refusal / VRAM / DB / model) → 200 at READY (K8s `initialDelay 5, period 5, failureThreshold 30` = 150s budget for ~24s warmup + DB reconnect).

```yaml
# k8s/backend-deployment.yaml (excerpt)
readinessProbe:
  httpGet: {path: /api/v1/marp/healthz/readiness, port: http}
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 30
```

Effect: K8s Endpoints for `faceattend-backend:8000` remain empty during 503, so the frontend `LoadBalancer :80` and camera WS clients never hit a cold model — no dropped frames during VRAM loading. Compose `healthcheck: curl -f .../readiness` enforces the same ordering (`frontend depends_on backend healthy`, `backend depends_on db healthy`).

## 3. Persistence map

| Write path | Table | Key |
|---|---|---|
| `students_router.enroll` | `students` | `student_id UNIQUE`, `embeddings JSONB` mean vector |
| `attendance_service.start_session` | `attendance_sessions` + N×`attendance_records` | pre-created `Absent` rows |
| `maybe_mark_present` (via `process_live_frame`) | `attendance_records` | `UNIQUE(session_id,student_id)`, `marked_memory` in-process dedup |
| `fr.log_detections` | `detection_events` | `{detection_type, confidence}` |
| `auth_router._ensure_admin` | `users` | bcrypt `password_hash`, JWT `sub/role/exp` |
| `marp_engine` transitions | `marp_telemetry` | `{event_type, phase, vram, load_ms, active_chaos_params JSONB}` async daemon insert, never blocks inference |

`GET /api/v1/marp/telemetry/export` (admin JWT) flattens `active_chaos_params` to `chaos_<knob>` CSV columns (`marp_research_data.csv`) for Excel/Python plotting — the research deliverable.
