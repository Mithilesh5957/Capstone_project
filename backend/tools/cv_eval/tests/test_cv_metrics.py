"""R8 metric-harness unit tests (synthetic score arrays ONLY).

These tests validate the metric implementation in backend/tools/cv_eval/.
Passing here proves the arithmetic is correct — it is NOT face-recognition
accuracy evidence (see docs/CV_EVALUATION_PROTOCOL.md §14).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from tools.cv_eval import manifest as M  # noqa: E402
from tools.cv_eval import metrics as m  # noqa: E402

BOX = [10, 10, 40, 40]


# ---------- IoU / box validation ----------

def test_iou_identical_is_one():
    assert m.iou(BOX, BOX) == pytest.approx(1.0)


def test_iou_disjoint_is_zero():
    assert m.iou(BOX, [100, 100, 40, 40]) == 0.0


def test_iou_half_overlap():
    # 20px overlap of 40px width -> inter 800, union 1600+1600-800=2400
    assert m.iou([0, 0, 40, 40], [20, 0, 40, 40]) == pytest.approx(800 / 2400)


def test_invalid_boxes_rejected():
    assert not m.validate_box([0, 0, 0, 40])       # zero width
    assert not m.validate_box([0, 0, -5, 40])      # negative width
    assert not m.validate_box([0, 0, 40])          # wrong length
    assert not m.validate_box([0, 0, float("nan"), 40])
    assert not m.validate_box("nope")
    assert m.validate_box(BOX)


# ---------- detection matching ----------

def test_perfect_detections():
    tp, fp, fn, matches = m.match_detections([BOX, [100, 100, 20, 20]],
                                             [BOX, [100, 100, 20, 20]])
    assert (tp, fp, fn) == (2, 0, 0) and len(matches) == 2
    assert m.prf(tp, fp, fn) == (1.0, 1.0, 1.0)


def test_missing_detections_all_fn():
    tp, fp, fn, _ = m.match_detections([], [BOX, [0, 0, 10, 10]])
    assert (tp, fp, fn) == (0, 0, 2)
    prec, rec, f1 = m.prf(tp, fp, fn)
    assert prec is None and rec == 0.0 and f1 is None


def test_false_detections_all_fp():
    tp, fp, fn, _ = m.match_detections([BOX], [])
    assert (tp, fp, fn) == (0, 1, 0)
    prec, rec, f1 = m.prf(tp, fp, fn)
    assert prec == 0.0 and rec is None and f1 is None


def test_empty_labels_and_preds():
    tp, fp, fn, matches = m.match_detections([], [])
    assert (tp, fp, fn, matches) == (0, 0, 0, [])
    assert m.prf(0, 0, 0) == (None, None, None)


def test_iou_threshold_boundary():
    # IoU exactly 0.5 matches at thresh 0.5, misses below-rule at 0.51
    pred = [20, 0, 40, 40]  # IoU 1/3 vs [0,0,40,40]... use exact-half pair
    a, b = [0, 0, 30, 30], [15, 0, 30, 30]  # inter 450 union 1350 -> 1/3
    assert m.iou(a, b) == pytest.approx(1 / 3)
    tp, _, _, _ = m.match_detections([a], [b], iou_thresh=1 / 3)
    assert tp == 1
    tp, fp, _, _ = m.match_detections([a], [b], iou_thresh=0.34)
    assert (tp, fp) == (0, 1)


def test_one_to_one_greedy_no_double_count():
    # two preds overlap one label: best takes it, other is FP
    tp, fp, fn, _ = m.match_detections([[9, 9, 42, 42], BOX], [BOX])
    assert (tp, fp, fn) == (1, 1, 0)


def test_invalid_pred_boxes_ignored_not_counted():
    tp, fp, fn, _ = m.match_detections([[0, 0, -5, 40]], [BOX])
    assert (tp, fp, fn) == (0, 0, 1)


# ---------- FAR / FRR ----------

def test_far_frr_typical():
    r = m.far_frr(genuine=[0.2, 0.5, 0.9], impostor=[0.7, 1.2], threshold=0.85)
    assert r["frr"] == pytest.approx(1 / 3)
    assert r["far"] == pytest.approx(1 / 2)
    assert (r["false_rejects"], r["false_accepts"],
            r["n_genuine"], r["n_impostor"]) == (1, 1, 3, 2)


def test_threshold_boundary_accepts_equal():
    r = m.far_frr(genuine=[0.85], impostor=[0.85], threshold=0.85)
    assert r["frr"] == 0.0 and r["far"] == 1.0


def test_all_genuine_edge_impostor_unavailable():
    r = m.far_frr(genuine=[0.1, 0.2], impostor=[], threshold=0.85)
    assert r["far"] is None and r["n_impostor"] == 0
    assert r["frr"] == 0.0


def test_all_impostor_edge_genuine_unavailable():
    r = m.far_frr(genuine=[], impostor=[0.1], threshold=0.85)
    assert r["frr"] is None and r["n_genuine"] == 0
    assert r["far"] == 1.0


def test_both_empty():
    r = m.far_frr([], [], threshold=0.85)
    assert r["far"] is None and r["frr"] is None


# ---------- ROC / AUC / EER ----------

def test_auc_perfect_separation_is_one():
    auc = m.auc(genuine=[0.1, 0.2, 0.3], impostor=[0.9, 1.0, 1.1],
                thresholds=[i / 10 for i in range(0, 21)])
    assert auc == pytest.approx(1.0)


def test_auc_empty_side_is_none():
    assert m.auc([], [0.5], [0.5]) is None
    assert m.auc([0.5], [], [0.5]) is None


def test_eer_threshold_separable():
    thr, far, frr = m.eer_threshold(genuine=[0.1, 0.2], impostor=[0.9, 1.0],
                                    thresholds=[0.05, 0.5, 0.95])
    assert thr == 0.5 and far == 0.0 and frr == 0.0


def test_eer_empty_is_none():
    assert m.eer_threshold([], [0.5], [0.5]) == (None, None, None)


# ---------- top-1 ----------

def test_top1_correct_and_incorrect():
    acc, ok, tot, mism = m.top1_accuracy([("s1", "s1"), ("s2", "s1"),
                                           (None, "s3")])
    assert acc == pytest.approx(1 / 3) and ok == 1 and tot == 3
    assert mism == [("s2", "s1"), (None, "s3")]


def test_top1_empty_is_none():
    assert m.top1_accuracy([]) == (None, 0, 0, [])


# ---------- latency ----------

def test_latency_stats_typical():
    n, med, p95 = m.latency_stats([0.1, 0.2, 0.3, 0.4, 0.5])
    assert (n, med, p95) == (5, 0.3, 0.5)


def test_latency_stats_even_median_and_single():
    n, med, p95 = m.latency_stats([0.2, 0.4])
    assert n == 2 and med == pytest.approx(0.3) and p95 == 0.4
    assert m.latency_stats([0.7]) == (1, 0.7, 0.7)
    assert m.latency_stats([]) == (0, None, None)


# ---------- manifest ----------

def _img(iid, split="probe_holdout", faces=None, path=None):
    return {"image_id": iid, "path": path or f"data/{iid}.jpg",
            "split": split,
            "faces": faces if faces is not None else [
                {"identity_id": "s01", "bbox": BOX}]}


def test_manifest_valid():
    man = {"images": [_img("a", "enrollment"), _img("b")]}
    assert M.validate_manifest(man) == []


def test_manifest_duplicate_ids_rejected():
    man = {"images": [_img("a"), _img("a")]}
    errs = M.validate_manifest(man)
    assert any("duplicate" in e for e in errs)


def test_manifest_bad_split_and_box_rejected():
    man = {"images": [_img("a", split="test"),
                      {"image_id": "b", "path": "p",
                       "split": "probe_dev",
                       "faces": [{"identity_id": "s1",
                                  "bbox": [0, 0, -2, 5]}]}]}
    errs = M.validate_manifest(man)
    assert any("split" in e for e in errs)
    assert any("bbox" in e for e in errs)


def test_manifest_missing_fields_rejected():
    assert M.validate_manifest({}) != []
    assert M.validate_manifest({"images": []}) != []
    assert M.validate_manifest({"images": [{"image_id": "x"}]}) != []


def test_manifest_unreadable_file():
    man, errs = M.load_manifest("/nonexistent/manifest.json")
    assert man is None and errs != []
