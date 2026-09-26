<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> RESULT / 分析结果</div>
    <div class="page-heading"><div><h1>结果详情</h1><p class="page-intro">仅显示已完成 Job 的 LIVE_CASE Result。</p></div><a-button :loading="results.loading" @click="results.loadResult(resultId)">重新读取</a-button></div>
    <div class="record-identity"><span>RESULT ID</span><code>{{ resultId }}</code><a-tag :color="result ? 'green' : 'default'">{{ result?.status ?? '未读取' }}</a-tag></div>
    <p v-if="results.error" class="notice notice-error" role="alert">{{ results.error }}</p>
    <p v-if="results.loading" class="notice" role="status">正在读取 Result…</p>
    <template v-if="result">
      <div class="result-grid">
        <div class="content-card">
          <div class="card-heading"><div><h2>单切片分类</h2><p>Prediction · {{ result.slice_id }}</p></div></div>
          <div v-if="result.prediction" class="prediction-content">
            <div class="prediction-label"><span>预测类别</span><strong>{{ result.prediction.class_label }}</strong></div>
            <div class="metric-pair"><div><span>正类概率</span><strong>{{ formatPercent(result.prediction.positive_probability) }}</strong></div><div><span>预测类别置信度</span><strong>{{ formatPercent(result.prediction.predicted_class_confidence) }}</strong></div></div>
            <p class="viewer-note">预测单位：Slice。正类概率与预测类别置信度分别来自服务端。</p>
          </div>
          <div v-else class="empty-state compact"><h3>分类字段不可用</h3><p>此 Result 未提供预测摘要。</p></div>
        </div>
        <div class="content-card">
          <div class="card-heading"><div><h2>模型响应图</h2><p>Heatmap · 不是病灶标注</p></div><a-tag v-if="result.kind === 'OCCLUSION'">{{ selectedScale }} px</a-tag></div>
          <div v-if="result.scale_summaries.length" class="scale-switch" aria-label="遮挡尺度">
            <button v-for="summary in result.scale_summaries" :key="summary.block_size" type="button" :class="{ active: selectedScale === summary.block_size }" @click="selectedScale = summary.block_size">{{ summary.block_size }} px</button>
          </div>
          <div v-if="selectedSummary" class="scale-metrics">
            <span>中位绝对概率变化 <strong>{{ formatPercent(selectedSummary.median_absolute_probability_change) }}</strong></span>
            <span>翻转比例 <strong>{{ formatPercent(selectedSummary.flip_rate) }}</strong></span>
            <span>候选响应 <strong>{{ selectedSummary.candidate_status === 'valid' ? '有效模型响应' : '正响应不足' }}</strong></span>
          </div>
          <div class="heatmap-frame">
            <p v-if="results.assetError || imageError" class="notice notice-error" role="alert">{{ results.assetError ?? imageError }}</p>
            <p v-else-if="results.assetLoading" role="status">正在读取授权图层…</p>
            <img v-else-if="results.assetUrl && selectedSummary?.response_layer && !imageError" :src="results.assetUrl" alt="当前尺度的模型决策响应图，不是病灶标注" @load="checkImage" @error="imageError = '响应图无法解码。'" />
            <p v-else>{{ result.kind === 'PREDICTION' ? '分类结果没有响应图资产。' : '当前尺度没有可显示的响应图。' }}</p>
          </div>
          <p v-if="selectedSummary?.response_layer" class="asset-caption">{{ selectedSummary.response_layer.coordinate_space }} · {{ selectedSummary.response_layer.width }} × {{ selectedSummary.response_layer.height }} px</p>
        </div>
        <div class="content-card model-card">
          <div class="card-heading"><div><h2>模型与算法版本</h2><p>服务端 provenance</p></div></div>
          <div class="result-meta">
            <div><span>模型 ID</span><code>{{ result.model_id }}</code></div>
            <div><span>模型版本</span><code>{{ result.model_version }}</code></div>
            <div><span>预处理版本</span><code>{{ result.preprocessing_version }}</code></div>
            <div><span>协议版本</span><code>{{ result.protocol_id }}</code></div>
            <div><span>数据来源</span><strong>{{ result.source }}</strong></div>
            <div><span>任务 ID</span><RouterLink :to="`/jobs/${encodeURIComponent(result.job_id)}`">{{ result.job_id }}</RouterLink></div>
          </div>
        </div>
      </div>
      <p class="result-disclaimer">响应图表示模型决策响应，不作为真实病灶标注或临床诊断。算法输入与原始 CT 坐标不可直接叠加。</p>
    </template>
    <div v-else-if="!results.loading" class="content-card"><div class="empty-state compact"><h3>结果尚不可显示</h3><p>请确认 Result ID、认证状态和 API 连接，然后重新读取。</p></div></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { formatPercent } from '../format'
import { useResultStore } from '../stores/results'

const route = useRoute()
const results = useResultStore()
const resultId = computed(() => String(route.params.id ?? ''))
const result = computed(() => results.current?.result_id === resultId.value ? results.current : null)
const selectedScale = ref<16 | 32 | 64>(16)
const selectedSummary = computed(() => result.value?.scale_summaries.find(item => item.block_size === selectedScale.value) ?? null)
const imageError = ref<string | null>(null)

watch(resultId, id => { void results.loadResult(id) }, { immediate: true })
watch(result, value => { if (value?.scale_summaries.length) selectedScale.value = value.scale_summaries[0]!.block_size })
watch([result, selectedScale], () => {
  imageError.value = null
  void results.loadAsset(selectedSummary.value?.response_layer ?? null)
})
onBeforeUnmount(() => results.clear())

function checkImage(event: Event) {
  const image = event.target as HTMLImageElement
  const layer = selectedSummary.value?.response_layer
  if (!layer || image.naturalWidth !== layer.width || image.naturalHeight !== layer.height) {
    imageError.value = '响应图尺寸与结果元数据不一致，已停止显示。'
  }
}
</script>
