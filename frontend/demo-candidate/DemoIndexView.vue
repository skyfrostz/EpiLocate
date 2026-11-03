<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { demoRows } from '../demo-history'
</script>
<template>
  <div class="view">
    <div class="page-heading"><div><h1>历史结果查看</h1><p class="page-intro">固定三张单切片 · 64 px 输入遮挡响应 · 本次查看不运行模型</p></div></div>
    <p class="notice">显示历史计算结果。分类任务为 RICORD 来源代理标签：1A=1、1B=0；模型响应不是病灶概率。仅查看单 SOP，未提供整例或三维诊断。</p>
    <section class="content-card"><ul>
      <li v-for="row in demoRows" :key="row.result_id"><RouterLink :to="`/results/${encodeURIComponent(row.result_id)}`">单切片 {{ row.case_index }} · 历史 64 px 响应</RouterLink></li>
    </ul></section>
  </div>
</template>
