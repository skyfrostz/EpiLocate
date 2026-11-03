<template>
  <section class="content-card" aria-label="新算法结果">
    <h2>{{ request.algorithm_mode }} · {{ request.method_mode }}</h2>
    <p role="status">{{ result.source }} · {{ output.execution_status }} · {{ output.algorithm_status }}</p>
    <p v-if="output.diagnostics.precomputed_replay">原结果证据：{{ output.diagnostics.source_evidence_type }}；本次仅回放，新增模型计算为零。</p>
    <p v-if="output.reason">{{ output.reason }}</p>
    <p>{{ request.task.unit === 'SLICE' ? '二维切片任务' : '完整所选 Series 的源病例分类' }} · {{ request.task.definition_id }}</p>
    <p v-if="output.prediction">预测类别：{{ output.prediction.class_label }} · logits {{ output.prediction.logits.join(', ') }}</p>
    <ResearchEvidence v-if="output.diagnostics.research_contract" :result-id="result.result_id" :request="request" :output="output" />
    <p>前向 {{ output.actual_forward }} / 反向 {{ output.actual_backward }} / 更新 {{ output.actual_updates }} · {{ output.runtime_seconds }} 秒</p>
    <p v-if="output.stop_events.length">预算停止记录 {{ output.stop_events.length }} 条；实际退出耗时已保留。</p>
    <label v-if="layers.length">模型证据图层 <select v-model="selected"><option v-for="layer in layers" :key="layer.asset_id" :value="layer.asset_id">{{ layer.evidence_type }}</option></select></label>
    <label><input v-model="visible" type="checkbox" :disabled="!gate.ok || !overlayUrl" /> 显示新算法叠加</label>
    <p role="status">{{ gate.ok ? '原生像素对应通过' : gate.reason }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <CornerstoneSliceViewer v-if="request.input.display_kind === 'DICOM'" :file="dicom" :slice-id="result.slice_id" :slice-width="request.input.native_shape_zyx[2]" :slice-height="request.input.native_shape_zyx[1]" :overlay="viewerOverlay" :overlay-visible="visible" :input-state="dicom ? 'ready' : 'empty'" />
    <div v-else-if="baseUrl" class="research-array-frame" aria-label="研究数组原生预览">
      <img :src="baseUrl" alt="研究数组原生像素预览" />
      <img v-if="visible && gate.ok && overlayUrl" :src="overlayUrl" class="research-array-overlay" alt="有符号贡献或算法支持叠加" />
    </div>
    <p v-else-if="request.input.display_kind === 'RESEARCH_ARRAY'">研究数组预览尚未交付；不经临床 DICOM 上传入口显示。</p>
    <p v-if="layer">{{ layer.evidence_type }} · 原始数值范围 {{ layer.value_min }} 至 {{ layer.value_max }}；图像显示强度不替代原始数值。</p>
    <p>模型解释证据，不是病灶概率或专家标注。拒绝不表示正常；空间未验证及 partial 结果保留诊断，叠加关闭。</p>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ResultRecord } from '../api/types'
