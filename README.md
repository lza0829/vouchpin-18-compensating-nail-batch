# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 退回补偿 → 批次互证。

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
- 测试: `cd backend && pip install -r requirements-dev.txt && python -m pytest`

## 退回的两种钉扎形态（全局互斥，只贯彻一种）

`settings.return_policy` 只有一个取值，`GET/PUT /api/settings/return-policy` 读写。

| 取值 | 名称 | 退回落点 | 批侧 |
| --- | --- | --- | --- |
| `compensating`（默认） | 独立补偿钉批 | 退回业务日，open 的退回事实 | 单独钉成 `compensating` sealed 批，批头 `compensates_batch_id` 指向原核销批 |
| `event_only` | 仅事件记账 | 退回业务日，`recorded` 非钉事实 | 不产生补偿批；原 sealed 批保持原样，退回只在事件侧展示 |

不变式：
- 退回只能针对**已钉扎**的原核销事实；一笔核销只能退回一次，且整笔冲销（退回金额为负数，绝对值等于原核销额）。
- 原核销批与批内事实**只读**：退回不重算、不改写任何原批数字与笔数。
- 退回事件、补偿事实、补偿批次、批头关联同源：`POST /api/returns` 一次事务里写事件 + 事实，事实带 `compensates_fact_id` / `compensates_batch_id`。
- 一旦存在 `compensating` sealed 批，策略锁定，不允许切回 `event_only`（返回 409）——已钉的补偿凭证不能被另一种策略抹掉。
- 切换策略只重新标注**未钉扎**退回事实的状态（`open` ↔ `recorded`），不改任何 sealed 数据。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings/return-policy` | 当前策略、可选项、是否锁定 |
| PUT | `/api/settings/return-policy` | 切换策略（`{"policy": "compensating"｜"event_only"}`） |
| POST | `/api/returns` | 写入退回（`coupon_code` 或 `redeem_fact_id`，可选 `business_day`/`note`） |
| GET | `/api/returns`、`/api/returns/preview` | 退回事实 / 按原批分组的待钉预览 |
| POST | `/api/returns/seal` | 把退回业务日 open 的退回事实按原批分组钉成补偿批 |
| GET | `/api/batches`、`/api/batches/{id}` | 批次列表 / 详情（含原批与补偿批互链） |
| GET | `/api/reconciliation`、`/api/reconciliation/check` | 互证报告；`/check` 返回逐项核对与 `failed` |
| POST | `/api/events` | 发放/核销/作废；`return` 会被拒绝，要求走 `/api/returns` |

`POST /api/returns` 响应带 `status`（`open`＝补偿策略待钉，`recorded`＝仅事件记账）、`compensates_fact_id`、`compensates_batch_id`。

## 两策略核对

`GET /api/reconciliation/check?business_day=YYYY-MM-DD` 的 `checks[]` 逐项给出 `ok`/`detail`，`consistent` 为总判定：

共用项
- `redeem_batch_intact` 原 sealed 批合计=批内事实合计
- `redeem_event_batch_match` 事件侧核销额=批侧已钉额+未钉 open
- `return_event_fact_same_source` 退回事件与退回事实一一同源
- `return_amount_vs_original` 退回额=原核销额且原批只读

`compensating` 追加
- `compensating_batch_header` 补偿批头指向原批
- `compensating_batch_intact` 补偿批合计=批内退回事实合计
- `return_batch_evidence_complete` 本日退回全部有批侧对账凭证（未钉则为缺口）
- `no_recording_facts_under_compensating` 不出现非钉退回事实

`event_only` 追加
- `event_only_no_compensating_batch` 不存在补偿 sealed 批
- `event_only_return_on_event_side` 退回在事件侧完整可见
- `event_only_no_open_return_facts` 无 open 退回事实

## 数据库

`redeem_facts.fact_kind`（`redeem`/`return`）、`compensates_fact_id`、`compensates_batch_id`；`redeem_batches.batch_kind`、`compensates_batch_id`；`coupon_events.compensates_fact_id`。

启动时自动迁移旧库：旧表 `redeem_facts(coupon_code UNIQUE)` 会一次性重建，改为只对 `fact_kind='redeem'` 生效的唯一部分索引，旧批数字原样保留（见 `backend/app/db.py`）。
