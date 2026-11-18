from __future__ import annotations

import os
import tempfile

import pytest

# app.config resolves DB_PATH at import time; keep every test run in scratch.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="vouchpin-tests-"))

import app.config as config  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


def _reset_tables() -> None:
    conn = connect()
    try:
        for table in (
            "coupon_events",
            "redeem_facts",
            "redeem_batches",
            "campaigns",
            "settings",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def fresh_db(tmp_path):
    """Point the app at a brand-new SQLite file for one test."""
    old_path = config.DB_PATH
    config.DB_PATH = tmp_path / "clipbond.db"
    try:
        init_db()
        yield config.DB_PATH
    finally:
        config.DB_PATH = old_path


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app

    seed_if_empty()
    return TestClient(app)


@pytest.fixture()
def empty_client(fresh_db):
    """Client with schema in place but no seed rows (for legacy scenarios)."""
    from fastapi.testclient import TestClient

    from app.main import app

    _reset_tables()
    return TestClient(app)
