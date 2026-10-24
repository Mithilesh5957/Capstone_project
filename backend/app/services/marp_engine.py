"""MARP state machine + in-situ chaos injector (singleton MARPEngine).

Stages: UNINITIALIZED -> DB_CONNECTED -> LOADING_WEIGHTS -> READY (or FAILED).
Legacy phase strings ('starting','loading_model_weights',...) are kept in the
module-level ``state`` dict so old probes (/healthz/*, tests/) agree with MARP.

Metrics: startup_timestamp, model_load_duration_ms, vram_allocated_mb,
total_health_checks_served, active_chaos_parameters.
Chaos: simulated_latency_sec, simulate_vram_exhaustion, artificial_probe_failure
(+ legacy vram_latency_s / frame_drop_rate / model_stall / SIMULATED_* flags).
"""
from __future__ import annotations
import threading
import time
from typing import Any, Dict, Tuple
from ..core import config

START_TIME = time.time()

# ---- legacy mutable surface (tests + old UI depend on these names) ----
state: Dict[str, Any] = {"phase": "starting", "model_ready": False, "db_ready": False}
face_cascade = None  # owned by FaceDetector; mirrored here for legacy imports
SIMULATED_DB_FAILURE = False
SIMULATED_MODEL_FAILURE = False
chaos_knobs: Dict[str, Any] = dict(config.CHAOS_DEFAULTS)

_session_lock = threading.Lock()
active_session: Dict[str, Any] = {"id": None, "name": None}
marked_memory: set = set()

PHASE_TO_MARP = {
    "starting": "UNINITIALIZED",
    "loading_model_weights": "LOADING_WEIGHTS",
    "warming_up_detector": "LOADING_WEIGHTS",
    "connecting_postgres": "DB_CONNECTED",
    "ready": "READY",
    "reloading": "LOADING_WEIGHTS",
}


