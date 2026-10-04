"""Database engine and sessions (SQLAlchemy 2). Postgres in production, SQLite locally and in tests."""

import ssl
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from . import config

# libpq-style URL options (as in Neon / Supabase / Vercel connection strings) that pg8000 doesn't accept.
LIBPQ_ONLY = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey", "connect_timeout", "target_session_attrs"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", None}


class Base(DeclarativeBase):
    pass


def pg8000_args(url: str):
    """Translate a libpq-style Postgres URL for pg8000: drop libpq-only options and turn `sslmode`
    into an SSL context (certificate-verified). Without `sslmode`, remote hosts still use TLS and
    local ones (e.g. Docker on localhost) don't."""
    u = make_url(url)
    mode = (u.query.get("sslmode") or "").lower()
    clean = u.difference_update_query(LIBPQ_ONLY)
    use_ssl = mode != "disable" and (mode != "" or u.host not in LOCAL_HOSTS)
    connect_args = {"ssl_context": ssl.create_default_context()} if use_ssl else {}
    if u.query.get("connect_timeout"):
        connect_args["timeout"] = int(u.query["connect_timeout"])
    return clean, connect_args


def _make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # enforce ON DELETE CASCADE in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    clean, connect_args = pg8000_args(url)
    if config.ON_VERCEL:
        # Serverless: no pooling across invocations; the database's own pooler (e.g. Neon's) handles that.
        engine = create_engine(clean, connect_args=connect_args, poolclass=NullPool)
    else:
        # Long-running server (local dev, single-server mode): reuse connections; a new TLS connection to a
        # remote database can take a second. Recycle before hosted Postgres drops idle connections.
        engine = create_engine(clean, connect_args=connect_args, pool_size=5, max_overflow=5,
                               pool_pre_ping=True, pool_recycle=240)
    # Always qualify tables as public.<table>. Behind a transaction-mode pooler (Neon, PgBouncer) server
    # connections are shared between clients, so a session setting such as search_path left by another
    # client must never decide which tables the app reads or writes.
    return engine.execution_options(schema_translate_map={None: "public"})


engine = _make_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
