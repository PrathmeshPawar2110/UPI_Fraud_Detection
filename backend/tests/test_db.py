"""Postgres URL handling for the pure-Python pg8000 driver."""

import pytest

from app.db import pg8000_args


@pytest.mark.parametrize("url,ssl,dropped", [
    # Neon / Vercel style: libpq options removed, TLS on
    ("postgresql+pg8000://u:p@ep-x-pooler.aws.neon.tech/neondb?sslmode=require&channel_binding=require", True,
     {"sslmode", "channel_binding"}),
    # remote host without sslmode still uses TLS
    ("postgresql+pg8000://u:p@db.example.com:5432/app", True, set()),
    # local Docker: plain connection
    ("postgresql+pg8000://postgres:pw@localhost:5432/postgres", False, set()),
    # explicit opt-out
    ("postgresql+pg8000://u:p@db.example.com/app?sslmode=disable", False, {"sslmode"}),
])
def test_pg8000_args(url, ssl, dropped):
    clean, args = pg8000_args(url)
    assert ("ssl_context" in args) is ssl
    assert not (set(clean.query) & {"sslmode", "channel_binding"})
    assert clean.host and clean.database and clean.password == "p" or clean.password == "pw"


def test_connect_timeout_is_translated():
    clean, args = pg8000_args("postgresql+pg8000://u:p@h.example.com/d?sslmode=require&connect_timeout=7")
    assert args["timeout"] == 7 and "connect_timeout" not in clean.query


def test_config_uses_pg8000(monkeypatch):
    import importlib

    from app import config
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h.example.com/d")
    try:
        importlib.reload(config)
        assert config.DATABASE_URL.startswith("postgresql+pg8000://")
    finally:
        monkeypatch.undo()
        importlib.reload(config)
