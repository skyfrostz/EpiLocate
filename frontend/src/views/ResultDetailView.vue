<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> RESULT / 分析结果</div>
    <div class="page-heading"><div><h1>结果详情</h1><p class="page-intro">分类、响应图和版本信息以已完成的 Result 为准。</p></div><span class="heading-subtle">/results/:id</span></div>
    <div class="record-identity"><span>RESULT ID</span><code>{{ resultId }}</code><a-tag>未读取</a-tag></div>
    <div class="result-grid">
      <div class="content-card"><div class="card-heading"><div><h2>分类结果</h2><p>Prediction</p></div></div><div class="empty-state compact"><h3>暂无已读取分类</h3><p>正类概率与预测类别置信度将分别显示。</p></div></div>
      <div class="content-card"><div class="card-heading"><div><h2>响应图</h2><p>Heatmap</p></div></div><div class="heatmap-placeholder"><span class="heatmap-grid"/><span>尚未读取图层资产</span></div></div>
      <div class="content-card model-card"><div class="card-heading"><div><h2>模型与来源</h2><p>Model version / provenance</p></div></div><div class="model-placeholder"><span>MODEL VERSION</span><strong>—</strong><span>SOURCE</span><strong>—</strong></div></div>
    </div>
    <p class="result-disclaimer">响应图表示模型决策响应，不作为真实病灶标注或临床诊断。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const resultId = computed(() => String(route.params.id ?? ''))
</script>
