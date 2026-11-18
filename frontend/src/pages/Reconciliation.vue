<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rep = ref(null)
const err = ref('')

async function load() {
  err.value = ''
  try { rep.value = await api.reconciliation() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel" v-if="rep">
    <div class="panel-head">
      <h2>互证报告 · {{ rep.business_day }}</h2>
      <span class="tag" :class="rep.return_policy === 'compensating' ? 'warn' : 'ok'">{{ rep.policy_label }}</span>
      <span class="tag" :class="rep.consistent ? 'ok' : 'bad'">{{ rep.consistent ? '互证一致' : '存在缺口' }}</span>
    </div>

    <div class="pair">
      <div class="pair-col">
        <div class="pair-head">事件侧</div>
        <p class="pair-line">核销 {{ rep.event_side.redeem_event_count }} 笔 · 合计 <strong>{{ rep.event_side.redeem_event_total }}</strong></p>
        <p class="pair-line">退回 {{ rep.event_side.return_event_count }} 笔 · 合计 <strong class="ticket-text">{{ rep.event_side.return_event_total }}</strong></p>
        <p class="hint" v-if="rep.return_policy === 'event_only'">退回的对账凭证在本侧展示。</p>
      </div>
      <div class="pair-arrow" aria-hidden="true">⇄</div>
      <div class="pair-col">
        <div class="pair-head">批侧</div>
        <p class="pair-line">原 sealed 批 {{ rep.batch_side.redeem_batches.length }} 个 · 合计
          <strong>{{ rep.batch_side.sealed_redeem_total }}</strong>（{{ rep.batch_side.sealed_redeem_fact_count }} 笔）</p>
        <p class="pair-line">
          compensating 批 {{ rep.batch_side.compensating_batches.length }} 个 · 合计
          <strong class="ticket-text">{{ rep.batch_side.sealed_compensating_total }}</strong>
        </p>
        <p class="hint">原批只读；补偿批并列展示。</p>
      </div>
    </div>

    <h2>核对项（{{ rep.checks.length }}）</h2>
    <table>
      <thead><tr><th>结果</th><th>核对项</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="c in rep.checks" :key="c.key">
          <td><span class="tag" :class="c.ok ? 'ok' : 'bad'">{{ c.ok ? '通过' : '缺口' }}</span></td>
          <td>{{ c.label }}</td>
          <td>{{ c.detail }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="rep">
    <h2>原批 ↔ 补偿批关联</h2>
    <p class="hint" v-if="!rep.return_side.links.length">本日无退回事实。</p>
    <table v-else>
      <thead>
        <tr>
          <th>退回事实</th><th>券码</th><th>金额</th><th>退回状态</th>
          <th>原核销批</th><th>补偿批</th><th>原批完好</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="l in rep.return_side.links" :key="l.return_fact_id">
          <td>#{{ l.return_fact_id }}</td>
          <td>{{ l.coupon_code }}</td>
          <td>{{ l.amount }}</td>
          <td><span class="tag" :class="l.batch_state === 'sealed' ? 'ok' : 'warn'">{{ l.batch_state }}</span></td>
          <td>
            #{{ l.original_batch_id }}
            <span class="hint">({{ l.original_batch_day }} · {{ l.original_batch_total }})</span>
          </td>
          <td>
            <span v-if="l.compensating_batch_id" class="tag warn">补偿批 #{{ l.compensating_batch_id }}</span>
            <span v-else class="hint">未钉扎</span>
          </td>
          <td><span class="tag" :class="l.original_batch_intact ? 'ok' : 'bad'">{{ l.original_batch_intact ? '是' : '否' }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
