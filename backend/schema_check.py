# ============================================================
# GREEN App — Alembic revision check at startup
# ============================================================

import logging
import os

logger = logging.getLogger(__name__)

ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "alembic.ini")


def head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(ALEMBIC_INI)).get_current_head()


def current_revision(connection):
    from alembic.runtime.migration import MigrationContext

    return MigrationContext.configure(connection).get_current_revision()


def warn_if_schema_outdated(engine) -> None:
    """Log (never raise): a startup failure would take the whole site down."""
    try:
        with engine.connect() as conn:
            current = current_revision(conn)
        head = head_revision()
    except Exception as e:  # DB unreachable at boot: pool_pre_ping retries later
        logger.error("Schema check skipped: %s", type(e).__name__)
        return
    if current != head:
        logger.warning(
            "Database schema at revision %s, code expects %s: run `alembic upgrade head` "
            "(or `alembic stamp 0001_baseline` first on a pre-Alembic database).",
            current, head,
        )
