#!/usr/bin/env python3
"""AC-2 fault-injection negative test with KPI-4 / KPI-6 reporting.

Scenario (mandatory negative tests):
  1. Start all containers (``docker compose up -d --build``).
  2. Force a fresh backend model-loading window (``restart backend``), then
     while the backend is still in that loading phase forcibly kill the ``db``
     container (``docker compose kill db`` == SIGKILL, no graceful shutdown).
  3. Verify the backend health probe catches the DB failure -- i.e.
     ``GET /healthz/readiness`` reverts to / stays at 503 -- and recovers
     cleanly to 200 OK once the DB reboots (``docker compose start db``),
     WITHOUT requiring a backend restart.
  4. Print a PASS/FAIL report with recovery time (KPI-4) and latency
     impact (KPI-6), and persist machine-readable JSON + CSV artifacts.

Only the Python standard library + the ``docker`` CLI are required
(subprocess is used instead of the Docker SDK so there are no extra deps).

Exit code: 0 on overall PASS, 1 on FAIL, 2 on harness/setup error.
"""
import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]  # repo root (tests/..)


# ---------------------------------------------------------------- helpers
def sh(*cmd, cwd, timeout=180):
    """Run a command, return CompletedProcess (never raises on nonzero exit)."""
    return subprocess.run(list(cmd), cwd=str(cwd), timeout=timeout,
                           capture_output=True, text=True)


def compose(root, *args, timeout=180):
    return sh("docker", "compose", *args, cwd=root, timeout=timeout)


def now_wall():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def probe(base_url, timeout=5):
    """One GET /healthz/readiness sample. HTTP errors (503) are valid samples."""
    target = base_url.rstrip("/") + "/healthz/readiness"
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(target, timeout=timeout) as r:
            code, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:          # 503 while loading / db down
        code = e.code
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
    except Exception:                            # connection refused, timeout, ...
        return {"wall": now_wall(), "t": time.monotonic(), "code": 0,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "phase": "unreachable", "model_ready": False,
                "db_ready": False, "uptime_s": 0.0}
    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        body = {}
    return {"wall": now_wall(), "t": time.monotonic(), "code": code,
            "latency_ms": latency_ms,
            "phase": str(body.get("phase", "?")),
            "model_ready": bool(body.get("model_ready", False)),
            "db_ready": bool(body.get("db_ready", False)),
            "uptime_s": float(body.get("uptime_s", 0.0) or 0.0)}


