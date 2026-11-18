from __future__ import annotations

from typing import Any

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo
from app.services import policy_service


def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        day = settings_repo.get(conn, "business_day")
        policy = policy_service.get_policy(conn)
        facts = fact_repo.list_facts(conn, day, domain.FACT_KIND_REDEEM)
        open_n = sum(1 for f in facts if f["status"] == domain.FACT_STATUS_OPEN)
        sealed_n = sum(1 for f in facts if f["status"] == domain.FACT_STATUS_SEALED)
        total = round(sum(float(f["amount"]) for f in facts), 2)
        events = event_repo.list_events(conn, day)
        returns = fact_repo.list_facts(conn, day, domain.FACT_KIND_RETURN)
        return_events = event_repo.list_events(conn, day, domain.EVENT_RETURN)
        return_opens = [f for f in returns if f["status"] == domain.FACT_STATUS_OPEN]
        return_recorded = [
            f for f in returns if f["status"] == domain.FACT_STATUS_RECORDED
        ]
        return_sealed = [f for f in returns if f["status"] == domain.FACT_STATUS_SEALED]

        redeem_batches = batch_repo.list_batches(
            conn, day, domain.BATCH_KIND_REDEEM
        )
        compensating_batches = batch_repo.list_batches(
            conn, day, domain.BATCH_KIND_COMPENSATING
        )
        all_batches = batch_repo.list_batches(conn)
        return {
            "business_day": day,
            "event_count": len(events),
            "fact_count": len(facts),
            "open_fact_count": open_n,
            "sealed_fact_count": sealed_n,
            "redeem_total_today": total,
            "batch_count": len(all_batches),
            "day_sealed": fact_repo.day_is_sealed(conn, day),
            "return_policy": policy,
            "return_policy_label": domain.POLICY_META[policy]["label"],
            "return_event_count": len(return_events),
            "return_fact_count": len(returns),
            "return_total_today": round(
                sum(float(f["amount"]) for f in returns), 2
            ),
            "open_return_count": len(return_opens),
            "recorded_return_count": len(return_recorded),
            "sealed_return_count": len(return_sealed),
            "sealed_return_total": round(
                sum(float(f["amount"]) for f in return_sealed), 2
            ),
            "redeem_batch_today": redeem_batches[0] if redeem_batches else None,
            "compensating_batch_count_today": len(compensating_batches),
            "compensating_total_today": round(
                sum(float(b["total_amount"]) for b in compensating_batches), 2
            ),
        }
    finally:
        conn.close()
