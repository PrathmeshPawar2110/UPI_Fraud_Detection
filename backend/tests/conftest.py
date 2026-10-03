"""Test setup: a fresh SQLite database per test session, set before the app is imported."""

import os
import tempfile
from pathlib import Path

_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.pop("ANTHROPIC_API_KEY", None)

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
_ids = itertools.count(1)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user(client):
    """A signed-in client for a brand-new user."""
    email = f"user{next(_ids)}@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery", "display_name": "T"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def other_user():
    c = TestClient(app)
    r = c.post("/api/auth/signup", json={"email": f"other{next(_ids)}@example.com", "password": "another long password"})
    assert r.status_code == 200, r.text
    return c