def poll_until(base_url, want, timeout, interval=1.0, tag="", log=None):
    """Poll readiness until want(sample) is True. Returns (sample|None, elapsed)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        s = probe(base_url)
        s["tag"] = tag
        if log is not None:
            log.append(s)
        if want(s):
            return s, time.monotonic() - t0
        time.sleep(interval)
    return None, time.monotonic() - t0


def take_samples(base_url, n, interval=1.0, tag="", log=None):
    out = []
    for _ in range(n):
        s = probe(base_url)
        s["tag"] = tag
        out.append(s)
        if log is not None:
            log.append(s)
        time.sleep(interval)
    return out


def pct(data, p):
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[f] + (s[c] - s[f]) * (k - f), 1)


def lat_stats(samples):
    lat = [s["latency_ms"] for s in samples]
    errs = sum(1 for s in samples if s["code"] != 200)
    return {"n": len(lat),
            "mean_ms": round(statistics.mean(lat), 1) if lat else 0,
            "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95),
            "max_ms": max(lat) if lat else 0,
            "non_200": errs}


def container_id(root, svc):
    p = compose(root, "ps", "-q", svc, timeout=30)
    return p.stdout.strip().splitlines()[0].strip() if p.returncode == 0 and p.stdout.strip() else ""


def db_up(root):
    p = compose(root, "exec", "-T", "db",
                "pg_isready", "-U", "analytics", "-d", "analytics", timeout=30)
    return p.returncode == 0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="AC-2 fault-injection test (KPI-4/KPI-6).")
    ap.add_argument("--project-dir", default=str(ROOT))
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--services", nargs="*", default=None,
                    help="limit 'up' to these services (default: all)")
    ap.add_argument("--build", action="store_true", default=True)
    ap.add_argument("--no-build", dest="build", action="store_false")
    ap.add_argument("--no-backend-restart", dest="restart_backend",
                    action="store_false", default=True,
                    help="skip forcing a fresh model-loading window")
    ap.add_argument("--startup-timeout", type=float, default=120)
    ap.add_argument("--detect-timeout", type=float, default=60)
    ap.add_argument("--recovery-timeout", type=float, default=180)
    ap.add_argument("--post-samples", type=int, default=10)
    ap.add_argument("--json", default="fault_report.json")
    ap.add_argument("--csv", default="fault_samples.csv")
    a = ap.parse_args()
    root, base = a.project_dir, a.base_url
    samples, checks = [], {}
    t_start = time.monotonic()

    def fail(msg):
        print(f"HARNESS ERROR: {msg}", file=sys.stderr)
        return 2

    # 1. Start all containers ------------------------------------------------
    up = ["up", "-d"] + (["--build"] if a.build else []) + (a.services or [])
    p = compose(root, *up, timeout=600)
    if p.returncode != 0:
        return fail(f"'docker compose {' '.join(up)}' failed:\n{p.stderr[-2000:]}")

    backend_id_before = container_id(root, "backend")

    # Force a fresh model-loading window so the fault lands mid-loading ------
    if a.restart_backend:
        p = compose(root, "restart", "backend", timeout=120)
        if p.returncode != 0:
            return fail(f"'docker compose restart backend' failed:\n{p.stderr[-2000:]}")
        backend_id_before = container_id(root, "backend")

    first, _ = poll_until(base, lambda s: s["code"] in (200, 503),
                          timeout=a.startup_timeout, tag="baseline", log=samples)
    if first is None:
        return fail("backend never answered HTTP (is port 8000 published?).")
    loading_phase_hit = first["code"] == 503  # fault lands inside model-loading
    time.sleep(2)  # stay inside the ~15s loading window, then inject the fault

    # 2. Forcibly kill db ------------------------------------------------------
    t_kill = time.monotonic()
    p = compose(root, "kill", "db", timeout=60)  # SIGKILL, container stays down
    if p.returncode != 0:
        return fail(f"'docker compose kill db' failed:\n{p.stderr[-2000:]}")

    # 3a. Backend must report 503 while the DB is down (AC-2a) -----------------
    s503, detect_lag = poll_until(base, lambda s: s["code"] == 503,
                                  timeout=a.detect_timeout, tag="fault", log=samples)
    checks["AC-2a_readiness_503_while_db_down"] = "PASS" if s503 else "FAIL"

    # Reboot the DB ------------------------------------------------------------
    t_reboot = time.monotonic()
    p = compose(root, "start", "db", timeout=120)
    if p.returncode != 0:
        return fail(f"'docker compose start db' failed:\n{p.stderr[-2000:]}")
    t0 = time.monotonic()
    while not db_up(root):
        if time.monotonic() - t0 > 120:
            return fail("db container never passed pg_isready after reboot.")
        time.sleep(2)
    t_db_up = time.monotonic()

    # 3b. Must recover to 200 WITHOUT a backend restart (AC-2b) -----------------
    s200, _ = poll_until(base, lambda s: s["code"] == 200,
                         timeout=a.recovery_timeout, tag="fault", log=samples)
    t_recovered = time.monotonic()
    backend_id_after = container_id(root, "backend")
    checks["AC-2b_readiness_200_after_db_reboot"] = "PASS" if s200 else "FAIL"
    checks["AC-2c_backend_not_restarted"] = (
        "PASS" if (s200 and backend_id_before and backend_id_before == backend_id_after)
        else ("FAIL" if s200 else "SKIP"))
    checks["INFO_fault_during_model_loading"] = (
        "YES" if loading_phase_hit else "NO (backend was already warm; steady-state fault)")

    # 4. Post-recovery steady-state samples for KPI-6 ---------------------------
    if s200:
        take_samples(base, a.post_samples, tag="recovered", log=samples)

    # KPIs ----------------------------------------------------------------------
    kpi4 = {"kill_to_200_s": round(t_recovered - t_kill, 1) if s200 else None,
            "reboot_to_200_s": round(t_recovered - t_reboot, 1) if s200 else None,
            "detect_503_lag_s": round(detect_lag, 1) if s503 else None,
            "db_reboot_s": round(t_db_up - t_reboot, 1)}
    by = lambda tag: [s for s in samples if s.get("tag") == tag]
    st = {k: lat_stats(by(k)) for k in ("baseline", "fault", "recovered")}
    kpi6 = {"per_phase_latency": st,
            "fault_p95_minus_baseline_p50_ms":
                round(st["fault"]["p95_ms"] - st["baseline"]["p50_ms"], 1),
            "recovered_p95_vs_baseline_p95_ms":
                round(st["recovered"]["p95_ms"] - st["baseline"]["p95_ms"], 1)
                if st["recovered"]["n"] else None}

    overall = ("PASS" if all(v == "PASS" for k, v in checks.items()
                             if k.startswith("AC-2")) else "FAIL")
    report = {"verdict": overall, "checks": checks, "KPI-4_recovery": kpi4,
              "KPI-6_latency_impact": kpi6,
              "total_harness_s": round(time.monotonic() - t_start, 1)}

    with open(a.json, "w") as f:
        json.dump(report, f, indent=2)
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["wall", "tag", "code", "latency_ms",
                                          "phase", "model_ready", "db_ready", "uptime_s"])
        w.writeheader()
        for s in samples:
            w.writerow({k: s.get(k) for k in w.fieldnames})

    # Console report -------------------------------------------------------------
    L = []
    L.append("=" * 60 + "\nAC-2 FAULT-INJECTION REPORT "
             f"(kill db during model-loading: {checks['INFO_fault_during_model_loading']})")
    for k, v in checks.items():
        L.append(f"  [{v:4}] {k}")
    L.append(f"KPI-4 recovery: kill->200 = {kpi4['kill_to_200_s']}s | "
             f"reboot->200 = {kpi4['reboot_to_200_s']}s | "
             f"detect-503 lag = {kpi4['detect_503_lag_s']}s | db reboot = {kpi4['db_reboot_s']}s")
    for ph, s in st.items():
        L.append(f"KPI-6 {ph:9}: n={s['n']} mean={s['mean_ms']}ms "
                 f"p50={s['p50_ms']}ms p95={s['p95_ms']}ms max={s['max_ms']}ms "
                 f"non_200={s['non_200']}")
    L.append(f"KPI-6 impact: fault p95 - baseline p50 = "
             f"{kpi6['fault_p95_minus_baseline_p50_ms']}ms")
    L.append(f"Artifacts: {a.json}, {a.csv}\nOVERALL: {overall}\n" + "=" * 60)
    print("\n".join(L))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
