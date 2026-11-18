from __future__ import annotations

from fastapi.testclient import TestClient


def day_of(client: TestClient) -> str:
    return client.get("/api/settings/day").json()["business_day"]


def seal_redeem_day(client: TestClient) -> dict:
    resp = client.post("/api/redeem/seal", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def checks(client: TestClient, day: str | None = None) -> dict:
    url = "/api/reconciliation/check" + (f"?business_day={day}" if day else "")
    resp = client.get(url)
    assert resp.status_code == 200, resp.text
    return resp.json()


def by_key(report: dict) -> dict:
    return {c["key"]: c for c in report["checks"]}


def test_return_requires_sealed_redeem(client: TestClient):
    resp = client.post("/api/returns", json={"coupon_code": "C-0901"})
    assert resp.status_code == 409
    assert "尚未钉扎" in resp.json()["detail"]

    resp = client.post("/api/returns", json={"coupon_code": "NOPE"})
    assert resp.status_code == 404


def test_compensating_policy_seals_separate_batch(client: TestClient):
    day = day_of(client)
    original = seal_redeem_day(client)

    resp = client.post(
        "/api/returns", json={"coupon_code": "C-1001", "business_day": day}
    )
    assert resp.status_code == 200, resp.text
    ret = resp.json()
    assert ret["status"] == "open"
    assert ret["amount"] == -10.0
    assert ret["compensates_batch_id"] == original["batch_id"]

    # Before the compensating seal, batch-side evidence is missing.
    report = checks(client)
    assert report["consistent"] is False
    assert by_key(report)["return_batch_evidence_complete"]["ok"] is False

    resp = client.post("/api/returns/seal", json={})
    assert resp.status_code == 200, resp.text
    sealed = resp.json()
    assert sealed["batch_count"] == 1
    assert sealed["total_amount"] == -10.0
    assert sealed["batches"][0]["compensates_batch_id"] == original["batch_id"]

    report = checks(client)
    assert report["consistent"] is True, report["failed"]
    assert report["evidence"]["area"] == "batch_side"

    # Original batch is read-only: numbers identical, and it links forward.
    batch = client.get(f"/api/batches/{original['batch_id']}").json()
    assert batch["total_amount"] == 30.0
    assert batch["fact_count"] == 2
    assert batch["intact"] is True
    assert [b["id"] for b in batch["compensated_batches"]] == [
        sealed["batches"][0]["batch_id"]
    ]


def test_return_constraints(client: TestClient):
    day = day_of(client)
    seal_redeem_day(client)

    assert (
        client.post(
            "/api/returns", json={"coupon_code": "C-1001", "amount": 5}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/returns",
            json={"coupon_code": "C-1001", "business_day": "2000-01-01"},
        ).status_code
        == 400
    )
    assert (
        client.post("/api/returns", json={"coupon_code": "C-1001"}).status_code == 200
    )
    # one return per redeem fact
    assert (
        client.post("/api/returns", json={"coupon_code": "C-1001"}).status_code == 409
    )
    # a return never flows through the generic event endpoint
    assert (
        client.post(
            "/api/events",
            json={
                "event_type": "return",
                "coupon_code": "C-1002",
                "campaign_code": "VIP20",
            },
        ).status_code
        == 400
    )
    assert day


def test_groups_compensating_batches_by_original_batch(client: TestClient):
    seal_redeem_day(client)
    # Original facts C-1001 and C-1002 belong to the same batch here; create a
    # second original batch on another day to exercise grouping.
    resp = client.put("/api/settings/day", json={"business_day": "2026-01-05"})
    assert resp.status_code == 200
    issued = client.post(
        "/api/events",
        json={
            "event_type": "redeem",
            "coupon_code": "C-7777",
            "campaign_code": "NEW10",
            "business_day": "2026-01-05",
        },
    )
    assert issued.status_code == 200, issued.text
    second = seal_redeem_day(client)

    client.put("/api/settings/day", json={"business_day": "2026-12-01"})
    for code in ("C-1001", "C-7777"):
        assert client.post("/api/returns", json={"coupon_code": code}).status_code == 200

    sealed = client.post("/api/returns/seal", json={}).json()
    assert sealed["batch_count"] == 2
    targets = sorted(b["compensates_batch_id"] for b in sealed["batches"])
    assert targets == sorted([1, second["batch_id"]])

    report = checks(client, "2026-12-01")
    assert report["consistent"] is True, report["failed"]
    assert len(report["checks"]) >= 1


def test_event_only_policy_keeps_returns_on_event_side(client: TestClient):
    seal_redeem_day(client)
    resp = client.put("/api/settings/return-policy", json={"policy": "event_only"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_policy"] == "event_only"

    ret = client.post("/api/returns", json={"coupon_code": "C-1001"}).json()
    assert ret["status"] == "recorded"

    report = checks(client)
    assert report["consistent"] is True, report["failed"]
    assert report["evidence"]["area"] == "event_side"
    assert report["batch_side"]["compensating_batches"] == []

    resp = client.post("/api/returns/seal", json={})
    assert resp.status_code == 409
    assert "仅事件记账" in resp.json()["detail"]

    # switching back re-opens the non-nailed return fact
    client.put("/api/settings/return-policy", json={"policy": "compensating"})
    facts = client.get("/api/returns").json()
    assert facts[0]["status"] == "open"
    assert client.post("/api/returns/seal", json={}).status_code == 200
    assert checks(client)["consistent"] is True


def test_policy_switch_locked_after_compensating_seal(client: TestClient):
    seal_redeem_day(client)
    client.post("/api/returns", json={"coupon_code": "C-1001"})
    client.post("/api/returns/seal", json={})

    resp = client.put("/api/settings/return-policy", json={"policy": "event_only"})
    assert resp.status_code == 409
    policy = client.get("/api/settings/return-policy").json()
    assert policy["return_policy"] == "compensating"
    assert policy["switch_locked"] is True


def test_redeem_sealed_day_still_accepts_separate_compensating_batch(
    client: TestClient,
):
    day = day_of(client)
    seal_redeem_day(client)
    client.post("/api/returns", json={"coupon_code": "C-1002", "business_day": day})
    assert client.post("/api/returns/seal", json={}).status_code == 200

    # Redeem side stays closed for the day; the return day gains its own batch.
    resp = client.post(
        "/api/events",
        json={
            "event_type": "redeem",
            "coupon_code": "C-2222",
            "campaign_code": "TEA5",
            "business_day": day,
        },
    )
    assert resp.status_code == 409
    batches = client.get("/api/batches").json()
    kinds = sorted(b["batch_kind"] for b in batches)
    assert kinds == ["compensating", "redeem"]
