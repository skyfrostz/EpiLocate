<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>
<template><div class="view"><section class="content-card empty-state"><span class="muted">404</span><h1>页面不存在</h1><p>链接可能已更改。可以返回概览，或从病例中心继续工作。</p><div class="context-links"><RouterLink to="/">返回概览</RouterLink><RouterLink to="/cases">病例中心</RouterLink></div></section></div></template>