import { apiClient } from '../api/client'
import { sessionEpoch, onSessionReset } from '../auth/lifecycle'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'
import ResearchEvidence from './ResearchEvidence.vue'
import { resolveApplicationOverlay } from '../viewer/next-geometry'
import type { ViewerOverlayInput } from '../viewer/geometry'
const props=defineProps<{result: ResultRecord}>()
const request=computed(()=>props.result.application_request!)
const output=computed(()=>props.result.application!)
const layers=computed(()=>output.value.layers.filter(l=>l.layer_kind!=='BASE_IMAGE'))
const selected=ref(''),visible=ref(false),baseUrl=ref<string|null>(null),overlayUrl=ref<string|null>(null)
const displayHash=ref<string|null>(null),dicom=ref<File|null>(null),error=ref<string|null>(null)
let generation=0,controller:AbortController|undefined
const key=()=>`epilocate:next-result:${props.result.result_id}`
const layer=computed(()=>layers.value.find(l=>l.asset_id===selected.value)??null)
const gate=computed(()=>resolveApplicationOverlay(props.result,layer.value,displayHash.value))
const viewerOverlay=computed<ViewerOverlayInput|null>(()=>gate.value.ok && layer.value && overlayUrl.value ? {url:overlayUrl.value,sliceId:props.result.slice_id,layer:layer.value,geometry:gate.value.geometry}:null)
async function hash(blob:Blob) { const bytes=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('') }
function clear() { generation++;controller?.abort();for(const url of [baseUrl.value,overlayUrl.value])if(url)URL.revokeObjectURL(url);baseUrl.value=null;overlayUrl.value=null;dicom.value=null;displayHash.value=null;visible.value=false }
async function asset(id:string,signal:AbortSignal) {
  const descriptor=props.result.assets.find(a=>a.asset_id===id)
  if(!descriptor?.sha256)throw new Error('缺少新算法资产 SHA。')
  const blob=await apiClient.getResultAsset(props.result.result_id,id,signal)
  if(await hash(blob)!==descriptor.sha256)throw new Error('新算法资产 SHA 不一致。')
  return blob
}
async function load() {
  clear();const own=generation,epoch=sessionEpoch.value;controller=new AbortController();const signal=controller.signal;error.value=null
  try {
    const q=request.value
    let source:Blob|null=null
    if(q.input.display_kind==='DICOM') {
      const detail=await apiClient.getCase(q.input.case_id,signal)
      const study=detail.studies.find(s=>s.study_id===q.input.study_id),series=study?.series.find(s=>s.series_id===q.input.series_id)
      const slice=series?.slices.find(s=>s.slice_id===q.input.slice_id)
      if(!slice || slice.width_px!==q.input.native_shape_zyx[2] || slice.height_px!==q.input.native_shape_zyx[1])throw new Error('病例、Series 与原生尺寸不一致。')
      source=await apiClient.getCaseDicom(q.input.case_id,signal)
      if(await hash(source)!==q.input.display_sha256)throw new Error('原图摘要不一致。')
    } else {
      const base=output.value.layers.find(l=>l.layer_kind==='BASE_IMAGE')
      if(base) {
        if(base.display_sha256!==q.input.display_sha256 || base.width!==q.input.native_shape_zyx[2] || base.height!==q.input.native_shape_zyx[1] || base.mapping_qa_sha256!==q.input.mapping_qa_sha256 || base.geometry_ledger_sha256!==q.input.geometry_ledger_sha256)throw new Error('研究数组预览与原生绑定不一致。')
        source=await asset(base.asset_id,signal)
      }
    }
    const overlay=layer.value ? await asset(layer.value.asset_id,signal):null
    if(own!==generation || epoch!==sessionEpoch.value)return
    if(source && q.input.display_kind==='DICOM')dicom.value=new File([source],'authorized-slice.dcm',{type:'application/dicom'})
    else if(source)baseUrl.value=URL.createObjectURL(source)
    displayHash.value=source ? q.input.display_sha256:null
    if(overlay)overlayUrl.value=URL.createObjectURL(overlay)
  } catch(e) {if(own===generation && !signal.aborted)error.value=e instanceof Error?e.message:'新算法证据读取失败。'}
}
watch(()=>props.result,()=>{try {const saved=JSON.parse(sessionStorage.getItem(key())??'null');selected.value=layers.value.some(l=>l.asset_id===saved?.layer)?saved.layer:layers.value[0]?.asset_id??''}catch{selected.value=layers.value[0]?.asset_id??''}void load()}, {immediate:true})
watch(selected,()=>{sessionStorage.setItem(key(),JSON.stringify({layer:selected.value}));void load()})
watch(sessionEpoch,clear)
onSessionReset(()=>{clear();for(const k of Object.keys(sessionStorage))if(k.startsWith('epilocate:next-result:'))sessionStorage.removeItem(k)})
onBeforeUnmount(clear)
</script>
<style scoped>
.research-array-frame{position:relative;width:100%;max-width:640px;line-height:0}
.research-array-frame img{display:block;width:100%;height:auto}
.research-array-frame .research-array-overlay{position:absolute;inset:0;width:100%;height:100%;opacity:.5}
</style>
