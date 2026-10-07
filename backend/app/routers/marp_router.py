"""MARP probes + in-situ chaos (/api/v1/marp/*). Mirrors legacy /healthz contract."""
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from ..core.database import engine
from ..schemas.marp import ChaosConfig, ChaosIn, ChaosTune
from ..services import marp_engine as marp

router = APIRouter(prefix="/api/v1/marp", tags=["marp"])


def _readiness_body():
    # Simulated latency chaos: stall the probe itself (edge failover drill).
    try:
        time.sleep(max(0.0, float(marp.chaos_knobs.get("simulated_latency_sec", 0.0) or 0.0)))
    except Exception:
        pass
    return marp.ENGINE.readiness()


@router.get("/healthz/liveness")
def liveness():
    return {"status": "alive", "marp_state": marp.marp_state(),
            "stage": marp.ENGINE.stage}


@router.get("/healthz/readiness")
def readiness():
    body, code = _readiness_body()
    return JSONResponse(body, status_code=code)


@router.get("/status")
def status():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"phase": marp.state["phase"], "marp_state": marp.marp_state(),
            "model_ready": marp.state["model_ready"], "db_connected": db_ok,
            "uptime_s": round(time.time() - marp.START_TIME, 1),
            "active_session": dict(marp.active_session),
            "chaos": dict(marp.chaos_knobs),
            "metrics": marp.ENGINE.metrics(),
            "simulated_db_failure": marp.SIMULATED_DB_FAILURE,
            "simulated_model_failure": marp.SIMULATED_MODEL_FAILURE}


# ---- new spec surface ----
@router.post("/chaos/inject")
def chaos_inject(cfg: ChaosConfig):
    chaos = marp.apply_chaos(cfg.model_dump())
    return {"ok": True, "chaos": chaos, "marp_state": marp.marp_state(),
            "stage": marp.ENGINE.stage,
            "message": "Chaos parameters applied live (no restart)"}


@router.get("/chaos/status")
def chaos_status():
    return {"chaos": marp.ENGINE.chaos_snapshot(),
            "marp_state": marp.marp_state(), "stage": marp.ENGINE.stage,
            "metrics": marp.ENGINE.metrics(),
            "simulated_db_failure": marp.SIMULATED_DB_FAILURE,
            "simulated_model_failure": marp.SIMULATED_MODEL_FAILURE}


@router.post("/chaos/reset")
def chaos_reset():
    chaos = marp.reset_chaos()
    return {"ok": True, "chaos": chaos, "marp_state": marp.marp_state(),
            "stage": marp.ENGINE.stage,
            "message": "Chaos cleared; standard operations restored"}


# ---- legacy compat (kept for old UI + fault_injection tests) ----
@router.post("/chaos")
def chaos(c: ChaosIn):
    return marp.inject(c.failure)


@router.post("/chaos/db-drop")
def db_drop():
    marp.SIMULATED_DB_FAILURE = True
    try:
        engine.dispose()
    except Exception:
        pass
    marp.state["db_ready"] = False
    marp.state["phase"] = "chaos: postgres unreachable (simulated)"
    return {"ok": True, "failure": "db_drop", "marp_state": marp.marp_state(),
            "phase": marp.state["phase"],
            "message": "Simulated DB failure injected; readiness now 503"}


@router.post("/chaos/unload-model")
def unload_model():
    marp.SIMULATED_MODEL_FAILURE = True
    marp.state["model_ready"] = False
    marp.state["phase"] = "chaos: model unloaded (simulated)"
    return {"ok": True, "failure": "model_unload", "marp_state": marp.marp_state(),
            "phase": marp.state["phase"],
            "message": "Simulated model failure injected; readiness now 503"}


@router.post("/chaos/recover")
def recover():
    marp.SIMULATED_DB_FAILURE = False
    marp.SIMULATED_MODEL_FAILURE = False
    marp.state["phase"] = "reloading"
    marp.start_background_load()
    return {"ok": True, "marp_state": marp.marp_state(), "phase": marp.state["phase"],
            "message": "Recovering; readiness 200 once reload completes"}


@router.post("/chaos/tune")
def tune(t: ChaosTune):
    marp.chaos_knobs.update({"vram_latency_s": max(0.0, t.vram_latency_s),
                             "frame_drop_rate": min(1.0, max(0.0, t.frame_drop_rate)),
                             "model_stall": bool(t.model_stall)})
    if t.model_stall:
        marp.state["phase"] = "chaos: model stalled (in-situ)"
    return {"ok": True, "chaos": dict(marp.chaos_knobs),
            "marp_state": marp.marp_state()}
