"""FACEATTEND Phase 1B regression tests: environment-security contract.

Covers §6 items 1-12 (item 13 = the R1 suite, run separately and required to
stay green). Behavior-first: subprocess import checks, real startup
validation, real `docker compose config` runs with synthetic placeholders
(secrets never printed), and manifest assertions. Static YAML checks are
marked as such; YAML validity does not prove a deployment works.
"""
import os
import shutil
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# This suite itself runs under the explicit test configuration (the contract
# under test requires ENVIRONMENT to be set for any in-process import).
os.environ.setdefault("ENVIRONMENT", "test")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
PROD_COMPOSE = ["docker", "compose", "-f", "docker-compose.yml",
                "-f", "docker-compose.prod.yml", "config"]

SYNTHETIC_SECRETS = {
    "JWT_SECRET": "synthetic-test-only-0123456789abcdef",
    "ADMIN_PASSWORD": "synthetic-test-only-pw",
    "POSTGRES_PASSWORD": "synthetic-test-only-db",
    "DATABASE_URL": "postgresql://analytics:synthetic-test-only-db@db:5432/analytics",
}
DEV_LITERALS = ("admin123", "default_dev_secret_change_me",
                "faceattend-dev-secret", "analytics:analytics@")
REQUIRED_VARS = ("JWT_SECRET", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "DATABASE_URL")


def _clean_env(**overrides):
    env = dict(os.environ)
    for k in ("ENVIRONMENT",) + REQUIRED_VARS:
        env.pop(k, None)
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


