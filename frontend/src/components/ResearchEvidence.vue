<template>
  <section aria-label="版本化研究证据">
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-else-if="target">
      <p>解释类别：{{ request.task.class_labels[target.explanation_target.resolved_class] }} · 预测类别：{{ output.prediction?.class_label }} · {{ target.explanation_target.policy }}</p>
      <p>优化：全部 logits 一致性；描述响应：固定类别 logit margin。两者分别记录。</p>
      <p v-if="target.source_label">来源标签：{{ target.source_label.label }} · 范围 {{ target.source_label.scope }}；不代表切片或病灶真值。</p>
      <p v-else>来源标签未知。</p>
    </template>
    <template v-else-if="f0">
      <p>F0 · 4×4×4 有符号粗贡献 · 来源分类分数未经校准</p>
      <p>解释类别：{{ request.task.class_labels[f0.explanation_target] }} · 来源标签：{{ f0.source_label.label }}（SOURCE_GROUP）</p>
      <p>空间均值 {{ mean }} + 有效 bias {{ bias }} = logit {{ rebuilt }}；原始 logit {{ output.prediction?.logits[f0.explanation_target] }}</p>
      <label>粗网格 z 层 <select :value="slice" @change="persistSlice"><option v-for="z in 4" :key="z" :value="z-1">{{ z-1 }}</option></select></label>
      <table aria-label="F0 原始有符号数值">
        <caption>原始 4×4 网格，无平滑或 ReLU；不是原生分割或病灶概率</caption>
        <tbody><tr v-for="(row,y) in grid" :key="y"><td v-for="(value,x) in row" :key="x" :class="value < 0 ? 'negative' : value > 0 ? 'positive' : ''">{{ value.toPrecision(5) }}</td></tr></tbody>
      </table>
      <p>正负贡献均保留；名义 native/LPS 格点和变换摘要保存在结果中。粗格点不代表精细病灶边界。</p>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ApplicationRequest, ApplicationResult } from '../api/next-algorithm'
const props=defineProps<{ resultId: string; request: ApplicationRequest; output: ApplicationResult }>()
interface Target { predicted_class: number; prediction_scope: string; contract_sha256: string; class_labels: string[]; explanation_target: {policy: string; declared_class: number; resolved_class: number}; source_label: {label: string; scope: string} | null; loss_definition: {optimization_objective: string; response_metric: string} }
interface F0 { schema: string; explanation_target: number; predicted_class: number; raw_logits: number[]; effective_bias: number[]; signed_values: number[][][][]; source_label: {label: string; scope: string} }
const slice=ref(0)
const sliceKey=()=>`epilocate:next-result:${props.resultId}:research-slice`
onMounted(()=>{const raw=sessionStorage.getItem(sliceKey());if(raw===null)return;const saved=Number(raw);if(Number.isInteger(saved)&&saved>=0&&saved<4)slice.value=saved})
function persistSlice(event: Event) {
  const selected=Number((event.currentTarget as HTMLSelectElement).value)
  if(Number.isInteger(selected)&&selected>=0&&selected<4) {
    slice.value=selected
    sessionStorage.setItem(sliceKey(),String(selected))
  }
}
const candidateTarget=computed(()=>props.output.diagnostics.target_contract as Target | null | undefined)
const candidateF0=computed(()=>props.output.diagnostics.f0 as F0 | undefined)
const error=computed(()=>{
  const t=candidateTarget.value, f=candidateF0.value, p=props.output.prediction, q=props.request
  if(t) {
    if(!p || t.contract_sha256!=='d852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c' || t.prediction_scope!=='SLICE' || t.predicted_class!==p.predicted_class || JSON.stringify(t.class_labels)!==JSON.stringify(q.task.class_labels) || t.explanation_target?.declared_class!==q.task.target_class || t.explanation_target?.resolved_class!==q.task.target_class || !['DECLARED_FIXED','ORIGINAL_ARGMAX_FIXED'].includes(t.explanation_target?.policy) || (t.explanation_target.policy==='ORIGINAL_ARGMAX_FIXED' && t.predicted_class!==q.task.target_class) || t.loss_definition?.optimization_objective!=='ALL_LOGITS' || t.loss_definition?.response_metric!=='FIXED_TARGET_LOGIT_MARGIN')return '解释目标契约不一致，研究证据显示已关闭。'
  }
  if(f) {
    if(!p || f.schema!=='EPI_NEXT_F0_CONSUMPTION_V1' || f.explanation_target!==q.task.target_class || f.predicted_class!==p.predicted_class || JSON.stringify(f.raw_logits)!==JSON.stringify(p.logits) || f.source_label?.scope!=='SOURCE_GROUP' || !Array.isArray(f.effective_bias) || f.effective_bias.length!==2 || f.effective_bias.some(v=>!Number.isFinite(v)) || !Array.isArray(f.signed_values) || f.signed_values.length!==2 || f.signed_values.some(c=>!Array.isArray(c) || c.length!==4 || c.some(z=>!Array.isArray(z) || z.length!==4 || z.some(row=>!Array.isArray(row) || row.length!==4 || row.some(v=>!Number.isFinite(v))))))return 'F0 数值或版本绑定不一致，粗图显示已关闭。'
    for(let c=0;c<2;c++) {const rebuilt=f.signed_values[c]!.flat(2).reduce((a,b)=>a+b,0)/64+f.effective_bias[c]!;if(Math.abs(rebuilt-p.logits[c]!)>1e-10+1e-12*Math.abs(p.logits[c]!))return 'F0 logit 恒等式不一致，粗图显示已关闭。'}
  }
  return null
})
const target=computed(()=>error.value?null:candidateTarget.value)
const f0=computed(()=>error.value?null:candidateF0.value)
const grid=computed(()=>f0.value?.signed_values[f0.value.explanation_target]?.[slice.value]??[])
const mean=computed(()=>f0.value?f0.value.signed_values[f0.value.explanation_target]!.flat(2).reduce((a,b)=>a+b,0)/64:0)
const bias=computed(()=>f0.value?.effective_bias[f0.value.explanation_target]??0)
const rebuilt=computed(()=>mean.value+bias.value)
</script>
<style scoped>
table{border-collapse:collapse}td{padding:.4rem;border:1px solid #ddd;font-variant-numeric:tabular-nums}.negative{background:#eaf0ff}.positive{background:#ffece9}
</style>
