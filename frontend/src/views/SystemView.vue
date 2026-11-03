<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { apiClient } from '../api/client'
import { errorText } from '../api/errors'
import { auth } from '../auth/session'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import { formatDate } from '../format'
import EpStatus from '../components/EpStatus.vue'
const loading = ref(false), observedAt = ref<number | null>(null), error = ref<string | null>(null)
let generation = 0, controller: AbortController | undefined
function reset() { generation++; controller?.abort(); loading.value=false; observedAt.value=null; error.value=null }
watch(sessionEpoch, reset, {flush:'sync'}); onBeforeUnmount(reset)
async function check() {
  const ownGeneration = ++generation, epoch = sessionEpoch.value
  controller?.abort(); const abort = controller = new AbortController()
  loading.value = true; error.value = null
  try {
    await apiClient.listCases(undefined, 1, abort.signal)
    if (ownGeneration === generation && isSessionCurrent(epoch)) observedAt.value = Date.now()
  } catch (cause) { if (ownGeneration === generation && isSessionCurrent(epoch)) error.value = errorText(cause) }
  finally { if (ownGeneration === generation && isSessionCurrent(epoch)) loading.value = false }
}
</script>
<template>
  <div class="view"><div class="page-heading"><div><h1>系统状态</h1><p class="page-intro">区分可访问的服务与尚未接入的运行指标。</p></div><a-button :loading="loading" @click="check">检查病例 API</a-button></div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }} 查询失败不能确定组件离线。</p>
    <section class="content-card"><div class="card-heading"><div><h2>当前可见服务</h2><p>仅当前浏览器请求证据，未查询内部节点。</p></div></div>
      <div class="availability-row"><div>Session Gateway<small>当前登录身份已验证 · Cookie 会话</small></div><EpStatus :label="auth.username ? '身份已确认' : '未登录'" tone="neutral" /></div>
      <div class="availability-row"><div>Backend 病例 API<small>{{ observedAt ? `最近响应：${formatDate(new Date(observedAt).toISOString())}` : '尚未主动查询' }}</small></div><EpStatus :label="loading ? '查询中' : error ? '读取失败' : observedAt ? '曾响应' : '未查询'" :tone="error ? 'warning' : 'neutral'" /></div>
      <div v-for="item in [{name:'GPU', note:'利用率与推理设备遥测'}, {name:'在线 Worker', note:'心跳与任务领取能力'}, {name:'Storage', note:'对象存储健康与容量'}, {name:'Queue', note:'授权范围队列深度'}]" :key="item.name" class="availability-row"><div>{{ item.name }}<small>{{ item.note }}</small></div><EpStatus label="未接入" tone="neutral" /></div>
    </section>
    <div class="notice"><h3>当前能力范围</h3><p>浏览器会话尚未提供角色与系统详情权限。当前使用统一基础视图；管理员详情需由服务端授权后启用。</p><p>病例 API 响应只证明该次请求成功，不能证明 GPU、Worker 或存储健康。研究训练任务与在线推理服务分别管理。</p></div>
  </div>
</template>