def _import_config(env_value):
    """Real behavior: import app.core.config in a fresh interpreter.

    Returns (returncode, stdout, stderr). Missing/blank/unknown ENVIRONMENT
    must fail; explicit development/test must succeed.
    """
    env = _clean_env()
    if env_value is not None:
        env["ENVIRONMENT"] = env_value
    return subprocess.run(
        [sys.executable, "-c",
         "import app.core.config as c; print('ENVIRONMENT=' + c.ENVIRONMENT)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


# ---- §6.1/§6.2: missing, blank, unsupported environment ----
@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_or_blank_environment_fails_at_import(raw):
    env = _clean_env()
    if raw is not None:
        env["ENVIRONMENT"] = raw
    p = subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert p.returncode != 0, "blank ENVIRONMENT must not boot"
    assert "ENVIRONMENT" in (p.stderr or ""), p.stderr


@pytest.mark.parametrize("raw", ["prod", "staging", "production ",
                                 "development ", "dev", "TESTING"])
def test_unsupported_environment_fails_at_import(raw):
    p = _import_config(raw if raw.strip() else raw)
    if raw.strip().lower() in ("production", "development"):
        assert p.returncode == 0, p.stderr
    else:
        assert p.returncode != 0, f"{raw!r} must fail, got: {p.stdout}"
        assert "ENVIRONMENT" in (p.stderr or "")


def test_explicit_environments_import_cleanly():
    for value in ("development", "test", "production"):
        p = _import_config(value)
        assert p.returncode == 0, f"{value}: {p.stderr}"
        assert f"ENVIRONMENT={value}" in p.stdout


# ---- §6.3/§6.4: dev and test startup allow local defaults ----
def test_development_startup_allows_dev_defaults(monkeypatch):
    import app.core.config as config

    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET", "default_dev_secret_change_me")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123")
    config.validate_startup_secrets()  # must not raise


def test_test_environment_allows_local_defaults(monkeypatch):
    import app.core.config as config

    monkeypatch.setattr(config, "ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    config.validate_startup_secrets()  # must not raise


# ---- §6.5–§6.8: production secret matrix ----
@pytest.mark.parametrize("jwt,admin", [
    ("", ""),                                  # both missing
    ("", "StrongTestPass-2026!"),              # missing JWT
    ("a-very-long-test-secret-0123456789abcdef", ""),  # missing admin
    ("short", "short"),                        # too short
    ("faceattend-dev-secret", "StrongTestPass-2026!"),  # documented default
    ("default_dev_secret_change_me", "StrongTestPass-2026!"),
    ("a-very-long-test-secret-0123456789abcdef", "admin123"),
])
def test_production_rejects_bad_secrets(monkeypatch, jwt, admin):
    import app.core.config as config

    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", jwt)
    monkeypatch.setenv("ADMIN_PASSWORD", admin)
    with pytest.raises(RuntimeError):
        config.validate_startup_secrets()


def test_production_accepts_strong_secrets(monkeypatch):
    import app.core.config as config

    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-very-long-test-secret-0123456789abcdef")
    monkeypatch.setenv("ADMIN_PASSWORD", "StrongTestPass-2026!")
    config.validate_startup_secrets()  # must not raise


# ---- §6.10/§6.11: production compose file ----
def _load_prod_compose():
    with open(os.path.join(REPO_ROOT, "docker-compose.prod.yml")) as f:
        return yaml.safe_load(f)


def test_prod_compose_selects_production_and_requires_secrets():
    """Static: prod override pins ENVIRONMENT=production and uses required
    interpolation for every sensitive value. Static-only: does not prove a
    deployment works."""
    doc = _load_prod_compose()
    backend_env = doc["services"]["backend"]["environment"]
    assert backend_env["ENVIRONMENT"] == "production"
    text = open(os.path.join(REPO_ROOT, "docker-compose.prod.yml")).read()
    for var in REQUIRED_VARS:
        assert "${%s:?" % var in text, f"{var} must use required interpolation"
    for lit in ("admin123", "default_dev_secret_change_me",
                "faceattend-dev-secret"):
        assert lit not in text, f"dev default leaked into prod file: {lit}"


def test_prod_compose_rejects_missing_secrets():
    compose = shutil.which("docker")
    if compose is None:
        pytest.skip("docker unavailable")
    p = subprocess.run(PROD_COMPOSE, cwd=REPO_ROOT, env=_clean_env(),
                       capture_output=True, text=True, timeout=120)
    assert p.returncode != 0, "prod config must fail without required secrets"


def test_prod_compose_renders_production_without_dev_defaults():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable")
    env = _clean_env(**SYNTHETIC_SECRETS)
    p = subprocess.run(PROD_COMPOSE, cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = p.stdout
    assert "ENVIRONMENT: production" in out
    for lit in DEV_LITERALS:
        assert lit not in out, f"dev default in rendered prod config: {lit}"
    # Never echo secrets: only assert on known-safe markers (no output dump).


# ---- §6.12: kubernetes manifests (static checks) ----
def _k8s_docs(path):
    with open(os.path.join(REPO_ROOT, path)) as f:
        return list(yaml.safe_load_all(f))


def test_k8s_no_hardcoded_dev_credentials():
    """Static: manifests must not embed real or documented-default secrets."""
    for path in ("k8s/backend-deployment.yaml", "k8s/backend-secret.example.yaml"):
        text = open(os.path.join(REPO_ROOT, path)).read()
        for lit in ("admin123", "faceattend-dev-secret",
                    "default_dev_secret_change_me"):
            assert lit not in text, f"{path} contains dev secret: {lit}"


def test_k8s_secret_wiring_and_prod_mode():
    """Static: Secret object removed from tracked manifest; example provided;
    deployment pins ENVIRONMENT=production and references required keys."""
    docs = _k8s_docs("k8s/backend-deployment.yaml")
    kinds = [d.get("kind") for d in docs if isinstance(d, dict)]
    assert "Secret" not in kinds, "tracked manifest must not ship a Secret"
    assert "ConfigMap" in kinds and "Deployment" in kinds
    config = next(d for d in docs if d.get("kind") == "ConfigMap")
    assert config["data"]["ENVIRONMENT"] == "production"
    deploy = next(d for d in docs if d.get("kind") == "Deployment")
    env = deploy["spec"]["template"]["spec"]["containers"][0]["env"]
    refs = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in env}
    for key in ("JWT_SECRET", "ADMIN_PASSWORD", "DATABASE_URL"):
        assert refs.get(key, {}).get("name") == "faceattend-backend-secret"
        assert refs[key].get("key") == key
    assert any(e["name"] == "ENVIRONMENT" for e in env)
    example = open(os.path.join(REPO_ROOT,
                                "k8s/backend-secret.example.yaml")).read()
    assert "REPLACE_ME" in example
