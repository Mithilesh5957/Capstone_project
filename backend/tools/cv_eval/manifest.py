"""FACEATTEND R8 evaluation harness — manifest loading and validation (stdlib).

Manifest format (JSON):
{
  "dataset": {"name": ..., "origin": ..., "license_or_consent": ...,
              "collected": "YYYY-MM-DD"},
  "images": [
    {"image_id": "s01_session2_004",
     "path": "data/s01/session2/004.jpg",   # local path, repo-relative or abs
     "split": "enrollment" | "probe_dev" | "probe_holdout" | "detection",
     "session_id": "s01_session2",            # optional, for session splits
     "faces": [                               # detection labels (optional)
       {"identity_id": "s01", "bbox": [x, y, w, h],
        "difficult": false}]}
  ]
}

No images or biometric templates are embedded — only IDs, local paths, labels.
run_eval.py refuses manifests with errors; every refusal is counted, never
silently skipped.
"""
from __future__ import annotations

import json
import os

from .metrics import validate_box

VALID_SPLITS = ("enrollment", "probe_dev", "probe_holdout", "detection")


def load_manifest(path):
    """Parse a manifest file. Returns (manifest_dict, errors)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as e:
        return None, [f"unreadable manifest {path!r}: {e}"]
    if not isinstance(manifest, dict):
        return None, ["manifest root must be a JSON object"]
    return manifest, []


def validate_manifest(manifest):
    """Return a list of error strings (empty = valid)."""
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest root must be a JSON object"]
    images = manifest.get("images")
    if not isinstance(images, list) or not images:
        return ["manifest.images must be a non-empty list"]
    seen = set()
    for idx, img in enumerate(images):
        where = f"images[{idx}]"
        if not isinstance(img, dict):
            errors.append(f"{where}: must be an object")
            continue
        iid = img.get("image_id")
        if not iid or not isinstance(iid, str):
            errors.append(f"{where}: missing/invalid image_id")
        elif iid in seen:
            errors.append(f"{where}: duplicate image_id {iid!r}")
        else:
            seen.add(iid)
        if not img.get("path") or not isinstance(img.get("path"), str):
            errors.append(f"{where} ({iid}): missing/invalid path")
        if img.get("split") not in VALID_SPLITS:
            errors.append(f"{where} ({iid}): split must be one of "
                          f"{list(VALID_SPLITS)}")
        faces = img.get("faces", [])
        if not isinstance(faces, list):
            errors.append(f"{where} ({iid}): faces must be a list")
            continue
        for fidx, face in enumerate(faces):
            if not isinstance(face, dict):
                errors.append(f"{where} ({iid}): faces[{fidx}] not an object")
                continue
            if not face.get("identity_id") or not isinstance(
                    face.get("identity_id"), str):
                errors.append(f"{where} ({iid}): faces[{fidx}] missing "
                              f"identity_id")
            if not validate_box(face.get("bbox")):
                errors.append(f"{where} ({iid}): faces[{fidx}] invalid bbox "
                              f"{face.get('bbox')!r}")
    return errors


def resolve_path(entry_path, base_dir=None):
    """Resolve a manifest path against base_dir (default: repo backend dir)."""
    if os.path.isabs(entry_path):
        return entry_path
    base = base_dir or os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    return os.path.normpath(os.path.join(base, entry_path))
