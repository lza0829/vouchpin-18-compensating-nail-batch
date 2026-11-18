from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day, domain.FACT_KIND_REDEEM)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        opens = fact_repo.open_facts_for_day(
            conn, day, domain.FACT_KIND_REDEEM
        )
        total = round(sum(float(f["amount"]) for f in opens), 2)
        return {
            "business_day": day,
            "open_count": len(opens),
            "open_total": total,
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": opens,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        if fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 已有 sealed 核销批")
        opens = fact_repo.open_facts_for_day(
            conn, day, domain.FACT_KIND_REDEEM
        )
        if not opens:
            raise HTTPException(400, "无可钉扎的 open 核销事实")
        total = round(sum(float(f["amount"]) for f in opens), 2)
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=len(opens),
            total_amount=total,
            sealed_at=datetime.now().replace(microsecond=0).isoformat(),
            note=body.get("note") or "",
            batch_kind=domain.BATCH_KIND_REDEEM,
        )
        fact_repo.mark_batched(conn, [int(f["id"]) for f in opens], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "batch_kind": domain.BATCH_KIND_REDEEM,
            "fact_count": len(opens),
            "total_amount": total,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches(
    business_day: str | None = None, batch_kind: str | None = None
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = batch_repo.list_batches(conn, business_day, batch_kind)
        for row in rows:
            row["facts"] = fact_repo.facts_for_batch(conn, int(row["id"]))
        return rows
    finally:
        conn.close()


def batch_detail(batch_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, "批次不存在")
        facts = fact_repo.facts_for_batch(conn, batch_id)
        batch["facts"] = facts
        batch["fact_total"] = round(sum(float(f["amount"]) for f in facts), 2)
        batch["intact"] = (
            int(batch["fact_count"]) == len(facts)
            and abs(round(float(batch["total_amount"]), 2) - batch["fact_total"]) < 1e-9
        )
        if batch["batch_kind"] == domain.BATCH_KIND_COMPENSATING:
            batch["original_batch"] = batch_repo.get_batch(
                conn, int(batch["compensates_batch_id"])
            )
            batch["compensated_batches"] = []
        else:
            batch["original_batch"] = None
            batch["compensated_batches"] = batch_repo.compensating_batches_for_original(
                conn, batch_id
            )
            for comp in batch["compensated_batches"]:
                comp["facts"] = fact_repo.facts_for_batch(conn, int(comp["id"]))
        return batch
    finally:
        conn.close()
