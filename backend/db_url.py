# ============================================================
# GREEN App — DATABASE_URL helpers
# DATABASE_URL is the only setting the database needs. These helpers
# normalise it, pick a pool that suits the server, and render it for logs
# without the password.
#   production : MySQL/MariaDB of o2switch (cPanel), driver PyMySQL
#   development: SQLite file
#   PostgreSQL : former Supabase database, still accepted (data copy, tests)
# ============================================================

from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

# Supabase pooler in transaction mode: every transaction may land on a
# different server connection, so the app must not keep its own pool.
TRANSACTION_POOLER_PORT = 6543

# PyMySQL is pure Python: no compiler needed on the shared hosting
# (mysqlclient would have to be built, and o2switch blocks gcc by default).
MYSQL_DRIVER = "mysql+pymysql"

# Every MySQL session: UTC (CURRENT_TIMESTAMP defaults, like utcnow() in the
# code) and a strict, explicit SQL mode, so MariaDB and MySQL 8 behave the
# same whatever the server defaults are (too long a value is an error, not
# silently truncated).
MYSQL_INIT_COMMAND = (
    "SET time_zone = '+00:00', sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,"
    "NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
)


def normalize_database_url(url: str) -> str:
    """
    - `mysql://`, `mariadb://`, `mysql+pymysql://` → `mysql+pymysql://`,
      with `charset=utf8mb4` unless set (accents and emoji);
    - `postgres://` → `postgresql://`, with `sslmode=require` unless set;
    - SQLite URLs are returned unchanged.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    u = make_url(url)
    backend = u.get_backend_name()
    if backend in ("mysql", "mariadb"):
        u = u.set(drivername=MYSQL_DRIVER)
        if "charset" not in u.query:
            u = u.update_query_dict({"charset": "utf8mb4"})
    elif backend == "postgresql" and "sslmode" not in u.query:
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
    if u.get_backend_name() == "mysql":
        # Passenger may start several worker processes, each with its own
        # pool: keep it small. MySQL closes idle connections after
        # wait_timeout (often a few minutes on shared hosting): recycle
        # before that, pool_pre_ping catches the rest.
        kwargs.update(pool_size=2, max_overflow=2, pool_recycle=280,
                      connect_args={"init_command": MYSQL_INIT_COMMAND})
    elif u.port == TRANSACTION_POOLER_PORT:
        kwargs["poolclass"] = NullPool
    else:
        # Session pooler (5432) or a plain server.
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
    if u.get_backend_name() == "mysql" and host not in ("", "localhost", "127.0.0.1"):
        out.append(
            "DATABASE_URL points at a remote MySQL server: on o2switch the database "
            "runs on the same machine as the app, use host localhost."
        )
    return out
