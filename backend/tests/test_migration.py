from __future__ import annotations

import sqlite3

LEGACY_SCHEMA = '''
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL, face_value REAL NOT NULL, min_spend REAL NOT NULL DEFAULT 0);
CREATE TABLE coupon_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL, campaign_code TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL, occurred_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE redeem_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, coupon_code TEXT NOT NULL UNIQUE,
  campaign_code TEXT NOT NULL, amount REAL NOT NULL, business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL, batch_id INTEGER, status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE redeem_batches (id INTEGER PRIMARY KEY AUTOINCREMENT, business_day TEXT NOT NULL,
  status TEXT NOT NULL, fact_count INTEGER NOT NULL DEFAULT 0, total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT, note TEXT NOT NULL DEFAULT '');
'''


def test_legacy_db_migrates_without_losing_batch_numbers(fresh_db):
    """The pre-compensating schema is rebuilt in place, once, without data loss."""
    conn = sqlite3.connect(fresh_db)
    conn.executescript(
        "DROP TABLE IF EXISTS coupon_events;"
        "DROP TABLE IF EXISTS redeem_facts;"
        "DROP TABLE IF EXISTS redeem_batches;"
        "DROP TABLE IF EXISTS campaigns;"
        "DROP TABLE IF EXISTS settings;"
    )
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('business_day', '2026-03-02')"
    )
    conn.execute(
        "INSERT INTO campaigns(code, title, face_value, min_spend) VALUES('NEW10', '新人', 10, 30)"
    )
    conn.execute(
        "INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount, business_day, occurred_at)"
        " VALUES('redeem', 'C-1', 'NEW10', 10, '2026-03-02', '2026-03-02T10:00:00')"
    )
    conn.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, batch_id, status)"
        " VALUES('C-1', 'NEW10', 10, '2026-03-02', 1, 1, 'sealed')"
    )
    conn.execute(
        "INSERT INTO redeem_batches(business_day, status, fact_count, total_amount, sealed_at)"
        " VALUES('2026-03-02', 'sealed', 1, 10, '2026-03-02T23:00:00')"
    )
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app

    init_db()
    init_db()  # must be idempotent

    client = TestClient(app)
    original = client.get("/api/batches/1").json()
    assert original["total_amount"] == 10.0
    assert original["fact_count"] == 1
    assert original["intact"] is True
    assert original["batch_kind"] == "redeem"
    assert original["compensates_batch_id"] is None

    # The old table-wide UNIQUE(coupon_code) must be replaced by a partial
    # index, so a return fact can coexist with the original redeem fact.
    resp = client.post(
        "/api/returns", json={"coupon_code": "C-1", "business_day": "2026-03-03"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["compensates_batch_id"] == 1

    resp = client.post("/api/returns/seal", json={"business_day": "2026-03-03"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["batches"][0]["compensates_batch_id"] == 1

    report = client.get("/api/reconciliation?business_day=2026-03-03").json()
    assert report["consistent"] is True, report["failed"]

    # Read-only guarantee: the legacy original keeps its numbers.
    after = client.get("/api/batches/1").json()
    assert after["total_amount"] == 10.0
    assert after["fact_count"] == 1
