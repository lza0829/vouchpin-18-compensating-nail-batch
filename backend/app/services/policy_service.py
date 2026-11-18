from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import batches as batch_repo


def get_policy(conn) -> str:
    value = settings_repo.get(conn, domain.RETURN_POLICY_KEY, "")
    if value in domain.RETURN_POLICIES:
        return value
    return domain.DEFAULT_RETURN_POLICY


def describe(conn) -> dict[str, Any]:
    policy = get_policy(conn)
    meta = domain.POLICY_META[policy]
    sealed_compensating = batch_repo.list_batches(
        conn, batch_kind=domain.BATCH_KIND_COMPENSATING
    )
    return {
        "return_policy": policy,
        "label": meta["label"],
        "summary": meta["summary"],
        "allows_compensating_seal": meta["allows_compensating_seal"],
        "alternatives": [
            {
                "value": value,
                "label": domain.POLICY_META[value]["label"],
                "summary": domain.POLICY_META[value]["summary"],
            }
            for value in domain.RETURN_POLICIES
        ],
        # Mutual exclusion is materialised: once compensating batches exist,
        # switching to event-only would leave batch-side evidence behind.
        "switch_locked": bool(sealed_compensating),
        "sealed_compensating_batch_ids": [int(b["id"]) for b in sealed_compensating],
    }


def get() -> dict[str, Any]:
    conn = connect()
    try:
        return describe(conn)
    finally:
        conn.close()


def set_policy(body: dict[str, Any]) -> dict[str, Any]:
    """Switch the globally enforced return strategy.

    Exactly one strategy is in force.  Unsealed return facts are re-labelled so
    their status matches the newly enforced strategy; sealed compensating
    batches are immutable evidence, so switching to ``event_only`` is refused
    once they exist.
    """
    target = (body.get("policy") or body.get("return_policy") or "").strip()
    if target not in domain.RETURN_POLICIES:
        raise HTTPException(
            400,
            "policy 须为 " + " / ".join(domain.RETURN_POLICIES),
        )
    conn = connect(immediate=True)
    try:
        current = get_policy(conn)
        if target == current:
            result = describe(conn)
            conn.commit()
            return result

        if target == domain.RETURN_POLICY_EVENT_ONLY:
            sealed = batch_repo.list_batches(
                conn, batch_kind=domain.BATCH_KIND_COMPENSATING
            )
            if sealed:
                raise HTTPException(
                    409,
                    "已存在 compensating sealed 批，退回策略不可切回「仅事件记账」；"
                    "原补偿批为只读凭证。",
                )
            conn.execute(
                """UPDATE redeem_facts SET status=?
                   WHERE fact_kind=? AND status=? AND batch_id IS NULL""",
                (
                    domain.FACT_STATUS_RECORDED,
                    domain.FACT_KIND_RETURN,
                    domain.FACT_STATUS_OPEN,
                ),
            )
        else:
            conn.execute(
                """UPDATE redeem_facts SET status=?
                   WHERE fact_kind=? AND status=? AND batch_id IS NULL""",
                (
                    domain.FACT_STATUS_OPEN,
                    domain.FACT_KIND_RETURN,
                    domain.FACT_STATUS_RECORDED,
                ),
            )

        settings_repo.set_(conn, domain.RETURN_POLICY_KEY, target)
        result = describe(conn)
        result["previous_policy"] = current
        conn.commit()
        return result
    finally:
        conn.close()
