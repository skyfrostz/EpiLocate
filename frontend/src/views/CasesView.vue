<template>
  <div class="view">
    <div class="page-heading"><div><h1>病例中心</h1><p class="page-intro">当前账号的匿名病例 · 从输入到结果。</p></div><a-button id="new-case" type="primary" :loading="creating" @click="createCase">创建匿名病例</a-button></div>
    <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
    <section class="content-card" aria-labelledby="cases-title">
      <div class="card-heading"><div><h2 id="cases-title">病例记录 <span class="muted">{{ cases.hasLoaded ? `· 已加载 ${cases.items.length} 例` : '' }}</span></h2><p>输入可用不代表分析完成；分析状态在病例与任务中核对。</p></div><a-button :loading="cases.loading" @click="cases.loadCases()">刷新</a-button></div>
      <CaseCollection :items="cases.items" expires>
        <label>显示密度<select v-model="displayDensity" @change="saveDisplay"><option value="compact">紧凑</option><option value="standard">标准</option><option value="comfortable">舒适</option></select></label>
      </CaseCollection>
      <p v-if="cases.error" class="notice notice-error" role="alert">{{ cases.error }}</p>
      <div v-if="cases.loading && !cases.hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
      <div v-else-if="cases.hasLoaded && !cases.items.length && !cases.error" class="empty-state compact"><h3>暂无病例</h3><p>创建匿名病例后，在病例工作区上传单切片 DICOM。</p></div>
      <div v-else-if="!cases.items.length" class="empty-state compact"><h3>病例列表未加载</h3><p>请检查网络或认证状态后重试。</p></div>
      <div class="table-actions"><span>仅当前已加载记录</span><a-button v-if="cases.nextCursor" :loading="cases.loading" @click="cases.loadCases(undefined, true)">加载更多</a-button></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useCaseStore } from '../stores/cases'
import CaseCollection from '../components/CaseCollection.vue'
import { displayDensity, saveDisplay } from '../design/preferences'
import { useCreateCase } from '../composables/useCreateCase'
const cases = useCaseStore()
const { creating, createError, createCase } = useCreateCase()
onMounted(() => { void cases.loadCases() })
</script>
