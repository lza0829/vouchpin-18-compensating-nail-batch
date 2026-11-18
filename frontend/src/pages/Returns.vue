<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const policy = ref(null)
const form = ref({ coupon_code: '', business_day: '' })
const msg = ref('')
const err = ref('')

async function load() {
  err.value = ''
  try {
    preview.value = await api.returnsPreview()
    policy.value = await api.returnPolicy()
    if (!form.value.business_day) form.value.business_day = preview.value.business_day
  } catch (e) { err.value = e.message }
}

async function submit() {
  msg.value = ''; err.value = ''
  try {
    const body = { coupon_code: form.value.coupon_code.trim() }
    if (form.value.business_day) body.business_day = form.value.business_day
    const r = await api.addReturn(body)
    msg.value = `已写入退回事件 #${r.event_id} / 补偿事实 #${r.fact_id} · 关联原批 #${r.compensates_batch_id} · ${r.status}`
    form.value.coupon_code = ''
    await load()
  } catch (e) { err.value = e.message }
}

async function seal() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.sealReturns({})
    msg.value = `已钉扎 ${r.batch_count} 个补偿批 · ${r.fact_count} 笔 · 合计 ${r.total_amount}`
    await load()
  } catch (e) { err.value = e.message }
}

onMounted(load)
</script>
<template>
  <div class="panel" v-if="policy">
    <div class="panel-head">
      <h2>退回策略</h2>
      <span class="tag" :class="policy.return_policy === 'compensating' ? 'warn' : 'ok'">
        {{ policy.label }}
      </span>
    </div>
    <p class="msg">{{ policy.summary }}</p>
    <p class="msg err" v-if="policy.switch_locked">
      已存在补偿 sealed 批（#{{ policy.sealed_compensating_batch_ids.join(', #') }}），策略锁定为独立补偿钉批。
    </p>
    <p class="msg" v-else>策略可切换；切换只影响未钉扎退回事实的标注。</p>
    <router-link class="link" to="/settings">切换策略 →</router-link>
  </div>

  <div class="panel" v-if="preview">
    <div class="grid">
      <div class="stat"><div class="k">退回业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat">
        <div class="k">{{ preview.return_policy === 'compensating' ? '待钉退回' : '非钉退回' }}</div>
        <div class="v ticket">{{ preview.open_count }}</div>
      </div>
      <div class="stat"><div class="k">待钉合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat">
        <div class="k">可补偿钉扎</div>
        <div class="v">{{ preview.allows_compensating_seal ? '是' : '否' }}</div>
      </div>
    </div>
    <div class="row">
      <label>原券码 <input v-model="form.coupon_code" placeholder="已钉核销的券码" /></label>
      <label>退回业务日 <input v-model="form.business_day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="submit">写入退回</button>
      <button type="button" @click="seal" :disabled="!preview.allows_compensating_seal || preview.open_count === 0">
        钉扎补偿批
      </button>
      <button type="button" class="ghost" @click="load">刷新</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="preview">
    <h2>按原批分组的待钉退回</h2>
    <p class="hint" v-if="!preview.groups.length">本日没有 open 的退回事实。</p>
    <table v-for="g in preview.groups" :key="g.compensates_batch_id">
      <thead>
        <tr>
          <th>退回事实</th><th>券码</th><th>金额</th><th>状态</th><th>批内</th>
        </tr>
        <tr class="group-head">
          <td colspan="5">
            原核销批 #{{ g.compensates_batch_id }}
            <span v-if="g.original_batch">
              · 业务日 {{ g.original_batch.business_day }}
              · {{ g.original_batch.fact_count }} 笔 · 合计 {{ g.original_batch.total_amount }}
            </span>
            <span class="tag ok">只读</span>
            <span class="tag warn">补偿 {{ g.fact_count }} 笔 / {{ g.total_amount }}</span>
          </td>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in g.facts" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag" :class="f.status === 'open' ? 'warn' : 'ok'">{{ f.status }}</span></td>
          <td>#{{ f.compensates_batch_id }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
