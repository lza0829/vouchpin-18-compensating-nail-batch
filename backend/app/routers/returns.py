from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services import return_service as svc

router = APIRouter(tags=["returns"])


@router.get("/returns")
def returns(business_day: str | None = Query(None)):
    return svc.list_returns(business_day)


@router.get("/returns/preview")
def preview(business_day: str | None = Query(None)):
    return svc.preview(business_day)


@router.post("/returns")
def create_return(body: dict[str, Any]):
    return svc.create_return(body)


@router.post("/returns/seal")
def seal(body: dict[str, Any]):
    return svc.seal(body)
