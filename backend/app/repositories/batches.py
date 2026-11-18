from __future__ import annotations

import sqlite3
from typing import Any

from app import domain


def list_batches(
    conn: sqlite3.Connection,
    business_day: str | None = None,
    batch_kind: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if business_day:
        clauses.append("business_day=?")
        params.append(business_day)
    if batch_kind:
        clauses.append("batch_kind=?")
        params.append(batch_kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM redeem_batches{where} ORDER BY id DESC", params
    ).fetchall()
    return [dict(r) for r in rows]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM redeem_batches WHERE id=?", (batch_id,)
    ).fetchone()
    return dict(row) if row else None


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """INSERT INTO redeem_batches(
             business_day, status, fact_count, total_amount, sealed_at, note,
             batch_kind, compensates_batch_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
            fields.get("batch_kind") or domain.BATCH_KIND_REDEEM,
            fields.get("compensates_batch_id"),
        ),
    )
    return int(cur.lastrowid)


def compensating_batches_for_original(
    conn: sqlite3.Connection, original_batch_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_batches WHERE compensates_batch_id=? ORDER BY id",
        (original_batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]
