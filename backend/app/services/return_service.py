from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.services import policy_service


def _day(conn, body: dict[str, Any]) -> str:
    return (body.get("business_day") or settings_repo.get(conn, "business_day")).strip()


def _resolve_original(
    conn, body: dict[str, Any]
) -> dict[str, Any]:
    fact_id = body.get("redeem_fact_id") or body.get("fact_id")
    if fact_id not in (None, ""):
        fact = fact_repo.get_fact(conn, int(fact_id))
    else:
        code = (body.get("coupon_code") or "").strip()
        if not code:
            raise HTTPException(400, "coupon_code 或 redeem_fact_id 必填")
        fact = fact_repo.redeem_fact_for_coupon(conn, code)
    if not fact:
        raise HTTPException(404, "原核销事实不存在")
    if fact["fact_kind"] != domain.FACT_KIND_REDEEM:
        raise HTTPException(400, "只能对核销事实发起退回")
    if not fact["batch_id"] or fact["status"] != domain.FACT_STATUS_SEALED:
        raise HTTPException(
            409, f"原核销事实 #{fact['id']} 尚未钉扎，退回仅针对已钉核销"
        )
    original_batch = batch_repo.get_batch(conn, int(fact["batch_id"]))
    if (
        not original_batch
        or original_batch["status"] != "sealed"
        or original_batch["batch_kind"] != domain.BATCH_KIND_REDEEM
    ):
        raise HTTPException(409, "原核销批不可用，无法建立补偿关联")
    return fact


def create_return(body: dict[str, Any]) -> dict[str, Any]:
    """Write the return event and its compensating fact as one source.

    The original redeem fact and its sealed batch are read-only here: nothing
    about them is recomputed or rewritten.  Under the compensating policy the
    new return fact is ``open`` so it can be sealed into a compensating batch
    on the return business day; under event-only it is a ``recorded``
    non-nailed fact.
    """
    conn = connect(immediate=True)
    try:
        policy = policy_service.get_policy(conn)
        day = _day(conn, body)
        if len(day) != 10:
            raise HTTPException(400, "business_day 格式 YYYY-MM-DD")

        original = _resolve_original(conn, body)
        if day < original["business_day"]:
            raise HTTPException(
                400, "退回业务日不得早于原核销业务日"
            )
        if fact_repo.return_fact_for_redeem(conn, int(original["id"])):
            raise HTTPException(
                409, f"券码 {original['coupon_code']} 已退回，原核销事实不可重复退回"
            )

        # A return is a negative fact: it offsets the original amount.  The
        # original fact and its sealed batch are never rewritten.
        original_amount = round(float(original["amount"]), 2)
        amount = round(-original_amount, 2)
        if body.get("amount") not in (None, ""):
            given = float(body["amount"])
            if abs(abs(given) - original_amount) > 1e-9:
                raise HTTPException(
                    400,
                    f"退回金额须等于原核销金额 {original_amount}（补偿按整笔冲销）",
                )

        occurred = (
            body.get("occurred_at")
            or datetime.now().replace(microsecond=0).isoformat()
        )
        eid = event_repo.insert_event(
            conn,
            event_type=domain.EVENT_RETURN,
            coupon_code=original["coupon_code"],
            campaign_code=original["campaign_code"],
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=body.get("note") or "",
            compensates_fact_id=int(original["id"]),
        )
        status = (
            domain.FACT_STATUS_OPEN
            if policy == domain.RETURN_POLICY_COMPENSATING
            else domain.FACT_STATUS_RECORDED
        )
        try:
            fid = fact_repo.insert_fact(
                conn,
                coupon_code=original["coupon_code"],
                campaign_code=original["campaign_code"],
                amount=amount,
                business_day=day,
                event_id=eid,
                status=status,
                fact_kind=domain.FACT_KIND_RETURN,
                compensates_fact_id=int(original["id"]),
                compensates_batch_id=int(original["batch_id"]),
            )
        except Exception as e:  # partial unique index: one return per redeem
            raise HTTPException(409, "退回事实写入失败（可能已退回）") from e

        conn.commit()
        return {
            "event_id": eid,
            "fact_id": fid,
            "business_day": day,
            "amount": amount,
            "original_amount": original_amount,
            "status": status,
            "return_policy": policy,
            "compensates_fact_id": int(original["id"]),
            "compensates_batch_id": int(original["batch_id"]),
            "original_business_day": original["business_day"],
        }
    finally:
        conn.close()


