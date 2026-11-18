from __future__ import annotations

# Single source of truth for the domain vocabulary shared by repositories,
# services and the reconciliation report.

# redeem_facts.fact_kind
FACT_KIND_REDEEM = "redeem"
FACT_KIND_RETURN = "return"

# coupon_events.event_type
EVENT_ISSUE = "issue"
EVENT_REDEEM = "redeem"
EVENT_VOID = "void"
EVENT_RETURN = "return"
EVENT_TYPES = (EVENT_ISSUE, EVENT_REDEEM, EVENT_VOID, EVENT_RETURN)

# redeem_facts.status
FACT_STATUS_OPEN = "open"          # eligible for a batch
FACT_STATUS_SEALED = "sealed"      # belongs to a batch
FACT_STATUS_RECORDED = "recorded"  # non-batched bookkeeping fact (event-only policy)

# redeem_batches.batch_kind
BATCH_KIND_REDEEM = "redeem"
BATCH_KIND_COMPENSATING = "compensating"

# settings key + allowed values.  These two strategies are globally mutually
# exclusive: exactly one of them is in force at any point in time.
RETURN_POLICY_KEY = "return_policy"
RETURN_POLICY_COMPENSATING = "compensating"
RETURN_POLICY_EVENT_ONLY = "event_only"
RETURN_POLICIES = (RETURN_POLICY_COMPENSATING, RETURN_POLICY_EVENT_ONLY)
DEFAULT_RETURN_POLICY = RETURN_POLICY_COMPENSATING

POLICY_META = {
    RETURN_POLICY_COMPENSATING: {
        "label": "独立补偿钉批",
        "summary": "退回落到退回业务日，可在该日把 open 的退回事实单独钉扎为 compensating sealed 批，批头指向原核销批；原批数字不改。",
        "allows_compensating_seal": True,
    },
    RETURN_POLICY_EVENT_ONLY: {
        "label": "仅事件记账",
        "summary": "退回只写事件与非钉事实，不允许对退回做 sealed 钉扎；互证报告在事件侧展示退回，批侧保持原 sealed。",
        "allows_compensating_seal": False,
    },
}
