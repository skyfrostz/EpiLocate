<template>
  <div class="view dashboard-view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> OVERVIEW / 总览</div>
    <div class="dashboard-heading">
      <div>
        <h1>影像研究工作台</h1>
        <p class="page-intro">从匿名病例进入影像、任务和结果。界面只呈现服务端已确认的数据。</p>
      </div>
      <div class="heading-badge"><span class="badge-crosshair" aria-hidden="true" /> SINGLE SLICE · CT</div>
    </div>

    <div class="dashboard-grid">
      <section class="primary-panel">
        <div class="panel-topline"><span>工作入口</span><span>01 / 03</span></div>
        <div class="scan-illustration" aria-hidden="true">
          <div class="scan-frame"><div class="scan-crosshair" /><div class="scan-focus" /></div>
          <span class="scan-coord scan-coord-a">AXIAL</span>
          <span class="scan-coord scan-coord-b">X · Y</span>
        </div>
        <div class="primary-panel-copy">
          <span class="panel-kicker">CASE FIRST</span>
          <h2>先找到病例，再阅读分析。</h2>
          <p>病例、任务和结果保持独立记录。打开病例后，可沿匿名 ID 追踪后续工作。</p>
          <a-button type="primary" size="large" @click="router.push('/cases')">进入病例中心 <span aria-hidden="true">↗</span></a-button>
        </div>
      </section>

      <section class="workflow-panel" aria-label="工作流程">
        <div class="section-small-heading"><span>工作流程</span><span>TRACEABLE FLOW</span></div>
        <div class="workflow-step"><span class="step-number">01</span><div><h3>病例准备</h3><p>查看已授权的匿名病例与影像输入。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-step"><span class="step-number">02</span><div><h3>任务执行</h3><p>按 Job ID 查询创建、排队、运行及终态。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-step"><span class="step-number">03</span><div><h3>结果阅读</h3><p>分类、模型版本和响应图以 Result 为准。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-note"><span class="note-mark">i</span><p>当前阶段建立页面与接口边界。这里不显示未经 API 读取的数量或诊断结论。</p></div>
      </section>
    </div>

    <section class="scope-strip" aria-label="当前范围">
      <div><span>影像范围</span><strong>单切片 CT</strong></div>
      <div><span>数据来源</span><strong>服务端真实记录</strong></div>
      <div><span>解释边界</span><strong>模型响应 ≠ 病灶标注</strong></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>
