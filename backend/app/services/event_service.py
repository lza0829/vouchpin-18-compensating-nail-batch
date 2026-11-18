from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import campaigns as camp_repo


def list_campaigns() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return camp_repo.list_all(conn)
    finally:
        conn.close()


def list_events(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return event_repo.list_events(conn, day)
    finally:
        conn.close()


def add_event(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        et = body.get("event_type")
        if et == domain.EVENT_RETURN:
            # Returns have their own single-source entry point: they must
            # reference the original sealed redeem fact and, under the
            # compensating policy, produce a fact that can be sealed later.
            raise HTTPException(
                400, "退回请走 POST /api/returns，以便与原核销批同源关联"
            )
        if et not in (domain.EVENT_ISSUE, domain.EVENT_REDEEM, domain.EVENT_VOID):
            raise HTTPException(400, "event_type 须为 issue/redeem/void")
        code = (body.get("coupon_code") or "").strip()
        camp = (body.get("campaign_code") or "").strip()
        if not code or not camp:
            raise HTTPException(400, "coupon_code / campaign_code 必填")
        if et == domain.EVENT_REDEEM and fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 核销已钉扎，禁止再写入核销")
        if et == domain.EVENT_REDEEM and fact_repo.redeem_fact_for_coupon(conn, code):
            raise HTTPException(409, f"券码 {code} 已有核销事实")
        amount = float(body.get("amount") or 0)
        if et == domain.EVENT_REDEEM and amount <= 0:
            # default face value from campaign
            camps = {c["code"]: c for c in camp_repo.list_all(conn)}
            if camp in camps:
                amount = float(camps[camp]["face_value"])
        if et == domain.EVENT_REDEEM and amount <= 0:
            raise HTTPException(400, "核销金额须为正数")
        occurred = body.get("occurred_at") or datetime.now().replace(microsecond=0).isoformat()
        eid = event_repo.insert_event(
            conn,
            event_type=et,
            coupon_code=code,
            campaign_code=camp,
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=body.get("note") or "",
        )
        fact_id = None
        if et == domain.EVENT_REDEEM:
            fact_id = fact_repo.insert_fact(
                conn,
                coupon_code=code,
                campaign_code=camp,
                amount=amount,
                business_day=day,
                event_id=eid,
                status=domain.FACT_STATUS_OPEN,
                fact_kind=domain.FACT_KIND_REDEEM,
            )
        conn.commit()
        return {"event_id": eid, "fact_id": fact_id, "business_day": day}
    finally:
        conn.close()
