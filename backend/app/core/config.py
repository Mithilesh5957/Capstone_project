"""FACEATTEND MARP — central configuration (env-driven, no hardcoding).

Single authoritative source for JWT settings and the ENVIRONMENT contract.
ENVIRONMENT must be set explicitly (development|test|production); see
resolve_environment(). JWT_SECRET is defined here only — security.py imports
it (no divergent defaults)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analytics:analytics@db:5432/analytics")
MODEL_LOAD_SECONDS = int(os.getenv("MODEL_LOAD_SECONDS", "15"))
REID_THRESHOLD = float(os.getenv("REID_THRESHOLD", "0.85"))
EMBED_SIZE = 64

FRAME_W, FRAME_H = 640, 480
DET_SCALE_FACTOR = 1.1
DET_MIN_NEIGHBORS = 6
DET_MIN_SIZE = (80, 80)
DET_ASPECT_LO, DET_ASPECT_HI = 0.7, 1.3
NEON_GREEN_BGR = (0, 255, 0)

JWT_SECRET = os.getenv("JWT_SECRET", "faceattend-dev-secret")
JWT_ALG = "HS256"
JWT_TTL_S = int(os.getenv("JWT_TTL_S", "86400"))

# Deployment-environment contract (Phase 1B):
# - "development": explicit local development only (dev defaults allowed).
# - "test": controlled test runs only (dev defaults allowed).
# - "production": strong, explicitly configured secrets; refuses to boot
#   with missing/weak/documented-default secrets (see validate_startup_secrets).
# A missing, blank, or unsupported value FAILS AT IMPORT with a clear error —
# it never silently grants development behavior. Every launcher (compose
# services, K8s env, test fixtures, local shell) must set ENVIRONMENT
# explicitly. Use resolve_environment() to test this contract without imports.
VALID_ENVIRONMENTS = ("development", "test", "production")


def resolve_environment(raw: str | None) -> str:
    """Resolve and validate the ENVIRONMENT selection.

    Raises ValueError for missing/blank/unsupported values so insecure
    startup fails clearly instead of silently falling back to development.
    """
    value = (raw or "").strip().lower()
    if not value:
        raise ValueError(
            "ENVIRONMENT is missing or blank. Set ENVIRONMENT explicitly to "
            "'development' (local only), 'test' (controlled tests), or "
            "'production' (strong secrets required). See .env.example."
        )
    if value not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"Unsupported ENVIRONMENT={value!r}. Expected one of "
            f"{list(VALID_ENVIRONMENTS)}. Refusing to guess a security posture."
        )
    return value


ENVIRONMENT = resolve_environment(os.getenv("ENVIRONMENT"))

# Secrets that MUST be overridden in production. Compared verbatim so that
# a deployment that merely re-uses the documented dev values still fails.
INSECURE_JWT_SECRETS = {
    "faceattend-dev-secret",
    "faceattend-dev-secret-change-in-prod-32chars!",
    "default_dev_secret_change_me",
    "change_me",
    "secret",
}
INSECURE_ADMIN_PASSWORDS = {"admin123", "admin", "password", "change_me", "changeme"}

MIN_JWT_SECRET_LEN = 32
MIN_ADMIN_PASSWORD_LEN = 12


def is_production() -> bool:
    return ENVIRONMENT == "production"


def is_development() -> bool:
    return ENVIRONMENT == "development"


def is_test() -> bool:
    return ENVIRONMENT == "test"


def validate_startup_secrets() -> None:
    """Fail fast when production would run with known/weak secrets.

    Raises RuntimeError in production if JWT_SECRET or ADMIN_PASSWORD is
    missing, too short, or one of the documented dev defaults. In
    non-production environments this is a no-op (dev defaults allowed).
    """
    if not is_production():
        return
    jwt_secret = os.getenv("JWT_SECRET", "")
    if (
        not jwt_secret
        or len(jwt_secret) < MIN_JWT_SECRET_LEN
        or jwt_secret in INSECURE_JWT_SECRETS
    ):
        raise RuntimeError(
            "Refusing to start: JWT_SECRET is missing, shorter than "
            f"{MIN_JWT_SECRET_LEN} chars, or a known dev default. Set a strong "
            "ENVIRONMENT=production JWT_SECRET (see .env.example)."
        )
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if (
        not admin_pw
        or len(admin_pw) < MIN_ADMIN_PASSWORD_LEN
        or admin_pw in INSECURE_ADMIN_PASSWORDS
    ):
        raise RuntimeError(
            "Refusing to start: ADMIN_PASSWORD is missing, shorter than "
            f"{MIN_ADMIN_PASSWORD_LEN} chars, or a known dev default. Set a strong "
            "ENVIRONMENT=production ADMIN_PASSWORD (see .env.example)."
        )

# YOLO / MediaPipe preferences (fallback chain is automatic)
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "yolov8n-face.pt")
FACE_BACKEND_ORDER = os.getenv("FACE_BACKEND_ORDER", "yolo,mediapipe,haar").split(",")

# Chaos defaults (in-situ, no root required)
CHAOS_DEFAULTS = {
    "vram_latency_s": 0.0,
    "frame_drop_rate": 0.0,
    "model_stall": False,
    "simulated_latency_sec": 0.0,
    "simulate_vram_exhaustion": False,
    "artificial_probe_failure": False,
}
