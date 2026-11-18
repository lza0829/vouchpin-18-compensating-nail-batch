<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref([])
const detail = ref(null)
const err = ref('')

async function load() {
  err.value = ''
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
async function open(id) {
  err.value = ''
  try { detail.value = await api.batch(id) } catch (e) { err.value = e.message }
}
function kindLabel(k) {
  return k === 'compensating' ? '补偿批' : '原核销批'
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead>
        <tr>
          <th>批次</th><th>业务日</th><th>类型</th><th>状态</th><th>笔数</th>
          <th>合计</th><th>关联批</th><th>钉扎时刻</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id" class="clickable" @click="open(b.id)">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td>
            <span class="tag" :class="b.batch_kind === 'compensating' ? 'warn' : 'ok'">{{ kindLabel(b.batch_kind) }}</span>
          </td>
          <td>{{ b.status }}</td>
          <td>{{ b.fact_count }}</td>
          <td>{{ b.total_amount }}</td>
          <td>
            <span v-if="b.compensates_batch_id" class="tag warn">→ 原批 #{{ b.compensates_batch_id }}</span>
            <span v-else class="hint">—</span>
          </td>
          <td>{{ b.sealed_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="detail">
    <div class="panel-head">
      <h2>批次 #{{ detail.id }}</h2>
      <span class="tag" :class="detail.batch_kind === 'compensating' ? 'warn' : 'ok'">{{ kindLabel(detail.batch_kind) }}</span>
      <span class="tag" :class="detail.intact ? 'ok' : 'bad'">{{ detail.intact ? '批内一致' : '批内不一致' }}</span>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ detail.business_day }}</div></div>
      <div class="stat"><div class="k">笔数</div><div class="v">{{ detail.fact_count }}</div></div>
      <div class="stat"><div class="k">批头合计</div><div class="v ticket">{{ detail.total_amount }}</div></div>
      <div class="stat"><div class="k">批内事实合计</div><div class="v ticket">{{ detail.fact_total }}</div></div>
    </div>

    <div class="pair" v-if="detail.batch_kind === 'compensating' && detail.original_batch">
      <div class="pair-col">
        <div class="pair-head">原核销批 <span class="tag ok">只读</span></div>
        <p class="pair-line">#{{ detail.original_batch.id }} · {{ detail.original_batch.fact_count }} 笔 · 合计
          <strong>{{ detail.original_batch.total_amount }}</strong></p>
        <p class="hint">原批不经退回改写。</p>
      </div>
      <div class="pair-arrow" aria-hidden="true">←</div>
      <div class="pair-col">
        <div class="pair-head">本补偿批</div>
        <p class="pair-line">#{{ detail.id }} · {{ detail.fact_count }} 笔 · 合计
          <strong>{{ detail.total_amount }}</strong></p>
        <p class="hint">批头 compensates_batch_id = {{ detail.compensates_batch_id }}</p>
      </div>
    </div>

    <div v-if="detail.batch_kind !== 'compensating' && detail.compensated_batches.length">
      <h2>关联补偿批</h2>
      <ul class="plain">
        <li v-for="c in detail.compensated_batches" :key="c.id">
          <span class="tag warn">补偿批 #{{ c.id }}</span>
          · 业务日 {{ c.business_day }} · {{ c.fact_count }} 笔 · 合计 {{ c.total_amount }}
        </li>
      </ul>
    </div>

    <h2>批内事实</h2>
    <table>
      <thead><tr><th>事实ID</th><th>种类</th><th>券码</th><th>金额</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in detail.facts" :key="f.id">
          <td>{{ f.id }}</td>
          <td><span class="tag" :class="f.fact_kind === 'return' ? 'warn' : ''">{{ f.fact_kind }}</span></td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.amount }}</td>
          <td>{{ f.status }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
