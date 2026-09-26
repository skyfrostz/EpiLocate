<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> CASE RECORD / 病例记录</div>
    <div class="page-heading"><div><h1>病例详情</h1><p class="page-intro">病例、Study、Series 与 Slice 的层级视图。</p></div><RouterLink class="back-link" to="/cases">← 返回病例中心</RouterLink></div>
    <div class="record-identity"><span>CASE ID</span><code>{{ caseId }}</code><a-tag>未读取</a-tag></div>
    <div class="detail-grid">
      <div class="content-card"><div class="card-heading"><div><h2>影像结构</h2><p>Study / Series / Slice</p></div></div><div class="empty-state compact"><span class="empty-symbol" aria-hidden="true">⌁</span><h3>影像层级尚未加载</h3><p>读取病例详情后才显示实际切片。</p></div></div>
      <div class="content-card"><div class="card-heading"><div><h2>影像浏览</h2><p>预留医学影像查看区域</p></div></div><div class="viewer-placeholder"><span class="viewer-corner corner-tl"/><span class="viewer-corner corner-tr"/><span class="viewer-corner corner-bl"/><span class="viewer-corner corner-br"/><span class="viewer-cross"/><p>尚无可显示影像</p><small>Viewer 接口将在后续阶段接入</small></div></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
const route = useRoute()
const caseId = computed(() => String(route.params.id ?? ''))
</script>
