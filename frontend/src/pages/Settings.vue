<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const day = ref('')
const policy = ref(null)
const msg = ref('')
const err = ref('')
async function load() {
  err.value = ''
  try {
    const r = await api.getDay()
    day.value = r.business_day
    policy.value = await api.returnPolicy()
  } catch (e) { err.value = e.message }
}
async function save() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setDay(day.value)
    msg.value = `业务日已设为 ${r.business_day}`
  } catch (e) { err.value = e.message }
}
async function choose(value) {
  msg.value = ''; err.value = ''
  if (policy.value && policy.value.return_policy === value) return
  try {
    const r = await api.setReturnPolicy(value)
    msg.value = `退回策略已设为「${r.label}」`
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>业务日 <input v-model="day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="save">保存</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="policy">
    <div class="panel-head">
      <h2>退回钉扎形态（全局互斥，只贯彻一种）</h2>
      <span class="tag" :class="policy.switch_locked ? 'bad' : 'ok'">
        {{ policy.switch_locked ? '已锁定' : '可切换' }}
      </span>
    </div>
    <div class="choices">
      <button
        v-for="c in policy.alternatives"
        :key="c.value"
        type="button"
        class="choice"
        :class="{ on: policy.return_policy === c.value }"
        :disabled="policy.return_policy === c.value"
        @click="choose(c.value)"
      >
        <strong>{{ c.label }}</strong>
        <small>{{ c.summary }}</small>
        <em v-if="policy.return_policy === c.value">当前策略</em>
      </button>
    </div>
    <p class="hint" v-if="policy.switch_locked">
      已存在补偿 sealed 批（#{{ policy.sealed_compensating_batch_ids.join(', #') }}）。
      它们是只读凭证，因此不允许切回「仅事件记账」。
    </p>
    <p class="hint" v-else>
      两条策略互斥；切换只重新标注未钉扎的退回事实状态，已 sealed 的批一律不改。
    </p>
  </div>
</template>