class MARPEngine:
    """Thread-safe singleton tracking lifecycle, metrics and chaos."""

    _instance: "MARPEngine | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "MARPEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self._state_lock = threading.RLock()
        self.stage: str = "UNINITIALIZED"
        self.startup_timestamp: float = START_TIME
        self.model_load_duration_ms: float = 0.0
        self.vram_allocated_mb: float = 0.0
        self.total_health_checks_served: int = 0
        self.detector_backend: str = "none"
        self.last_error: str | None = None

    # -- state helpers -------------------------------------------------
    def set_stage(self, stage: str, phase: str | None = None) -> None:
        with self._state_lock:
            self.stage = stage
            if phase is not None:
                state["phase"] = phase
        _log_telemetry_async("STATE_CHANGE")

    def mark_ready(self, backend: str, duration_ms: float, vram_mb: float) -> None:
        with self._state_lock:
            self.stage = "READY"
            self.detector_backend = backend
            self.model_load_duration_ms = duration_ms
            self.vram_allocated_mb = vram_mb
            self.last_error = None
            state["model_ready"] = True
            state["phase"] = "ready"
        _log_telemetry_async("STATE_CHANGE")

    def mark_failed(self, error: str, phase: str) -> None:
        with self._state_lock:
            self.stage = "FAILED"
            self.last_error = error
            state["phase"] = phase
        _log_telemetry_async("STATE_CHANGE")

    def chaos_snapshot(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(chaos_knobs)

    def metrics(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "startup_timestamp": self.startup_timestamp,
                "uptime_s": round(time.time() - self.startup_timestamp, 1),
                "stage": self.stage,
                "model_load_duration_ms": round(self.model_load_duration_ms, 1),
                "vram_allocated_mb": round(self.vram_allocated_mb, 1),
                "total_health_checks_served": self.total_health_checks_served,
                "detector_backend": self.detector_backend,
                "active_chaos_parameters": dict(chaos_knobs),
                "last_error": self.last_error,
            }

    def record_probe(self) -> None:
        with self._state_lock:
            self.total_health_checks_served += 1

    # -- readiness ------------------------------------------------------
    def readiness(self) -> Tuple[Dict[str, Any], int]:
        """Central readiness evaluation. Applies chaos overrides first."""
        from sqlalchemy import text
        from ..core.database import engine
        self.record_probe()
        uptime = round(time.time() - START_TIME, 1)

        # Artificial probe refusal (chaos) wins over everything.
        if chaos_knobs.get("artificial_probe_failure"):
            return ({
                "phase": state.get("phase", ""), "marp_state": marp_state(),
                "stage": self.stage, "model_ready": state.get("model_ready", False),
                "db_ready": state.get("db_ready", False), "uptime_s": uptime,
                "progress_duration_s": uptime,
                "error": "Artificial probe failure (chaos)",
                "artificial_probe_failure": True,
                **self.metrics(),
            }, 503)
        if chaos_knobs.get("simulate_vram_exhaustion"):
            return ({
                "phase": state.get("phase", ""), "marp_state": marp_state(),
                "stage": self.stage, "uptime_s": uptime,
                "progress_duration_s": uptime,
                "error": "VRAM exhausted (chaos): model buffers unavailable",
                "simulate_vram_exhaustion": True,
                **self.metrics(),
            }, 503)
        if SIMULATED_DB_FAILURE:
            return ({
                "phase": state["phase"], "marp_state": marp_state(),
                "stage": self.stage, "model_ready": state["model_ready"],
                "db_ready": False, "uptime_s": uptime,
                "progress_duration_s": uptime,
                "error": "Database Connection Lost",
                "simulated_db_failure": True, **self.metrics(),
            }, 503)
        if SIMULATED_MODEL_FAILURE:
            return ({
                "phase": state["phase"], "marp_state": marp_state(),
                "stage": self.stage, "model_ready": False,
                "db_ready": state["db_ready"], "uptime_s": uptime,
                "progress_duration_s": uptime,
                "error": "Model Unloaded",
                "simulated_model_failure": True, **self.metrics(),
            }, 503)
        if state["model_ready"]:
            try:
                with engine.connect() as c:
                    c.execute(text("SELECT 1"))
                state["db_ready"] = True
            except Exception:
                state["db_ready"] = False
        ready = bool(state["model_ready"] and state["db_ready"])
        body = {
            "phase": state["phase"], "marp_state": marp_state(),
            "stage": self.stage, "model_ready": state["model_ready"],
            "db_ready": state["db_ready"], "uptime_s": uptime,
            "progress_duration_s": uptime, **self.metrics(),
        }
        return body, (200 if ready else 503)


ENGINE = MARPEngine()


def marp_state() -> str:
    ph = state.get("phase", "")
    if ph.startswith("db_failed") or ph.startswith("detector_failed"):
        return "FAILED"
    if ph.startswith("chaos"):
        if SIMULATED_DB_FAILURE:
            return "FAILED_DB"
        if SIMULATED_MODEL_FAILURE:
            return "FAILED_MODEL"
        if chaos_knobs.get("artificial_probe_failure"):
            return "FAILED_PROBE"
        if chaos_knobs.get("simulate_vram_exhaustion"):
            return "FAILED_VRAM"
        return "FAILED"
    mapped = PHASE_TO_MARP.get(ph)
    if mapped:
        return mapped
    # Prefer live engine stage when phase is custom.
    try:
        return ENGINE.stage
    except Exception:
        return ph.upper() if ph else "UNINITIALIZED"


def _chaos_delay() -> float:
    try:
        extra = float(chaos_knobs.get("vram_latency_s", 0.0) or 0.0)
    except Exception:
        extra = 0.0
    try:
        extra += float(chaos_knobs.get("simulated_latency_sec", 0.0) or 0.0)
    except Exception:
        pass
    return max(0.0, extra)


def load_heavy_model() -> None:
    """Background boot: DB -> weights (FaceDetector chain) -> READY.

    Order per spec: database migration/connect first (DB_CONNECTED),
    then model pre-warm; READY only after detector init finishes.
    """
    from sqlalchemy import text
    from ..core.database import Base, engine
    t0 = time.time()
    ENGINE.set_stage("UNINITIALIZED", "starting")

    # Optional stall: hold the loading window open for chaos drills.
    state["phase"] = "loading_model_weights"
    ENGINE.set_stage("LOADING_WEIGHTS", "loading_model_weights")
    delay = config.MODEL_LOAD_SECONDS + _chaos_delay()
    # Sleep in 1s slices so a mid-load reset/recover is observable.
    for _ in range(int(delay)):
        time.sleep(1)
        if state.get("phase") == "reloading" and False:  # placeholder guard
            pass
    time.sleep(max(0.0, delay - int(delay)))
    if chaos_knobs.get("model_stall"):
        ENGINE.set_stage("LOADING_WEIGHTS", "chaos: model stalled (in-situ)")
        return
    if chaos_knobs.get("simulate_vram_exhaustion"):
        ENGINE.mark_failed("VRAM exhausted during weight load (chaos)",
                           "detector_failed: VRAM exhausted (chaos)")
        return

    # Detector init (YOLO -> MediaPipe -> Haar) via FaceDetector hooks.
    state["phase"] = "warming_up_detector"
    try:
        from .face_detection import detector as _det
        ok = _det.load()
        if not ok:
            raise RuntimeError(f"no detector backend available (tried {_det.attempted})")
        global face_cascade
        face_cascade = _det.haar  # mirror for legacy imports (may be None)
    except Exception as e:
        ENGINE.mark_failed(str(e), f"detector_failed: {e}")
        return
    time.sleep(1)

    # DB migrate + connect.
    ENGINE.set_stage("DB_CONNECTED", "connecting_postgres")
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        state["db_ready"] = True
    except Exception as e:
        ENGINE.mark_failed(str(e), f"db_failed: {e}")
        return

    duration_ms = (time.time() - t0) * 1000.0
    vram_mb = _estimate_vram_mb()
    ENGINE.mark_ready(_det.backend if "_det" in dir() else "haar", duration_ms, vram_mb)


def _estimate_vram_mb() -> float:
    """Best-effort VRAM/RAM weight-buffer estimate (no torch dep required)."""
    try:
        import psutil  # type: ignore
        return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return 0.0


def start_background_load() -> None:
    threading.Thread(target=load_heavy_model, daemon=True).start()


def apply_chaos(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply ChaosConfig-style payload live (no restart)."""
    allowed = ("simulated_latency_sec", "frame_drop_rate",
               "simulate_vram_exhaustion", "artificial_probe_failure",
               "model_stall", "vram_latency_s")
    update = {}
    for k in allowed:
        if k in payload:
            update[k] = payload[k]
    try:
        if "simulated_latency_sec" in update:
            update["simulated_latency_sec"] = min(30.0, max(0.0, float(update["simulated_latency_sec"])))
        if "frame_drop_rate" in update:
            update["frame_drop_rate"] = min(1.0, max(0.0, float(update["frame_drop_rate"])))
        if "vram_latency_s" in update:
            update["vram_latency_s"] = max(0.0, float(update["vram_latency_s"]))
        for flag in ("simulate_vram_exhaustion", "artificial_probe_failure", "model_stall"):
            if flag in update:
                update[flag] = bool(update[flag])
    except Exception:
        pass
    chaos_knobs.update(update)
    if update.get("artificial_probe_failure"):
        state["phase"] = "chaos: probe refusal (in-situ)"
    elif update.get("simulate_vram_exhaustion"):
        state["phase"] = "chaos: vram exhausted (in-situ)"
    _log_telemetry_async("CHAOS_INJECTED")
    return dict(chaos_knobs)


def reset_chaos() -> Dict[str, Any]:
    global SIMULATED_DB_FAILURE, SIMULATED_MODEL_FAILURE
    SIMULATED_DB_FAILURE = False
    SIMULATED_MODEL_FAILURE = False
    chaos_knobs.update({k: v for k, v in config.CHAOS_DEFAULTS.items()})
    if state.get("phase", "").startswith("chaos") or state.get("phase", "").startswith("detector_failed"):
        state["phase"] = "reloading"
        start_background_load()
    _log_telemetry_async("CHAOS_RESET")
    return dict(chaos_knobs)


def inject(failure: str):
    """Legacy chaos interface shared by /api/chaos and MARP router."""
    global SIMULATED_DB_FAILURE, SIMULATED_MODEL_FAILURE
    from ..core.database import engine
    if failure == "db_drop":
        SIMULATED_DB_FAILURE = True
        try:
            engine.dispose()
        except Exception:
            pass
        state["db_ready"] = False
        state["phase"] = "chaos: postgres unreachable"
    elif failure == "model_unload":
        SIMULATED_MODEL_FAILURE = True
        state["model_ready"] = False
        state["phase"] = "chaos: model unloaded"
    elif failure == "recover":
        SIMULATED_DB_FAILURE = False
        SIMULATED_MODEL_FAILURE = False
        chaos_knobs.update({"model_stall": False, "vram_latency_s": 0.0,
                            "frame_drop_rate": 0.0,
                            "simulated_latency_sec": 0.0,
                            "simulate_vram_exhaustion": False,
                            "artificial_probe_failure": False})
        state["phase"] = "reloading"
        start_background_load()
    _log_telemetry_async("CHAOS_INJECTED" if failure != "recover" else "CHAOS_RESET")
    return {"phase": state["phase"]}


def _log_telemetry_async(event_type: str) -> None:
    """Fire-and-forget persistent telemetry insert (never blocks inference).

    Captures stage/phase + VRAM + load-duration + chaos snapshot at event
    time. Table is auto-created so fresh volumes and pre-existing volumes
    both work; all DB errors are swallowed — in-memory MARP stays live even
    if Postgres is down (chaos drills depend on this).
    """
    try:
        with ENGINE._state_lock:
            snapshot = {
                "phase": state.get("phase", ""),
                "vram": float(ENGINE.vram_allocated_mb or 0.0),
                "load_ms": float(ENGINE.model_load_duration_ms or 0.0),
                "chaos": dict(chaos_knobs),
            }
    except Exception:
        return

    def _insert() -> None:
        try:
            from ..core.database import Base, engine
            from ..models.telemetry import MarpTelemetry  # noqa: F401 (register table)
            try:
                Base.metadata.create_all(engine, tables=[
                    MarpTelemetry.__table__])  # type: ignore[attr-defined]
            except Exception:
                try:
                    Base.metadata.create_all(engine)
                except Exception:
                    pass
            from ..core.database import SessionLocal
            s = SessionLocal()
            try:
                s.add(MarpTelemetry(
                    event_type=event_type,
                    phase=snapshot["phase"],
                    vram_allocated_mb=snapshot["vram"],
                    load_duration_ms=snapshot["load_ms"],
                    active_chaos_params=snapshot["chaos"],
                ))
                s.commit()
            except Exception:
                try:
                    s.rollback()
                except Exception:
                    pass
            finally:
                try:
                    s.close()
                except Exception:
                    pass
        except Exception:
            pass

    try:
        threading.Thread(target=_insert, daemon=True).start()
    except Exception:
        pass


def session_lock():
    return _session_lock
