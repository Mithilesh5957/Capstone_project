"""FACEATTEND R8 evaluation harness — metric implementations (pure stdlib).

Deterministic scoring helpers used by run_eval.py and covered by
backend/tools/cv_eval/tests/test_cv_metrics.py.

Conventions (match docs/CV_EVALUATION_PROTOCOL.md):
- Boxes are [x, y, w, h] in pixels.
- Recognition scores are Euclidean DISTANCES: lower = more similar; a probe is
  accepted iff score <= threshold.
- Every rate function returns (rate_or_None, numerator, denominator): None with
  a zero denominator is reported as unavailable, never as 0%.
"""
from __future__ import annotations

import math


def _valid_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v)


def validate_box(box, w_frame=None, h_frame=None) -> bool:
    """True iff box is [x, y, w, h] with finite numbers, w > 0, h > 0."""
    try:
        x, y, w, h = box
    except (TypeError, ValueError):
        return False
    if not all(_valid_number(v) for v in (x, y, w, h)):
        return False
    if w <= 0 or h <= 0:
        return False
    return True


def iou(a, b) -> float:
    """Intersection-over-union of two [x, y, w, h] boxes (0.0 if no overlap)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def match_detections(preds, labels, iou_thresh=0.5):
    """Greedy one-to-one IoU matching.

    Invalid predicted boxes are ignored (counted neither TP nor FP — callers
    must validate inputs separately; see validate_box). Returns
    (tp, fp, fn, matches) where matches is a list of (pred_idx, label_idx).
    """
    valid = [(i, p) for i, p in enumerate(preds) if validate_box(p)]
    unmatched_labels = set(range(len(labels)))
    candidates = []
    for i, p in valid:
        for j, lab in enumerate(labels):
            if not validate_box(lab):
                continue
            v = iou(p, lab)
            if v >= iou_thresh:
                candidates.append((v, i, j))
    candidates.sort(key=lambda c: c[0], reverse=True)
    used_p, used_l, matches = set(), set(), []
    for v, i, j in candidates:
        if i in used_p or j in used_l:
            continue
        used_p.add(i)
        used_l.add(j)
        matches.append((i, j))
    tp = len(matches)
    fp = len(valid) - tp
    fn = len([j for j in unmatched_labels if j not in used_l
              and validate_box(labels[j])])
    return tp, fp, fn, matches


def prf(tp, fp, fn):
    """(precision, recall, f1), each None when its denominator is zero."""
    prec = tp / (tp + fp) if (tp + fp) > 0 else None
    rec = tp / (tp + fn) if (tp + fn) > 0 else None
    if prec is None or rec is None or (prec + rec) == 0:
        f1 = None if (prec is None or rec is None) else 0.0
        if prec is not None and rec is not None and prec + rec == 0:
            f1 = 0.0
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def far_frr(genuine, impostor, threshold):
    """FAR/FRR at one threshold for distance scores (accept iff s <= thr).

    Returns dict with far, frr (None on empty side), and all four counts.
    A score exactly equal to the threshold counts as ACCEPTED.
    """
    n_gen = len(genuine)
    n_imp = len(impostor)
    fr = sum(1 for s in genuine if s > threshold)
    fa = sum(1 for s in impostor if s <= threshold)
    return {
        "threshold": threshold,
        "far": (fa / n_imp) if n_imp else None,
        "frr": (fr / n_gen) if n_gen else None,
        "false_accepts": fa,
        "false_rejects": fr,
        "n_impostor": n_imp,
        "n_genuine": n_gen,
    }


def roc_points(genuine, impostor, thresholds):
    """List of (threshold, far, frr) sorted by threshold ascending."""
    return [(t, far_frr(genuine, impostor, t)["far"],
             far_frr(genuine, impostor, t)["frr"]) for t in sorted(thresholds)]


def auc(genuine, impostor, thresholds):
    """Trapezoidal AUC of TPR (=1-FRR) over FAR. None if either side is empty
    or no finite operating point exists."""
    if not genuine or not impostor:
        return None
    pts = [(far, 1.0 - frr) for _, far, frr in roc_points(genuine, impostor,
                                                          thresholds)
           if far is not None and frr is not None]
    if not pts:
        return None
    pts.sort(key=lambda p: (p[0], p[1]))
    area = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        area += (x1 - x0) * (y0 + y1) / 2.0
    # Anchor the curve at (0, y_at_0) and (1, y_at_1) extremes is caller
    # policy; raw trapezoidal over swept points is reported as-is.
    return area


def eer_threshold(genuine, impostor, thresholds):
    """Threshold minimizing |FAR - FRR|; returns (threshold, far, frr).

    EER estimate is (far + frr) / 2 at that threshold — an operating-point
    estimate, not an interpolated crossing. None threshold if a side is empty.
    """
    if not genuine or not impostor or not thresholds:
        return None, None, None
    best = None
    for t in sorted(thresholds):
        r = far_frr(genuine, impostor, t)
        gap = abs(r["far"] - r["frr"])
        if best is None or gap < best[0]:
            best = (gap, t, r["far"], r["frr"])
    return best[1], best[2], best[3]


def top1_accuracy(results):
    """results: iterable of (predicted_id_or_None, true_id).

    Returns (accuracy_or_None, n_correct, n_total, mismatches) where a None
    prediction always counts as incorrect; empty input → accuracy None.
    """
    rows = list(results)
    if not rows:
        return None, 0, 0, []
    correct = sum(1 for p, t in rows if p is not None and p == t)
    mism = [(p, t) for p, t in rows if not (p is not None and p == t)]
    return correct / len(rows), correct, len(rows), mism


def latency_stats(samples):
    """(n, median_or_None, p95_or_None). p95 = nearest-rank ceil(0.95*n).

    Empty input → (0, None, None). Single sample → median == p95 == value.
    """
    xs = sorted(samples)
    n = len(xs)
    if n == 0:
        return 0, None, None
    mid = n // 2
    median = xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0
    p95 = xs[min(n - 1, math.ceil(0.95 * n) - 1)]
    return n, median, p95
