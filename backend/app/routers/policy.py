from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services import policy_service as svc

router = APIRouter(tags=["settings"])


@router.get("/settings/return-policy")
def get_policy():
    return svc.get()


@router.put("/settings/return-policy")
def put_policy(body: dict[str, Any]):
    return svc.set_policy(body)
