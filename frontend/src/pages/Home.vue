<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">核销事实</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销额</div><div class="v ticket">{{ d.redeem_total_today }}</div></div>
      <div class="stat"><div class="k">日已钉扎</div><div class="v">{{ d.day_sealed ? '是' : '否' }}</div></div>
    </div>
    <p class="msg" v-if="!err">票根洋红标出核销侧数字；钉扎后禁止再写入该日核销。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="d">
    <div class="panel-head">
      <h2>退回与补偿 · 今日并列</h2>
      <span class="tag" :class="d.return_policy === 'compensating' ? 'warn' : ''">
        策略：{{ d.return_policy_label }}
      </span>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">退回事件</div><div class="v">{{ d.return_event_count }}</div></div>
      <div class="stat"><div class="k">退回合计</div><div class="v ticket">{{ d.return_total_today }}</div></div>
      <div class="stat">
        <div class="k">{{ d.return_policy === 'compensating' ? '待钉退回' : '非钉退回' }}</div>
        <div class="v">{{ d.return_policy === 'compensating' ? d.open_return_count : d.recorded_return_count }}</div>
      </div>
      <div class="stat"><div class="k">补偿批</div><div class="v">{{ d.compensating_batch_count_today }}</div></div>
      <div class="stat"><div class="k">补偿合计</div><div class="v ticket">{{ d.compensating_total_today }}</div></div>
    </div>

    <div class="pair" v-if="d.redeem_batch_today">
      <div class="pair-col">
        <div class="pair-head">原核销批 <span class="tag ok">只读</span></div>
        <p class="pair-line">#{{ d.redeem_batch_today.id }} · {{ d.redeem_batch_today.fact_count }} 笔 · 合计
          <strong>{{ d.redeem_batch_today.total_amount }}</strong></p>
        <p class="hint">原批数字不因退回重算。</p>
      </div>
      <div class="pair-arrow" aria-hidden="true">→</div>
      <div class="pair-col">
        <div class="pair-head">补偿批 <span class="tag warn">{{ d.return_policy === 'compensating' ? '独立钉扎' : '不产生' }}</span></div>
        <p class="pair-line" v-if="d.compensating_batch_count_today">
          {{ d.compensating_batch_count_today }} 批 · 合计 <strong>{{ d.compensating_total_today }}</strong>
        </p>
        <p class="pair-line" v-else-if="d.return_policy === 'compensating'">
          待钉 {{ d.open_return_count }} 笔 · 合计 <strong>{{ d.return_total_today }}</strong>
        </p>
        <p class="pair-line" v-else>退回仅在事件侧展示。</p>
        <p class="hint">批头 compensates_batch_id 指回原批。</p>
      </div>
    </div>
    <router-link class="link" to="/returns">进入退回补偿 →</router-link>
  </div>
</template>
