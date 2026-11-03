<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { CaseSummary } from '../api/types'
import { inputStatus, shortId } from '../domain/clinical'
import { formatDate } from '../format'
import EpStatus from './EpStatus.vue'
withDefaults(defineProps<{ items: CaseSummary[]; expires?: boolean }>(), { expires:false })
</script>
<template>
  <div class="table-scroll" tabindex="0" role="region" aria-label="病例记录表，可横向滚动">
    <table class="clinical-table"><thead><tr><th scope="col">匿名病例</th><th scope="col">输入状态</th><th scope="col" class="optional-column">分析状态</th><th scope="col" class="optional-column">创建时间</th><th v-if="expires" scope="col" class="optional-column">输入可用期</th><th scope="col">操作</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.case_id">
        <td><RouterLink :to="`/cases/${encodeURIComponent(item.case_id)}`" class="case-link" :aria-label="`打开病例 ${item.case_id}`">{{ shortId(item.case_id) }}</RouterLink><details class="identity-detail"><summary>查看完整标识</summary><code>{{ item.case_id }}</code><span class="cell-sub">匿名上下文：{{ item.patient_id }}</span></details></td>
        <td><EpStatus v-bind="inputStatus(item.status)" /></td><td class="optional-column"><span class="muted">未查询</span></td><td class="optional-column">{{ formatDate(item.created_at) }}</td><td v-if="expires" class="optional-column">{{ formatDate(item.input_expires_at) }}</td><td><RouterLink :to="`/cases/${encodeURIComponent(item.case_id)}`" :aria-label="`继续病例 ${item.case_id}`">打开 →</RouterLink></td>
      </tr></tbody>
    </table>
  </div>
</template>
