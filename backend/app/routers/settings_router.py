"""Detection parameter tuning (/api/v1/settings)."""
from fastapi import APIRouter, Depends
from ..core import config
from ..core.security import get_current_user, require_admin

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/detection")
def get_detection(_user: dict = Depends(get_current_user)):
    return {"frame": {"w": config.FRAME_W, "h": config.FRAME_H},
            "scale_factor": config.DET_SCALE_FACTOR,
            "min_neighbors": config.DET_MIN_NEIGHBORS,
            "min_size": list(config.DET_MIN_SIZE),
            "aspect_range": [config.DET_ASPECT_LO, config.DET_ASPECT_HI],
            "reid_threshold": config.REID_THRESHOLD}


@router.post("/detection")
def set_detection(body: dict, _admin: dict = Depends(require_admin)):
    if "reid_threshold" in body:
        v = float(body["reid_threshold"])
        config.REID_THRESHOLD = min(2.0, max(0.1, v))
    if "min_neighbors" in body:
        config.DET_MIN_NEIGHBORS = max(1, min(12, int(body["min_neighbors"])))
    if "min_size" in body:
        s = int(body["min_size"])
        config.DET_MIN_SIZE = (s, s)
    return {"ok": True, "reid_threshold": config.REID_THRESHOLD,
            "min_neighbors": config.DET_MIN_NEIGHBORS,
            "min_size": list(config.DET_MIN_SIZE)}
