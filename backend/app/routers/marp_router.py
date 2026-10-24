"""MARP probes + in-situ chaos (/api/v1/marp/*). Mirrors legacy /healthz contract."""
import csv
import io
import time
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from ..core.database import SessionLocal, engine
from ..core.security import require_admin
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


# ---- new spec surface (operator-guarded) ----
@router.post("/chaos/inject")
def chaos_inject(cfg: ChaosConfig, _admin: dict = Depends(require_admin)):
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
def chaos_reset(_admin: dict = Depends(require_admin)):
    chaos = marp.reset_chaos()
    return {"ok": True, "chaos": chaos, "marp_state": marp.marp_state(),
            "stage": marp.ENGINE.stage,
            "message": "Chaos cleared; standard operations restored"}


# ---- legacy compat (kept for old UI + fault_injection tests) ----
# NOTE: legacy chaos endpoints remain unauthenticated for DevOps harness
# compatibility; new /chaos/inject|reset|tune paths above require JWT admin.
@router.post("/chaos")
def chaos(c: ChaosIn):
    return marp.inject(c.failure)


@router.post("/chaos/db-drop")
def db_drop(_admin: dict = Depends(require_admin)):
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
def unload_model(_admin: dict = Depends(require_admin)):
    marp.SIMULATED_MODEL_FAILURE = True
    marp.state["model_ready"] = False
    marp.state["phase"] = "chaos: model unloaded (simulated)"
    return {"ok": True, "failure": "model_unload", "marp_state": marp.marp_state(),
            "phase": marp.state["phase"],
            "message": "Simulated model failure injected; readiness now 503"}


@router.post("/chaos/recover")
def recover(_admin: dict = Depends(require_admin)):
    marp.SIMULATED_DB_FAILURE = False
    marp.SIMULATED_MODEL_FAILURE = False
    marp.state["phase"] = "reloading"
    marp.start_background_load()
    return {"ok": True, "marp_state": marp.marp_state(), "phase": marp.state["phase"],
            "message": "Recovering; readiness 200 once reload completes"}


@router.post("/chaos/tune")
def tune(t: ChaosTune, _admin: dict = Depends(require_admin)):
    marp.chaos_knobs.update({"vram_latency_s": max(0.0, t.vram_latency_s),
                             "frame_drop_rate": min(1.0, max(0.0, t.frame_drop_rate)),
                             "model_stall": bool(t.model_stall)})
    if t.model_stall:
        marp.state["phase"] = "chaos: model stalled (in-situ)"
    return {"ok": True, "chaos": dict(marp.chaos_knobs),
            "marp_state": marp.marp_state()}


# ---- research telemetry export (Phase 5, operator-guarded) ----
CHAOS_EXPORT_KEYS = (
    "simulated_latency_sec",
    "frame_drop_rate",
    "simulate_vram_exhaustion",
    "artificial_probe_failure",
    "model_stall",
    "vram_latency_s",
)


@router.get("/telemetry/export")
def telemetry_export(
    _admin: dict = Depends(require_admin),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    """Download MARP research data as CSV (`marp_research_data.csv`).

    Flattens the JSONB `active_chaos_params` into one `chaos_<key>` column
    per knob so researchers can plot directly in Excel/Python without
    JSON parsing.
    """
    from ..models.telemetry import MarpTelemetry  # noqa: F401 (register table)

    s = SessionLocal()
    try:
        rows = (
            s.query(MarpTelemetry)
            .order_by(MarpTelemetry.id.asc())
            .limit(limit)
            .all()
        )
        buf = io.StringIO()
        fieldnames = [
            "id", "timestamp", "event_type", "phase",
            "vram_allocated_mb", "load_duration_ms",
            *[f"chaos_{k}" for k in CHAOS_EXPORT_KEYS],
        ]
        w = csv.DictWriter(buf, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            chaos = r.active_chaos_params or {}
            if not isinstance(chaos, dict):
                chaos = {}
            out = {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "event_type": r.event_type or "",
                "phase": r.phase or "",
                "vram_allocated_mb": r.vram_allocated_mb,
                "load_duration_ms": r.load_duration_ms,
            }
            for k in CHAOS_EXPORT_KEYS:
                v = chaos.get(k, "")
                out[f"chaos_{k}"] = v if not isinstance(v, (dict, list)) else str(v)
            w.writerow(out)
        data = buf.getvalue()
    finally:
        s.close()
    return PlainTextResponse(
        data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marp_research_data.csv"},
    )
