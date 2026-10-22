# ============================================================
# GREEN App — DATABASE_URL helpers
# DATABASE_URL is the only setting the database needs. These helpers
# normalise it, pick a pool that suits the Supabase pooler, and render
# it for logs without the password.
# ============================================================

from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

# Supabase pooler in transaction mode: every transaction may land on a
# different server connection, so the app must not keep its own pool.
TRANSACTION_POOLER_PORT = 6543


def normalize_database_url(url: str) -> str:
    """
    Accept `postgres://` and `postgresql://`; add `sslmode=require` to
    PostgreSQL URLs that don't set it. SQLite URLs are returned unchanged.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    u = make_url(url)
    if u.get_backend_name() == "postgresql" and "sslmode" not in u.query:
        u = u.update_query_dict({"sslmode": "require"})
    return u.render_as_string(hide_password=False)


def mask_database_url(url: str) -> str:
    """Same URL with the password replaced by ***: safe for logs."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable DATABASE_URL>"


def engine_kwargs(url: str) -> dict:
    """create_engine() keyword arguments for this URL."""
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        # FastAPI serves requests from several threads.
        return {"connect_args": {"check_same_thread": False}}

    kwargs = {"pool_pre_ping": True}
    if u.port == TRANSACTION_POOLER_PORT:
        kwargs["poolclass"] = NullPool
    else:
        # Session pooler (5432) or a plain server. Passenger may start
        # several worker processes, each with its own pool: keep it small.
        kwargs.update(pool_size=2, max_overflow=2, pool_recycle=1800)
    return kwargs


def database_warnings(url: str) -> list:
    """Configuration problems worth a log line at startup."""
    u = make_url(url)
    out = []
    host = u.host or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        out.append(
            "DATABASE_URL uses the Supabase direct connection, which is IPv6-only "
            "without the IPv4 add-on. Shared hosting is usually IPv4: use the pooler "
            "URL (aws-0-<region>.pooler.supabase.com, port 6543 or 5432)."
        )
    return out
