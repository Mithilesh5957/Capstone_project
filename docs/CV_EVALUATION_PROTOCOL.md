# FACEATTEND — CV Evaluation Protocol (R8)

How the current face-detection and identity-recognition pipeline is measured,
and under what rules. This protocol separates **method** (here) from **results**
(`audit-output/PHASE_R8_CV_EVALUATION_REPORT.md` and per-run artifacts).
No numeric target below is a pass/fail gate unless an authoritative requirement
(SPEC ownership, UQ-01/UQ-02) adopts it; unadopted numbers are reported as
observations only.

## 1. Objectives and scope

- O1. Establish a defensible **detection baseline**: precision/recall/F1 of the
  configured detector pipeline at a stated IoU rule, with the producing backend
  (yolo/mediapipe/haar) recorded per result.
- O2. Establish a defensible **recognition baseline**: FAR/FRR at the configured
  operating threshold, genuine/impostor score distributions, ROC/AUC and EER
  where the data supports them, closed-set top-1 accuracy with confusion
  patterns — each with denominators and sample counts.
- O3. Measure **component latency and resources** on the actual evaluation
  machine (cold init + warm inference median/p95, RSS), without inferring
  production throughput or deployment SLO compliance.
- O4. Keep every claim in its lane: source inspection ≠ metric-unit tests ≠
  labelled-dataset evaluation ≠ synthetic checks ≠ model-loading tests ≠
  production measurements.

Out of scope for R8: changing the matcher, threshold, schema, endpoints, MARP,
or frontend; adopting learned embeddings; any accuracy optimization.

## 2. System under test (frozen for R8)

- Detector chain `FaceDetector` (`backend/app/services/face_detection.py`):
  order from `FACE_BACKEND_ORDER` (default `yolo,mediapipe,haar`); YOLO
  `conf=0.5`; aspect gate 0.7–1.3 (`DET_ASPECT_LO/HI`); Haar
  `scaleFactor=1.1`, `minNeighbors=6`, `minSize=80×80`; boxes sorted by area
  desc; confidence is an **area heuristic** (`0.80 + area_ratio*2.5`, cap 0.99),
  not a model score.
- Canonical frame 640×480 (`FRAME_W/H`, `INTER_LINEAR`); templates 64×64
  grayscale (`EMBED_SIZE`), `equalizeHist`, `/255`, L2-normalized 4096-vector.
- Representation: **raw pixel template, not a learned embedding** (SPEC FR-09).
- Matcher: 1-NN Euclidean distance (`face_recognition.match_student`); **lower
  distance = more similar**; accept iff `distance <= REID_THRESHOLD` (default
  0.85, env-overridable, uncalibrated — ROADMAP G-4.12). Geometry note: for
  L2-unit vectors the maximum distance is 2.0 and random high-dim pairs sit
  near √2 ≈ 1.414, so 0.85 is permissive; FAR must be measured, not assumed.
- Enrollment: mean of ≤8 image vectors, renormalized, stored as JSONB
  `students.embeddings` (`students_router.enroll_impl`).
- Attendance marking: `maybe_mark_present` keyed on
  `(active_session_id, student_id)` via in-process `marked_memory`; sessions
  pre-create `Absent` rows. Marking correctness is workflow logic, evaluated
  by the R1 lifecycle tests — not by CV metrics here.

## 3. Dataset provenance and permitted use

- Use only data with a clear license or explicit written consent for academic
  evaluation (e.g. institution-collected volunteer set with consent forms, or a
  public research benchmark used within its license). Record origin, license /
  consent reference, and collection date in the run manifest.
- **Forbidden**: real students' attendance records, enrolled production
  biometric templates, production databases, scraped web faces, inferred
  demographic attributes.
- Data stays local to the evaluation machine. Never upload biometric images,
  templates, or identifiable evaluation data to external services. Do not
  download large datasets automatically; any acquisition is a separate,
  explicitly authorized step.
- If no suitable dataset exists locally, empirical accuracy evaluation is
  **blocked**: complete the protocol, manifest format, and harness, and report
  the block. Candidate public benchmark *families* (options only, no results
  claimed): constrained frontal sets (e.g. AT&T/ORL-style lab sets), LFW-style
  unconstrained pairs (verification protocol), classroom-like multi-face sets
  if licensed. Suitability must be re-checked per license at acquisition time.

## 4. Ground-truth labelling requirements

- Detection: one record per image: list of face boxes `[x, y, w, h]` in pixels
  at the recorded canonical resolution, plus an `image_id`. Occluded faces
  beyond recognition use are flagged `difficult` and reported separately.
- Recognition: `identity_id` per face instance; enrollment vs probe assignment;
  capture `session_id` where available (lighting/pose/distance/occlusion tags
  encouraged for condition splits).
- Label quality: double-entry or adjudicated review for ≥10% of labels;
  disagreements logged. Missing/unparseable labels fail the sample (counted,
  never silently dropped from denominators).

## 5. Gallery/probe construction and splits

- **Closed-set identification**: gallery = enrollment images (follow the product
  rule: mean of ≤8 per identity where available); probes = disjoint images.
