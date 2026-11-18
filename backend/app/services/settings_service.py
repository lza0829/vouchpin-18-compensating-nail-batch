from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.db import connect
from app.repositories import settings as settings_repo
from app.services import policy_service


def get_day() -> dict[str, Any]:
    conn = connect()
    try:
        return {
            "business_day": settings_repo.get(conn, "business_day"),
            "return_policy": policy_service.get_policy(conn),
        }
    finally:
        conn.close()


def set_day(body: dict[str, Any]) -> dict[str, Any]:
    day = (body.get("business_day") or "").strip()
    if len(day) != 10:
        raise HTTPException(400, "business_day 格式 YYYY-MM-DD")
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, "business_day", day)
        conn.commit()
        return {
            "business_day": day,
            "return_policy": policy_service.get_policy(conn),
        }
    finally:
        conn.close()
