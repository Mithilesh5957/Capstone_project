"""SQLAlchemy engine / session factory. Sync engine (psycopg2) — matches existing deploy."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE_URL

Base = declarative_base()

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Backwards-compat alias used by legacy code paths
Session = SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
