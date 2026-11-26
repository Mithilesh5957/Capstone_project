"""FACEATTEND R8 evaluation harness — pipeline runner (data-gated, unexecuted).

Executes the REAL product code path (face_detection / face_recognition) over a
validated manifest. App modules are imported lazily inside functions so that
importing this module never requires cv2/numpy/fastapi.

Status: IMPLEMENTED BUT UNEXECUTED — no approved labelled dataset exists
locally (see R8 report §dataset). Do not present synthetic runs of this module
as accuracy evidence.
"""
from __future__ import annotations

import os
import time

from .manifest import load_manifest, resolve_path, validate_manifest
from .metrics import (auc, eer_threshold, far_frr, latency_stats,
                      match_detections, prf, top1_accuracy)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def run_detection(manifest, iou_thresh=0.5, base_dir=None):
    """Run fd.detect_faces_jpeg over split=='detection' images with labels.

    Returns a JSON-serializable result dict (counts, prf, per-image outcomes
    with backend + latency; sample IDs only, never images).
    """
    from app.services import face_detection as fd  # noqa: PLC0415 (lazy: cv2)

    per_image, lat, backend_of = [], [], {}
    for img in manifest["images"]:
        if img.get("split") != "detection":
            continue
        path = resolve_path(img["path"], base_dir)
        t0 = time.perf_counter()
        try:
            dets = fd.detect_faces_jpeg(_read_bytes(path))
        except OSError:
            per_image.append({"image_id": img["image_id"], "error": "missing"})
            continue
        dt = time.perf_counter() - t0
        lat.append(dt)
        preds = [d["bbox"] for d in dets]
        labels = [f["bbox"] for f in img.get("faces", [])]
        tp, fp, fn, matches = match_detections(preds, labels, iou_thresh)
        per_image.append({"image_id": img["image_id"], "tp": tp, "fp": fp,
                          "fn": fn, "latency_s": dt,
                          "backend": fd.detector.backend,
                          "n_pred": len(preds), "n_label": len(labels)})
        backend_of[img["image_id"]] = fd.detector.backend
    agg_tp = sum(r.get("tp", 0) for r in per_image)
    agg_fp = sum(r.get("fp", 0) for r in per_image)
    agg_fn = sum(r.get("fn", 0) for r in per_image)
    prec, rec, f1 = prf(agg_tp, agg_fp, agg_fn)
    n, med, p95 = latency_stats(lat)
    return {"iou_thresh": iou_thresh, "tp": agg_tp, "fp": agg_fp, "fn": agg_fn,
            "precision": prec, "recall": rec, "f1": f1,
            "n_images": len(per_image),
            "n_timed": n, "latency_median_s": med, "latency_p95_s": p95,
            "images": per_image}


def run_recognition(manifest, threshold=0.85, thresholds_grid=None,
                    base_dir=None):
    """Gallery/probe recognition over enrollment + probe_* splits.

    Gallery follows the product enrollment rule (mean of ≤8 vectors per
    identity, via students_router logic replicated on file embeddings —
    see note). Returns genuine/impostor distances, FAR/FRR at `threshold`,
    ROC/AUC + EER over `thresholds_grid`, and closed-set top-1 results.

    Note: uses fr.embedding_from_bytes per image then the mean rule from
    enroll_impl; no database is touched.
    """
    from app.services import face_recognition as fr  # noqa: PLC0415

    gallery_vecs, probes = {}, []
    for img in manifest["images"]:
        split = img.get("split")
        if split not in ("enrollment", "probe_dev", "probe_holdout"):
            continue
        path = resolve_path(img["path"], base_dir)
        try:
            vec = fr.embedding_from_bytes(_read_bytes(path))
        except OSError:
            probes.append({"image_id": img["image_id"], "error": "missing"})
            continue
        if vec is None:
            probes.append({"image_id": img["image_id"], "error": "no_template"})
            continue
        ident = (img.get("faces") or [{}])[0].get("identity_id")
        if split == "enrollment" and ident:
            gallery_vecs.setdefault(ident, []).append(vec)
        elif ident:
            probes.append({"image_id": img["image_id"], "identity": ident,
                           "split": split, "vec": vec})
    gallery = {}
    for ident, vecs in gallery_vecs.items():
        use = vecs[:8]
        mean = [sum(c) / len(use) for c in zip(*use)]
        n = sum(v * v for v in mean) ** 0.5
        gallery[ident] = [v / n for v in mean] if n > 0 else mean
    genuine, impostor, top1_rows = [], [], []
    for p in probes:
        if "vec" not in p:
            continue
        scored = sorted(((fr.euclidean(p["vec"], g), ident)
                         for ident, g in gallery.items()),
                        key=lambda t: t[0])
        if not scored:
            continue
        best_d, best_id = scored[0]
        top1_rows.append((best_id, p["identity"]))
        for d, ident in scored:
            (genuine if ident == p["identity"] else impostor).append(d)
    op = far_frr(genuine, impostor, threshold)
    grid = thresholds_grid or [i / 100.0 for i in range(0, 201, 5)]
    acc, n_ok, n_tot, mism = top1_accuracy(top1_rows)
    e_thr, e_far, e_frr = eer_threshold(genuine, impostor, grid)
    return {"threshold": threshold, "operating_point": op,
            "n_gallery_identities": len(gallery),
            "n_genuine_pairs": len(genuine),
            "n_impostor_pairs": len(impostor),
            "auc": auc(genuine, impostor, grid),
            "eer_threshold": e_thr, "eer_far": e_far, "eer_frr": e_frr,
            "eer_estimate": ((e_far + e_frr) / 2.0
                             if e_far is not None and e_frr is not None
                             else None),
            "top1_accuracy": acc, "top1_correct": n_ok, "top1_total": n_tot,
            "mismatches": [{"predicted": a, "actual": b} for a, b in mism],
            "genuine_distances": genuine, "impostor_distances": impostor}


def main(manifest_path, out_path, threshold=0.85, iou_thresh=0.5):
    """CLI entry: validate manifest, run both arms, write JSON artifact."""
    import json  # noqa: PLC0415 (stdlib, local import keeps module light)

    manifest, load_errors = load_manifest(manifest_path)
    if load_errors:
        raise SystemExit(f"manifest refused: {load_errors}")
    errors = validate_manifest(manifest)
    if errors:
        raise SystemExit(f"manifest invalid: {errors}")
    result = {
        "manifest": os.path.abspath(manifest_path),
        "threshold": threshold,
        "iou_thresh": iou_thresh,
        "detection": run_detection(manifest, iou_thresh,
                                   os.path.dirname(manifest_path)),
        "recognition": run_recognition(manifest, threshold,
                                       base_dir=os.path.dirname(
                                           manifest_path)),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return out_path


if __name__ == "__main__":
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="FACEATTEND R8 CV evaluation")
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()
    print(main(args.manifest, args.out, args.threshold, args.iou))
