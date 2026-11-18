from __future__ import annotations

from typing import Any

from app import domain
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.services import policy_service


def _sum(rows: list[dict[str, Any]]) -> float:
    return round(sum(float(r["amount"]) for r in rows), 2)


def _check(key: str, label: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "ok": bool(ok), "detail": detail}


def _batch_view(batch: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    fact_total = _sum(facts)
    return {
        "batch_id": int(batch["id"]),
        "business_day": batch["business_day"],
        "batch_kind": batch["batch_kind"],
        "status": batch["status"],
        "fact_count": int(batch["fact_count"]),
        "total_amount": round(float(batch["total_amount"]), 2),
        "sealed_at": batch["sealed_at"],
        "note": batch["note"],
        "compensates_batch_id": batch["compensates_batch_id"],
        "fact_total": fact_total,
        "intact": int(batch["fact_count"]) == len(facts)
        and abs(round(float(batch["total_amount"]), 2) - fact_total) < 1e-9,
    }


def _links(
    conn, return_facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair every return fact with the read-only original batch it compensates."""
    links: list[dict[str, Any]] = []
    for fact in return_facts:
        original_fact = fact_repo.get_fact(conn, int(fact["compensates_fact_id"]))
        original_batch = batch_repo.get_batch(conn, int(fact["compensates_batch_id"]))
        original_batch_facts = (
            fact_repo.facts_for_batch(conn, int(original_batch["id"]))
            if original_batch
            else []
        )
        compensating_batch = (
            batch_repo.get_batch(conn, int(fact["batch_id"]))
            if fact["batch_id"]
            else None
        )
        original_sealed = bool(
            original_batch
            and original_batch["status"] == "sealed"
            and original_batch["batch_kind"] == domain.BATCH_KIND_REDEEM
            and original_fact
            and original_fact["status"] == domain.FACT_STATUS_SEALED
            and int(original_fact["batch_id"]) == int(original_batch["id"])
        )
        amount_matches_original = bool(
            original_fact
            and abs(abs(float(fact["amount"])) - abs(float(original_fact["amount"])))
            < 1e-9
        )
        if fact["status"] == domain.FACT_STATUS_SEALED:
            batch_state = "sealed"
        elif fact["status"] == domain.FACT_STATUS_OPEN:
            batch_state = "pending"
        else:
            batch_state = "not_batched"
        links.append(
            {
                "return_fact_id": int(fact["id"]),
                "coupon_code": fact["coupon_code"],
                "business_day": fact["business_day"],
                "amount": round(float(fact["amount"]), 2),
                "status": fact["status"],
                "batch_state": batch_state,
                "original_fact_id": int(fact["compensates_fact_id"]),
                "original_fact_status": original_fact["status"] if original_fact else None,
                "original_fact_amount": round(float(original_fact["amount"]), 2)
                if original_fact
                else None,
                "original_batch_id": int(fact["compensates_batch_id"]),
                "original_batch_day": original_batch["business_day"]
                if original_batch
                else None,
                "original_batch_total": round(float(original_batch["total_amount"]), 2)
                if original_batch
                else None,
                "original_batch_fact_count": int(original_batch["fact_count"])
                if original_batch
                else None,
                "original_batch_intact": bool(
                    original_batch
                    and _batch_view(original_batch, original_batch_facts)["intact"]
                ),
                "original_sealed": original_sealed,
                "amount_matches_original": amount_matches_original,
                "compensating_batch_id": int(compensating_batch["id"])
                if compensating_batch
                else None,
                "compensating_batch_day": compensating_batch["business_day"]
                if compensating_batch
                else None,
                "compensating_batch_compensates": int(
                    compensating_batch["compensates_batch_id"]
                )
                if compensating_batch and compensating_batch["compensates_batch_id"]
                else None,
            }
        )
    return links


def report(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        policy = policy_service.get_policy(conn)

        return_events = event_repo.list_events(
            conn, day, domain.EVENT_RETURN
        )
        redeem_events = event_repo.list_events(conn, day, domain.EVENT_REDEEM)

        redeem_batches = batch_repo.list_batches(
            conn, day, domain.BATCH_KIND_REDEEM
        )
        compensating_batches = batch_repo.list_batches(
            conn, day, domain.BATCH_KIND_COMPENSATING
        )
        return_facts = fact_repo.list_facts(conn, day, domain.FACT_KIND_RETURN)

        redeem_facts_day = fact_repo.list_facts(conn, day, domain.FACT_KIND_REDEEM)
        sealed_redeem = [
            f for f in redeem_facts_day if f["status"] == domain.FACT_STATUS_SEALED
        ]
        open_redeem = [
            f for f in redeem_facts_day if f["status"] == domain.FACT_STATUS_OPEN
        ]

        redeem_batch_views = [
            _batch_view(b, fact_repo.facts_for_batch(conn, int(b["id"])))
            for b in redeem_batches
        ]
        compensating_batch_views = [
            _batch_view(b, fact_repo.facts_for_batch(conn, int(b["id"])))
            for b in compensating_batches
        ]

        links = _links(conn, return_facts)
        open_returns = [
            f for f in return_facts if f["status"] == domain.FACT_STATUS_OPEN
        ]
        sealed_returns = [
            f for f in return_facts if f["status"] == domain.FACT_STATUS_SEALED
        ]
        recorded_returns = [
            f for f in return_facts if f["status"] == domain.FACT_STATUS_RECORDED
        ]

        # --- reconciliation checks, strategy specific -------------------
        checks: list[dict[str, Any]] = []

        checks.append(
            _check(
                "redeem_batch_intact",
                "原核销批合计=批内事实合计",
                all(b["intact"] for b in redeem_batch_views),
                "原 sealed 批只读；笔数与合计须与批内事实一致。"
                if redeem_batch_views
                else "本日无原 sealed 批。",
            )
        )

        redeem_event_ids = {int(e["id"]) for e in redeem_events}
        sealed_event_ids = {int(f["event_id"]) for f in sealed_redeem}
        unsealed_redeem_events = [
            e for e in redeem_events if int(e["id"]) not in sealed_event_ids
        ]
        checks.append(
            _check(
                "redeem_event_batch_match",
                "事件侧核销额=批侧已钉额（未钉部分单列 open）",
                round(_sum(redeem_events), 2)
                == round(_sum(sealed_redeem) + _sum(open_redeem), 2)
                and redeem_event_ids == {
                    int(f["event_id"]) for f in redeem_facts_day
                },
                f"事件 {len(redeem_events)} 笔 / 已钉 {len(sealed_redeem)} 笔 / "
                f"待钉 {len(open_redeem)} 笔，未钉事件 {len(unsealed_redeem_events)} 笔。",
            )
        )

        event_links = {
            int(e["compensates_fact_id"])
            for e in return_events
            if e["compensates_fact_id"] is not None
        }
        fact_links = {int(f["compensates_fact_id"]) for f in return_facts}
        checks.append(
            _check(
                "return_event_fact_same_source",
                "退回事件与退回事实一一同源",
                len(return_events) == len(return_facts) and event_links == fact_links,
                f"退回事件 {len(return_events)} 笔 / 退回事实 {len(return_facts)} 笔，"
                f"关联原核销事实 {len(event_links)} 个。",
            )
        )

        return_amount_ok = all(
            link["amount_matches_original"]
            and link["original_sealed"]
            and link["original_batch_intact"]
            for link in links
        )
        checks.append(
            _check(
                "return_amount_vs_original",
                "退回额=原核销额且原批只读",
                return_amount_ok,
                "补偿按整笔冲销，退回额等于原核销事实额；原批合计与笔数未改。"
                if links
                else "本日无退回事实。",
            )
        )

        if policy == domain.RETURN_POLICY_COMPENSATING:
            pending = [link for link in links if link["batch_state"] == "pending"]
            sealed_links = [link for link in links if link["batch_state"] == "sealed"]
            link_ok = all(
                link["compensating_batch_compensates"]
                == link["original_batch_id"]
                for link in sealed_links
            )
            checks.append(
                _check(
                    "compensating_batch_header",
                    "补偿批头 compensates_batch_id 指向原批",
                    link_ok,
                    f"已钉补偿事实 {len(sealed_links)} 笔，"
                    f"待钉 {len(pending)} 笔。",
                )
            )
            checks.append(
                _check(
                    "compensating_batch_intact",
                    "补偿批合计=批内退回事实合计",
                    all(b["intact"] for b in compensating_batch_views),
                    "补偿批只含退回事实，但不改写原 sealed 批。"
                    if compensating_batch_views
                    else "本日尚无补偿 sealed 批。",
                )
            )
            checks.append(
                _check(
                    "return_batch_evidence_complete",
                    "本日退回全部有批侧对账凭证",
                    not pending,
                    "每笔退回事实均已落入 compensating sealed 批。"
                    if not pending
                    else f"{len(pending)} 笔退回事实仍为 open，缺少批侧凭证。",
                )
            )
            checks.append(
                _check(
                    "no_recording_facts_under_compensating",
                    "补偿策略下不出现非钉退回事实",
                    not recorded_returns,
                    "非钉事实仅属「仅事件记账」策略。"
                    if not recorded_returns
                    else f"{len(recorded_returns)} 笔退回事实为非钉状态，策略与数据不一致。",
                )
            )
        else:  # event-only
            checks.append(
                _check(
                    "event_only_no_compensating_batch",
                    "事件记账策略下无补偿 sealed 批",
                    not compensating_batch_views,
                    "批侧保持原 sealed；退回只在事件侧展示。"
                    if not compensating_batch_views
                    else "存在 compensating 批，违反全局互斥策略。",
                )
            )
            checks.append(
                _check(
                    "event_only_return_on_event_side",
                    "退回在事件侧完整可见",
                    len(return_events) == len(return_facts),
                    f"退回事件 {len(return_events)} 笔，事件侧即退回的对账凭证。",
                )
            )
            checks.append(
                _check(
                    "event_only_no_open_return_facts",
                    "非钉退回事实不会被钉扎",
                    not open_returns,
                    f"非钉(recorded) {len(recorded_returns)} 笔；sealed 退回 {len(sealed_returns)} 笔。",
                )
            )

        consistent = all(c["ok"] for c in checks)

        if policy == domain.RETURN_POLICY_COMPENSATING:
            evidence = {
                "mode": "compensating_batches",
                "area": "batch_side",
                # Evidence is only present once returns actually sit in a
                # compensating sealed batch; an open return is a gap.
                "batch_side_return_evidence": not open_returns and bool(return_facts),
                "uncompensated_count": len(open_returns),
                "uncompensated_total": _sum(open_returns),
                "note": "退回落到退回业务日，须单独钉扎为 compensating sealed 批；"
                "原批数字不改，总览并列展示原批与补偿批。",
            }
        else:
            evidence = {
                "mode": "event_only",
                "area": "event_side",
                "batch_side_return_evidence": False,
                "uncompensated_count": 0,
                "uncompensated_total": 0.0,
                "note": "退回只写事件（与非钉事实），不对退回做 sealed 钉扎；"
                "互证报告以事件侧展示退回，批侧保持原 sealed。",
            }

        return {
            "business_day": day,
            "return_policy": policy,
            "policy_label": domain.POLICY_META[policy]["label"],
            "event_side": {
                "redeem_event_count": len(redeem_events),
                "redeem_event_total": _sum(redeem_events),
                "return_event_count": len(return_events),
                "return_event_total": _sum(return_events),
                "return_events": return_events,
            },
            "batch_side": {
                "redeem_batches": redeem_batch_views,
                "sealed_redeem_total": round(
                    sum(b["total_amount"] for b in redeem_batch_views), 2
                ),
                "sealed_redeem_fact_count": sum(
                    b["fact_count"] for b in redeem_batch_views
                ),
                "compensating_batches": compensating_batch_views,
                "sealed_compensating_total": round(
                    sum(b["total_amount"] for b in compensating_batch_views), 2
                ),
                "open_redeem_fact_count": len(open_redeem),
                "open_redeem_fact_total": _sum(open_redeem),
            },
            "return_side": {
                "return_fact_count": len(return_facts),
                "return_fact_total": _sum(return_facts),
                "open_count": len(open_returns),
                "open_total": _sum(open_returns),
                "sealed_count": len(sealed_returns),
                "sealed_total": _sum(sealed_returns),
                "recorded_count": len(recorded_returns),
                "recorded_total": _sum(recorded_returns),
                "links": links,
            },
            "evidence": evidence,
            "checks": checks,
            "consistent": consistent,
        }
    finally:
        conn.close()
