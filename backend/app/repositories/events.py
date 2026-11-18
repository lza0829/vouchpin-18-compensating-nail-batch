from __future__ import annotations

import sqlite3
from typing import Any

from app import domain


def list_events(
    conn: sqlite3.Connection,
    business_day: str | None = None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if business_day:
        clauses.append("business_day=?")
        params.append(business_day)
    if event_type:
        clauses.append("event_type=?")
        params.append(event_type)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    if business_day:
        sql = f"SELECT * FROM coupon_events{where} ORDER BY id"
    else:
        sql = f"SELECT * FROM coupon_events{where} ORDER BY id DESC LIMIT 200"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_event(conn: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM coupon_events WHERE id=?", (event_id,)
    ).fetchone()
    return dict(row) if row else None


def return_event_for_fact(
    conn: sqlite3.Connection, compensates_fact_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM coupon_events WHERE compensates_fact_id=? AND event_type=? LIMIT 1",
        (compensates_fact_id, domain.EVENT_RETURN),
    ).fetchone()
    return dict(row) if row else None


def insert_event(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """INSERT INTO coupon_events(
             event_type, coupon_code, campaign_code, amount, business_day,
             occurred_at, note, compensates_fact_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            fields["event_type"],
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields.get("amount") or 0),
            fields["business_day"],
            fields["occurred_at"],
            fields.get("note") or "",
            fields.get("compensates_fact_id"),
        ),
    )
    return int(cur.lastrowid)


def redeem_events(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM coupon_events WHERE business_day=? AND event_type=? ORDER BY id",
        (business_day, domain.EVENT_REDEEM),
    ).fetchall()
    return [dict(r) for r in rows]
