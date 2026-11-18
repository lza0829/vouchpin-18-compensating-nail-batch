from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services import reconciliation_service as svc

router = APIRouter(tags=["reconciliation"])


@router.get("/reconciliation")
def reconciliation(business_day: str | None = Query(None)):
    return svc.report(business_day)


@router.get("/reconciliation/check")
def check(business_day: str | None = Query(None)):
    """Full report plus a compact verdict, used by both strategies' checks."""
    report = svc.report(business_day)
    report["failed"] = [c for c in report["checks"] if not c["ok"]]
    return report


@router.post("/reconciliation")  # convenience alias for clients that POST
def reconciliation_post(body: dict[str, Any] | None = None):
    return svc.report((body or {}).get("business_day"))
