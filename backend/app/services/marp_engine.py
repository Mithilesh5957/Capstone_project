"""MARP state machine + in-situ chaos injector (singleton MARPEngine).

Lifecycle contract (R2):
  UNINITIALIZED -> LOADING_WEIGHTS -> READY
                          |            ^   (explicit recover/reset only)
                          v            |
               FAILED_{db,model,timeout}   SHUTDOWN (terminal, process exiting)

- Single-flight: at most one loader thread per engine; concurrent callers
  attach to the active generation. Stale generations never commit results.
- No fixed startup sleep: DB is checked first via the real engine, then the
  detector loads with a bounded budget (MODEL_LOAD_SECONDS = attempt timeout,
  not a mandatory wait). Fast loads go READY immediately.
- Failures are explicit and stable (no indefinite loading): DB, detector
  exception, or budget expiry each produce a distinct FAILED kind with a
  distinct phase prefix. No automatic retries (operator recovers explicitly).
- DB loss after READY is reported live (failure_kind "db") and recovers
  automatically when the database returns — no restart needed.
- Legacy phase strings ('starting','loading_model_weights',...) are kept in the
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

# ---- R2 single-flight loader coordination ----
_load_lock = threading.Lock()
_load_generation: int = 0
_load_thread: "threading.Thread | None" = None
_shutdown_event = threading.Event()


def _current_generation() -> int:
    with _load_lock:
        return _load_generation


def _loader_alive() -> bool:
    t = _load_thread
    return t is not None and t.is_alive()


def _is_stale(generation: int) -> bool:
    return generation != _current_generation() or _shutdown_event.is_set()


def session_snapshot() -> Dict[str, Any]:
    """Lock-protected copy of the active session for API responses."""
    with _session_lock:
        return dict(active_session)

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
        # R2: distinct, stable failure classification + owning attempt.
        # failure_kind in {None, "db", "model", "timeout"}.
        self.failure_kind: str | None = None
        self.attempt: int = 0

    # -- state helpers -------------------------------------------------
    def set_stage(self, stage: str, phase: str | None = None) -> None:
        with self._state_lock:
            self.stage = stage
            if phase is not None:
                state["phase"] = phase
        _log_telemetry_async("STATE_CHANGE")

    def begin_attempt(self, generation: int) -> None:
        """Open a load attempt: LOADING stage, cleared failure classification.

        Preserves a caller-preset "reloading" phase (explicit recovery);
        otherwise reports "starting".
        """
        with self._state_lock:
            self.stage = "LOADING_WEIGHTS"
            self.attempt = generation
            self.failure_kind = None
            self.last_error = None
            state["model_ready"] = False
            if state.get("phase") != "reloading":
                state["phase"] = "starting"
        _log_telemetry_async("STATE_CHANGE")

    def mark_ready(self, backend: str, duration_ms: float, vram_mb: float) -> None:
        with self._state_lock:
            self.stage = "READY"
            self.detector_backend = backend
            self.model_load_duration_ms = duration_ms
            self.vram_allocated_mb = vram_mb
            self.last_error = None
            self.failure_kind = None
            state["model_ready"] = True
            state["phase"] = "ready"
        _log_telemetry_async("STATE_CHANGE")

    def mark_failed(self, error: str, phase: str, kind: str | None = None) -> None:
        with self._state_lock:
            self.stage = "FAILED"
            self.last_error = error
            self.failure_kind = kind
            state["model_ready"] = False
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
        """Central readiness evaluation. Shutdown, then chaos overrides."""
        from sqlalchemy import text
        from ..core.database import engine
        self.record_probe()
        uptime = round(time.time() - START_TIME, 1)

        # Shutdown in progress: process alive (liveness stays 200) but no
        # traffic should be routed here.
        if _shutdown_event.is_set():
            return ({
                "phase": state.get("phase", ""), "marp_state": marp_state(),
                "stage": self.stage, "model_ready": False,
                "db_ready": state.get("db_ready", False), "uptime_s": uptime,
                "progress_duration_s": uptime,
                "error": "Application shutting down",
                "failure_kind": "shutdown",
                "attempt": self.attempt,
                **self.metrics(),
            }, 503)

        # Artificial probe refusal (chaos) wins over everything else.
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
                with self._state_lock:
                    state["db_ready"] = True
            except Exception:
                with self._state_lock:
                    state["db_ready"] = False
        ready = bool(state["model_ready"] and state["db_ready"])
        # Structured unavailability reason (additive; existing keys unchanged):
        # explicit failure classification wins, then live DB flap, else loading.
        if ready:
            failure_kind = None
        elif self.failure_kind:
            failure_kind = self.failure_kind
        elif state["model_ready"] and not state["db_ready"]:
            failure_kind = "db"
        else:
            failure_kind = "loading"
        body = {
            "phase": state["phase"], "marp_state": marp_state(),
            "stage": self.stage, "model_ready": state["model_ready"],
            "db_ready": state["db_ready"], "uptime_s": uptime,
            "progress_duration_s": uptime, "failure_kind": failure_kind,
            "attempt": self.attempt, **self.metrics(),
        }
        return body, (200 if ready else 503)


ENGINE = MARPEngine()


def marp_state() -> str:
    ph = state.get("phase", "")
    # Distinct terminal states (R2): DB vs model vs timeout stay separable.
    # Phase prefixes are stable API; only this derived label gained variants.
    if ph.startswith("db_failed"):
        return "FAILED_DB"
    if ph.startswith("timeout"):
        return "FAILED_TIMEOUT"
    if ph.startswith("detector_failed"):
        return "FAILED_MODEL"
    if ph == "shutdown":
        return "SHUTDOWN"
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


def _load_budget_s() -> float:
    """Bound for one load attempt. MODEL_LOAD_SECONDS is a timeout upper
    bound (plus intentional chaos delays), never a mandatory wait."""
    try:
        base = float(config.MODEL_LOAD_SECONDS)
    except Exception:
        base = 15.0
    return max(1.0, base + _chaos_delay())


def _check_database() -> None:
    """Real DB readiness: schema migrate + live SELECT 1. Raises on failure."""
    from sqlalchemy import text
    from ..core.database import engine
    _ensure_schema()
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    with ENGINE._state_lock:
        state["db_ready"] = True


def _load_detector(budget_s: float, generation: int):
    """Run the FaceDetector chain with a bounded budget.

    Returns (backend_name | None, error | None, timed_out: bool). The load
    itself runs in an inner daemon thread so an overrun cannot block the
    worker: on timeout the worker records FAILED_TIMEOUT and returns, and a
    late-finishing inner thread commits nothing (see generation checks).
    """
    from .face_detection import detector as _det
    result: Dict[str, Any] = {}
    done = threading.Event()

    def _run() -> None:
        try:
            ok = _det.load()
            if ok:
                result["backend"] = _det.backend
                global face_cascade
                face_cascade = _det.haar  # mirror for legacy imports
            else:
                result["error"] = (
                    f"no detector backend available (tried {_det.attempted})")
        except Exception as e:  # noqa: BLE001 - surfaced as FAILED_MODEL
            result["error"] = str(e)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    deadline = time.time() + max(0.5, budget_s)
    while time.time() < deadline:
        if _is_stale(generation):
            return None, "superseded by a newer load attempt", False
        if done.wait(0.1):
            break
    else:
        return None, None, True
    if _is_stale(generation):
        return None, "superseded by a newer load attempt", False
    if "backend" in result:
        return result["backend"], None, False
    return None, result.get("error", "detector load failed"), False


def _commit_if_current(generation: int, action: str, *args: Any) -> bool:
    """Commit mark_ready/mark_failed only for the active generation."""
    if _is_stale(generation):
        return False
    if action == "ready":
        ENGINE.mark_ready(*args)  # type: ignore[arg-type]
    else:
        ENGINE.mark_failed(*args)  # type: ignore[arg-type]
    return not _is_stale(generation)


def _load_worker(generation: int, reason: str) -> None:
    """Single coordinated load attempt: DB first, then bounded detector load.

    Stale generations (superseded recovery) and shutdown abort without
    committing any result.
    """
    t0 = time.time()
    if _is_stale(generation):
        return  # superseded before it even started; commit nothing.
    ENGINE.begin_attempt(generation)
    with ENGINE._state_lock:
        state["phase"] = "reloading" if reason == "recovery" else "loading_model_weights"

    # Optional stall drill: hold the window open, but bounded by the attempt
    # budget and immediately releasable (stall cleared / recover / shutdown).
    if chaos_knobs.get("model_stall"):
        with ENGINE._state_lock:
            state["phase"] = "chaos: model stalled (in-situ)"
        deadline = t0 + _load_budget_s()
        while time.time() < deadline:
            if _is_stale(generation):
                return
            if not chaos_knobs.get("model_stall"):
                break
            time.sleep(0.1)
        if chaos_knobs.get("model_stall") and not _is_stale(generation):
            _commit_if_current(
                generation, "failed",
                "model stall exceeded load budget (chaos)",
                "chaos: model stalled (in-situ)",
                "timeout",
            )
            return
    if chaos_knobs.get("simulate_vram_exhaustion"):
        _commit_if_current(
            generation, "failed",
            "VRAM exhausted during weight load (chaos)",
            "detector_failed: VRAM exhausted (chaos)",
            "model",
        )
        return
    if _is_stale(generation):
        return

    # DB readiness via the real initialization mechanism.
    with ENGINE._state_lock:
        state["phase"] = "connecting_postgres"
    try:
        _check_database()
    except Exception as e:  # noqa: BLE001 - classified as FAILED_DB below
        _commit_if_current(generation, "failed", str(e), f"db_failed: {e}", "db")
        return
    if _is_stale(generation):
        return

    # Bounded detector load (no fixed sleep anywhere on this path).
    with ENGINE._state_lock:
        state["phase"] = "warming_up_detector"
    elapsed = time.time() - t0
    backend, error, timed_out = _load_detector(_load_budget_s() - elapsed, generation)
    if timed_out:
        _commit_if_current(
            generation, "failed",
            f"detector load exceeded {_load_budget_s():.0f}s budget",
            f"timeout: detector load exceeded budget",
            "timeout",
        )
        return
    if error is not None or backend is None:
        _commit_if_current(
            generation, "failed", str(error), f"detector_failed: {error}", "model")
        return

    duration_ms = (time.time() - t0) * 1000.0
    _commit_if_current(generation, "ready", backend, duration_ms, _estimate_vram_mb())


def load_heavy_model(generation: int | None = None) -> None:
    """Backward-compatible entry: run one coordinated attempt inline.

    Prefer start_background_load() (single-flight). A direct call claims a
    fresh generation so it cannot be mistaken for an older attempt.
    """
    global _load_generation
    if generation is None:
        with _load_lock:
            _load_generation += 1
            generation = _load_generation
    _load_worker(generation, "boot")


def _estimate_vram_mb() -> float:
    """Best-effort VRAM/RAM weight-buffer estimate (no torch dep required)."""
    try:
        import psutil  # type: ignore
        return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return 0.0


def start_background_load(reason: str = "boot") -> int:
    """Single-flight loader start. At most one loader thread is ever active:
    concurrent callers attach to the running attempt and observe the same
    generation. Returns the active generation. Refuses new work after
    shutdown. Retrying a FAILED attempt spawns exactly one new worker
    (the previous worker has exited); retrying while LOADING is a no-op.
    """
    global _load_generation, _load_thread
    with _load_lock:
        if _shutdown_event.is_set():
            return _load_generation
        t = _load_thread
        if t is not None and t.is_alive():
            return _load_generation
        _load_generation += 1
        generation = _load_generation
        _load_thread = threading.Thread(
            target=_load_worker, args=(generation, reason), daemon=True)
        _load_thread.start()
        return generation


def note_shutdown(timeout_s: float = 5.0) -> None:
    """Application shutdown: stop accepting load work, invalidate in-flight
    attempts, and best-effort join the loader so no uncontrolled new recovery
    work is left behind. Daemon threads still die with the process."""
    _shutdown_event.set()
    with _load_lock:
        global _load_generation
        _load_generation += 1
        t = _load_thread
    with ENGINE._state_lock:
        ENGINE.stage = "SHUTDOWN"
        state["phase"] = "shutdown"
    if t is not None and t.is_alive():
        t.join(timeout=max(0.0, timeout_s))


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
    with ENGINE._state_lock:
        chaos_knobs.update(update)
        if update.get("artificial_probe_failure"):
            state["phase"] = "chaos: probe refusal (in-situ)"
        elif update.get("simulate_vram_exhaustion"):
            state["phase"] = "chaos: vram exhausted (in-situ)"
        snapshot = dict(chaos_knobs)
    _log_telemetry_async("CHAOS_INJECTED")
    return snapshot


def _needs_recovery_locked() -> bool:
    """True when an explicit recovery attempt is meaningful: chaos-induced
    states and stable FAILED states (operator asked to try again)."""
    phase = state.get("phase", "")
    return (
        phase.startswith("chaos")
        or phase.startswith("detector_failed")
        or phase.startswith("db_failed")
        or phase.startswith("timeout")
    )


def reset_chaos() -> Dict[str, Any]:
    global SIMULATED_DB_FAILURE, SIMULATED_MODEL_FAILURE
    with ENGINE._state_lock:
        SIMULATED_DB_FAILURE = False
        SIMULATED_MODEL_FAILURE = False
        chaos_knobs.update({k: v for k, v in config.CHAOS_DEFAULTS.items()})
        wants_reload = _needs_recovery_locked()
        if wants_reload:
            state["phase"] = "reloading"
    if wants_reload:
        start_background_load("recovery")
    _log_telemetry_async("CHAOS_RESET")
    return dict(chaos_knobs)


def inject(failure: str):
    """Legacy chaos interface shared by /api/chaos and MARP router."""
    global SIMULATED_DB_FAILURE, SIMULATED_MODEL_FAILURE
    from ..core.database import engine
    wants_reload = False
    with ENGINE._state_lock:
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
            wants_reload = True
    if wants_reload:
        start_background_load("recovery")
    _log_telemetry_async("CHAOS_INJECTED" if failure != "recover" else "CHAOS_RESET")
    return {"phase": state["phase"]}


_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema() -> None:
    """Single schema owner for MARP lifecycle DDL. Serialized so concurrent
    loader/telemetry threads cannot race CREATE TABLE; idempotent afterwards.
    Real (non-race) failures propagate to the caller for classification —
    only the duplicate-table race is absorbed here."""
    global _schema_ready
    from sqlalchemy.exc import OperationalError, ProgrammingError
    from ..core.database import Base, engine
    from ..models.telemetry import MarpTelemetry  # noqa: F401 (register table)
    if _schema_ready:
        try:
            Base.metadata.create_all(engine, checkfirst=True)
            return
        except (OperationalError, ProgrammingError):
            pass
    with _schema_lock:
        try:
            Base.metadata.create_all(engine, checkfirst=True)
            _schema_ready = True
        except (OperationalError, ProgrammingError) as e:
            if "already exists" not in str(getattr(e, "orig", e)):
                raise


def _log_telemetry_async(event_type: str) -> None:
    """Fire-and-forget persistent telemetry insert (never blocks inference).

    Captures stage/phase + VRAM + load-duration + chaos snapshot at event
    time. Schema is owned by _ensure_schema; DB outages are still swallowed
    (SQLAlchemyError only) so in-memory MARP stays live during chaos drills.
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
        # Narrowed handling: DB outages are swallowed so MARP stays live;
        # anything else propagates loudly out of the daemon thread.
        from sqlalchemy.exc import SQLAlchemyError
        from ..core.database import SessionLocal
        from ..models.telemetry import MarpTelemetry
        try:
            _ensure_schema()
        except SQLAlchemyError:
            return  # DB unavailable; event dropped, MARP stays live.
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
        except SQLAlchemyError:
            try:
                s.rollback()
            except Exception:
                pass
        finally:
            try:
                s.close()
            except Exception:
                pass

    try:
        threading.Thread(target=_insert, daemon=True).start()
    except Exception:
        pass


def session_lock():
    return _session_lock