def list_returns(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day, domain.FACT_KIND_RETURN)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        policy = policy_service.get_policy(conn)
        opens = fact_repo.open_facts_for_day(conn, day, domain.FACT_KIND_RETURN)
        groups: dict[int, dict[str, Any]] = {}
        for fact in opens:
            obid = fact["compensates_batch_id"]
            group = groups.setdefault(
                int(obid),
                {
                    "compensates_batch_id": int(obid),
                    "original_batch": batch_repo.get_batch(conn, int(obid)),
                    "facts": [],
                    "fact_count": 0,
                    "total_amount": 0.0,
                },
            )
            group["facts"].append(fact)
            group["fact_count"] += 1
            group["total_amount"] = round(
                group["total_amount"] + float(fact["amount"]), 2
            )
        return {
            "business_day": day,
            "return_policy": policy,
            "allows_compensating_seal": policy
            == domain.RETURN_POLICY_COMPENSATING,
            "open_count": len(opens),
            "open_total": round(sum(float(f["amount"]) for f in opens), 2),
            "groups": list(groups.values()),
            "facts": opens,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    """Seal the return day's open return facts into compensating batches.

    One batch per original redeem batch, so every batch header can carry a
    single ``compensates_batch_id``.  The original batches are only read.
    """
    conn = connect(immediate=True)
    try:
        policy = policy_service.get_policy(conn)
        if policy != domain.RETURN_POLICY_COMPENSATING:
            raise HTTPException(
                409,
                "当前退回策略为「仅事件记账」，不允许对退回做 sealed 钉扎；"
                "如要改为独立补偿钉批，请先在策略设置中切换。",
            )
        day = _day(conn, body)
        opens = fact_repo.open_facts_for_day(conn, day, domain.FACT_KIND_RETURN)
        if not opens:
            raise HTTPException(400, "无可钉扎的 open 退回事实")

        groups: dict[int, list[dict[str, Any]]] = {}
        for fact in opens:
            groups.setdefault(int(fact["compensates_batch_id"]), []).append(fact)

        sealed_at = datetime.now().replace(microsecond=0).isoformat()
        created: list[dict[str, Any]] = []
        for original_batch_id, facts in groups.items():
            original_batch = batch_repo.get_batch(conn, original_batch_id)
            if (
                not original_batch
                or original_batch["status"] != "sealed"
                or original_batch["batch_kind"] != domain.BATCH_KIND_REDEEM
            ):
                raise HTTPException(
                    409, f"原核销批 #{original_batch_id} 不可用，拒绝补偿钉扎"
                )
            total = round(sum(float(f["amount"]) for f in facts), 2)
            bid = batch_repo.create_batch(
                conn,
                business_day=day,
                status="sealed",
                fact_count=len(facts),
                total_amount=total,
                sealed_at=sealed_at,
                note=body.get("note") or "",
                batch_kind=domain.BATCH_KIND_COMPENSATING,
                compensates_batch_id=original_batch_id,
            )
            fact_repo.mark_batched(
                conn,
                [int(f["id"]) for f in facts],
                bid,
                compensates_batch_id=original_batch_id,
            )
            created.append(
                {
                    "batch_id": bid,
                    "business_day": day,
                    "batch_kind": domain.BATCH_KIND_COMPENSATING,
                    "compensates_batch_id": original_batch_id,
                    "fact_count": len(facts),
                    "total_amount": total,
                    "status": "sealed",
                }
            )
        conn.commit()
        return {
            "business_day": day,
            "batch_count": len(created),
            "fact_count": sum(b["fact_count"] for b in created),
            "total_amount": round(sum(b["total_amount"] for b in created), 2),
            "batches": created,
        }
    finally:
        conn.close()
