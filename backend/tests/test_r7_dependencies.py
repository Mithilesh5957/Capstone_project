"""R7 dependency reproducibility: manifests are pinned and consistent.

Verifies the *declared* dependency contract (files), not the ambient
interpreter: the pinned set targets Python 3.11 (production image), while
this suite may run on newer Pythons. Runtime CV imports are exercised
wherever the interpreter supports them; the test never fails merely
because the local interpreter differs from the pinned target.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Importing app modules requires an explicit ENVIRONMENT (R2 contract).
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "R1_TEST_DATABASE_URL",
        "postgresql+psycopg://postgres@localhost/faceattend_r1_test",
    ),
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _req_lines():
    with open(os.path.join(REPO_ROOT, "backend", "requirements.txt")) as f:
        return [l.split("#")[0].strip() for l in f if l.strip() and not l.startswith("#")]


def test_backend_requirements_fully_pinned():
    for line in _req_lines():
        assert re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[^,;\s]+", line), \
            f"unpinned requirement: {line!r}"


def test_opencv_pair_shares_one_build():
    """opencv-python + opencv-contrib-python at one 4.8.1.78 build: both names
    are required (ultralytics needs opencv-python>=4.6.0, mediapipe needs
    opencv-contrib-python), and same-build shadowing stays ABI-identical
    instead of drifting to numpy-2-only 5.x."""
    pins = {}
    for line in _req_lines():
        m = re.fullmatch(r"(opencv-[a-z\-]*)==([0-9.]+)", line)
        if m:
            pins[m.group(1)] = m.group(2)
    assert set(pins) == {"opencv-python", "opencv-contrib-python"}, pins
    assert len(set(pins.values())) == 1, pins


def test_opencv_headless_not_listed():
    """No third same-path cv2 writer: nothing requires opencv-python-headless
    by name, so listing it only adds shadowing fragility (see requirements)."""
    names = [line.split("==")[0] for line in _req_lines()]
    assert "opencv-python-headless" not in names, names


def test_numpy_pinned_to_1x_for_opencv48():
    pins = dict(line.split("==") for line in _req_lines())
    assert pins["numpy"].startswith("1."), pins["numpy"]


def test_frontend_lockfile_consistent_with_manifest():
    lock_path = os.path.join(REPO_ROOT, "frontend", "package-lock.json")
    assert os.path.exists(lock_path), "package-lock.json must be committed"
    lock = json.load(open(lock_path))
    assert lock.get("lockfileVersion") in (2, 3)
    root_ts = lock["packages"]["node_modules/typescript"]["version"]
    major = int(root_ts.split(".")[0])
    assert major in (3, 4), f"hoisted typescript {root_ts} breaks react-scripts range ^3.2.1 || ^4"
    manifest = json.load(open(os.path.join(REPO_ROOT, "frontend", "package.json")))
    assert "typescript" in manifest.get("overrides", {}), \
        "typescript must be constrained via overrides (see R7 report)"


def _require_pinned_cv2():
    """The pinned target is opencv 4.8.1.78 (Python 3.11). Newer ambient
    builds (e.g. cv2 5.x, which moved CascadeClassifier) are explicitly
    out of scope here; the authoritative check runs in the pinned
    py3.11 container (see R7 report)."""
    cv2 = pytest.importorskip("cv2", reason="opencv not installed here")
    if int(cv2.__version__.split(".")[0]) != 4:
        pytest.skip(
            f"ambient cv2 {cv2.__version__} differs from pinned 4.8.1.78; "
            "see container-based check in the R7 report")
    return cv2


def test_cv_runtime_importable():
    """Capability check on the ambient interpreter (informational versions)."""
    cv2 = _require_pinned_cv2()
    import numpy

    import app.services.face_detection as fdmod  # noqa: F401
    import app.services.face_recognition as frmod  # noqa: F401
    assert hasattr(cv2, "CascadeClassifier")
    assert hasattr(frmod, "embedding_from_bytes")
    assert hasattr(fdmod, "FaceDetector")
    print(f"\n[runtime] cv2={cv2.__version__} numpy={numpy.__version__} "
          f"(pinned target: cv2 4.8.1.78 / numpy 1.26.4 on Python 3.11)")


def test_haar_cascade_loads_from_bundled_data():
    cv2 = _require_pinned_cv2()
    cc = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    assert not cc.empty(), "bundled Haar cascade must load (offline fallback)"