- **Session separation preferred**: gallery and probe from different capture
  sessions; near-duplicate frames (same burst/video seconds apart) must never
  straddle gallery and probe — dedupe by timestamp/hash before splitting.
- **Impostor comparisons**: all valid cross-identity probe-vs-gallery pairs
  (or a documented random subsample with seed) for FAR.
- **Dev/holdout**: exploratory threshold analysis on a dev split only; the
  final holdout is evaluated once with the pre-registered operating threshold
  (default 0.85 unless a dev-split calibration, documented before holdout,
  selects otherwise). Never tune on the test set and report it as unbiased.
- Minimum-size rule: if genuine or impostor counts are too small for a stable
  estimate, report the metric as **unavailable / statistically weak** with
  counts — never a bare percentage.

## 6. Data-leakage prevention checklist

- No shared frames, bursts, or near-duplicates across gallery/probe/holdout.
- No identity in both gallery-enrollment and impostor-probe roles within one
  comparison set unless the protocol explicitly defines open-set handling.
- Enrollment follows the product code path (mean vector); no hand-picked
  "best" enrollment image unless that variant is a separately reported arm.
- Manifest records split assignment per sample; the runner refuses samples
  with duplicate IDs or missing images (counted as errors).

## 7. Detection metrics

- Box matching: greedy match by IoU, one-to-one, at **IoU ≥ 0.5** (stated;
  alternatives only as extra reported arms, never silently).
- Counts: TP (matched), FP (unmatched predictions), FN (unmatched labels).
- Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1 = harmonic mean — each with
  its denominator. Report per-backend (yolo/mediapipe/haar/fallback-pipeline)
  separately; Haar-fallback success never stands in for YOLO/MediaPipe quality.
- Report missed-face and false-detection **sample IDs** (never images).
- Latency: per-image detect time at stated dimensions; median/p95 over runs.
- Init: record detector init success/failure per backend, missing weights,
  and which fallback actually served each image.

## 8. Recognition metrics

- Scores: Euclidean distances (lower = more similar); accept iff ≤ threshold.
- FAR = false accepts / impostor comparisons; FRR = false rejects / genuine
  comparisons. Report counts, not just rates.
- Distributions: genuine and impostor score histograms (binned counts).
- ROC/AUC over swept thresholds on the dev split; EER only if the data
  supports a valid estimate (state interpolation rule or mark unavailable).
- Closed-set top-1 accuracy + confusion patterns (which identities collide).
- Operating-point row: FAR/FRR/top-1 **at 0.85** (or the pre-registered
  threshold) on holdout — no single "accuracy" as a substitute for FAR/FRR.
- Condition splits (lighting/pose/distance) only where per-condition counts
  support comparison; otherwise report as unavailable.

## 9. Threshold policy

- The shipped default (0.85) is the pre-registered operating point.
- Any alternative threshold must be selected on the **dev split** (e.g. EER or
  fixed-FAR criterion, documented before holdout is touched) and then frozen.
- Never change the product threshold to improve a reported score in R8.

## 10. Environment recording

Every run records: CPU model/cores, GPU presence/absence (SPEC §10: no GPU
required or used), OS, Python version, `pip freeze` of the eval env (or the
image digest + requirements hash), image dimensions, `EMBED_SIZE`,
`FRAME_W/H`, detector order, threshold, MARP/model state if the app path is
used, and `git rev-parse HEAD` of the code under test. Secrets redacted.

## 11. Repeated runs and randomness

- Metric code is deterministic (no RNG in scoring). Any sampling (e.g.
  impostor subsample) uses a recorded seed.
- Detector/model inference is run as-is; run-to-run variance is reported, not
  averaged away silently (report n and spread).
- Holdout is evaluated once per registered configuration; re-runs after
  changes are new registered runs.

## 12. Result formats and artifacts

- Machine-readable run artifact: JSON with config, environment, counts,
  metrics, and per-sample outcomes (IDs + labels + scores, never images);
  optional CSV mirrors for plotting.
- Storage: `experiments/<date>-<slug>/` per VERIFICATION_PLAN §J (JSON/CSV +
  HEAD + redacted config). No images or real biometric templates in reports.
- The R8 report embeds only aggregate metrics with denominators.

## 13. Limitations, privacy, reproducibility

- Small samples → wide uncertainty; report counts and mark weak estimates.
- No demographic or subgroup claims without stratified, consented labels.
- No liveness/presentation-attack resistance (SPEC DATA-04); photo-of-photo
  acceptance is a disclosed limitation, not a measured pass.
- Classroom generalization requires classroom-condition data; lab-set numbers
  do not transfer silently.
- Reproduction: pinned env + manifest + seed + frozen code revision must
  suffice to replay any reported number.

## 14. Harness layout (informative)

- `backend/tools/cv_eval/`: `metrics.py` (pure-stdlib scoring), `manifest.py`
  (manifest load/validate), `run_eval.py` (pipeline runner over a manifest;
  unexecuted without approved data).
- `backend/tools/cv_eval/tests/test_cv_metrics.py`: unit tests for the metric
  implementation (synthetic score arrays — validate code, not accuracy).
- Metric-unit tests passing never constitutes recognition-accuracy evidence.
