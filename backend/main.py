"""Compat shim: `uvicorn main:app` serves the modular MARP app (backend/app/main.py)."""
from app.main import app  # noqa: F401
