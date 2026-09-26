<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> CASE CENTER / 病例中心</div>
    <div class="page-heading"><div><h1>病例中心</h1><p class="page-intro">病例仅显示匿名标识。列表数据将在连接 Case API 后呈现。</p></div><span class="heading-subtle">/cases</span></div>
    <div class="content-card">
      <div class="card-heading"><div><h2>病例列表</h2><p>按创建时间查看本人可访问的病例。</p></div><a-tag color="blue">API v2</a-tag></div>
      <div class="table-head" aria-hidden="true"><span>CASE ID</span><span>状态</span><span>创建时间</span><span>输入可用期</span></div>
      <div class="empty-state"><span class="empty-symbol" aria-hidden="true">⌁</span><h3>尚未加载病例记录</h3><p>当前页面没有从服务端读取列表，因此不会把未加载状态显示为“零病例”。</p></div>
    </div>
  </div>
</template>
