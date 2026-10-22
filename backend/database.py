# ============================================================
# GREEN App — Database Setup
# PostgreSQL (Supabase) or SQLite + SQLAlchemy ORM configuration.
# Creates the engine, session factory, and declarative base.
# The schema itself is managed by Alembic (backend/migrations).
# ============================================================

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL
from db_url import database_warnings, engine_kwargs, mask_database_url

logger = logging.getLogger(__name__)

# ---- Engine -------------------------------------------------
# Pool choice depends on the URL (NullPool behind the Supabase
# transaction pooler, a small pool otherwise): see db_url.engine_kwargs.
engine = create_engine(DATABASE_URL, echo=False, **engine_kwargs(DATABASE_URL))
IS_SQLITE = engine.dialect.name == "sqlite"

logger.info("Database: %s", mask_database_url(DATABASE_URL))
for _warning in database_warnings(DATABASE_URL):
    logger.warning(_warning)

# ---- Session Factory ----------------------------------------
# Each request gets its own session (opened/closed in dependency).
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ---- Declarative Base ----------------------------------------
# All ORM models inherit from this base class.
Base = declarative_base()


# ---- Dependency ---------------------------------------------
def get_db():
    """
    FastAPI dependency: yields a DB session per request,
    then closes it when the request is done.

    Usage in a route:
        @router.get("/something")
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
