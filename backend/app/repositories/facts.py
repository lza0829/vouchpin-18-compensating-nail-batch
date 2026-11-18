from __future__ import annotations

import sqlite3
from typing import Any

from app import domain


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


def list_facts(
    conn: sqlite3.Connection,
    business_day: str | None = None,
    fact_kind: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if business_day:
        clauses.append("business_day=?")
        params.append(business_day)
    if fact_kind:
        clauses.append("fact_kind=?")
        params.append(fact_kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    if business_day:
        sql = f"SELECT * FROM redeem_facts{where} ORDER BY id"
    else:
        sql = f"SELECT * FROM redeem_facts{where} ORDER BY id DESC LIMIT 200"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_fact(conn: sqlite3.Connection, fact_id: int) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM redeem_facts WHERE id=?", (fact_id,)).fetchone()
    )


def redeem_fact_for_coupon(
    conn: sqlite3.Connection, coupon_code: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM redeem_facts WHERE coupon_code=? AND fact_kind=? ORDER BY id LIMIT 1",
            (coupon_code, domain.FACT_KIND_REDEEM),
        ).fetchone()
    )


def return_fact_for_redeem(
    conn: sqlite3.Connection, redeem_fact_id: int
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM redeem_facts WHERE compensates_fact_id=? AND fact_kind=? LIMIT 1",
            (redeem_fact_id, domain.FACT_KIND_RETURN),
        ).fetchone()
    )


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        """INSERT INTO redeem_facts(
             coupon_code, campaign_code, amount, business_day, event_id, status,
             fact_kind, compensates_fact_id, compensates_batch_id)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            fields.get("status") or domain.FACT_STATUS_OPEN,
            fields.get("fact_kind") or domain.FACT_KIND_REDEEM,
            fields.get("compensates_fact_id"),
            fields.get("compensates_batch_id"),
        ),
    )
    return int(cur.lastrowid)


def open_facts_for_day(
    conn: sqlite3.Connection, business_day: str, fact_kind: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM redeem_facts
           WHERE business_day=? AND fact_kind=? AND status=?
           ORDER BY id""",
        (business_day, fact_kind, domain.FACT_STATUS_OPEN),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_batched(
    conn: sqlite3.Connection,
    fact_ids: list[int],
    batch_id: int,
    compensates_batch_id: int | None = None,
) -> None:
    for fid in fact_ids:
        if compensates_batch_id is None:
            conn.execute(
                "UPDATE redeem_facts SET status=?, batch_id=? WHERE id=?",
                (domain.FACT_STATUS_SEALED, batch_id, fid),
            )
        else:
            conn.execute(
                """UPDATE redeem_facts
                   SET status=?, batch_id=?, compensates_batch_id=?
                   WHERE id=?""",
                (
                    domain.FACT_STATUS_SEALED,
                    batch_id,
                    compensates_batch_id,
                    fid,
                ),
            )


def facts_for_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE batch_id=? ORDER BY id", (batch_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def day_is_sealed(conn: sqlite3.Connection, business_day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM redeem_batches WHERE business_day=? AND batch_kind=? AND status='sealed' LIMIT 1",
        (business_day, domain.BATCH_KIND_REDEEM),
    ).fetchone()
    return row is not None


def redeem_batch_for_day(
    conn: sqlite3.Connection, business_day: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            """SELECT * FROM redeem_batches
               WHERE business_day=? AND batch_kind=? AND status='sealed'
               ORDER BY id DESC LIMIT 1""",
            (business_day, domain.BATCH_KIND_REDEEM),
        ).fetchone()
    )
