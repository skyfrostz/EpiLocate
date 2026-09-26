<template>
  <div class="cornerstone-viewer">
    <div v-if="file" ref="viewportElement" class="cornerstone-viewport" aria-label="单切片 DICOM 查看器" />
    <div v-else class="viewer-placeholder"><span class="viewer-corner corner-tl"/><span class="viewer-corner corner-tr"/><span class="viewer-corner corner-bl"/><span class="viewer-corner corner-br"/><span class="viewer-cross"/><p>当前无法读取原始 DICOM</p><small>病例输入可能已过期，或 API 暂时不可用。</small></div>
    <p v-if="loading" class="viewer-note" role="status">正在解码本地 DICOM…</p>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="file && !loading && !error" class="viewer-note">单切片 DICOM 已从本次上传或授权 API 恢复。</p>
    <p v-if="overlay && !overlayCompatible(overlay, sliceId, sliceWidth, sliceHeight)" class="viewer-note">图层与当前 Slice 或坐标空间不一致，已禁用叠加。</p>
    <p v-else-if="overlay" class="viewer-note">图层空间元数据已匹配；画布映射和实际叠加留待 Viewer 后续阶段。</p>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Types } from '@cornerstonejs/core'
import { overlayCompatible, type ViewerOverlayInput } from './geometry'

let loaderInitialized = false

const props = defineProps<{
  file: File | null
  sliceId: string | null
  sliceWidth: number | null
  sliceHeight: number | null
  overlay?: ViewerOverlayInput | null
}>()
const viewportElement = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let cleanup: (() => void) | undefined
let generation = 0

watch(() => props.file, async file => {
  generation++
  cleanup?.()
  cleanup = undefined
  error.value = null
  if (!file) return
  const ownGeneration = generation
  loading.value = true
  await nextTick()
  if (!viewportElement.value || ownGeneration !== generation) return
  try {
    const core = await import('@cornerstonejs/core')
    const dicom = await import('@cornerstonejs/dicom-image-loader')
    if (ownGeneration !== generation) return
    if (!loaderInitialized) {
      core.init()
      dicom.init({ maxWebWorkers: 2 })
      loaderInitialized = true
    }
    const imageId = dicom.wadouri.fileManager.add(file)
    const fileIndex = Number(imageId.split(':')[1])
    const engine = new core.RenderingEngine(`epilocate-viewer-${crypto.randomUUID()}`)
    const viewportId = 'single-slice'
    const element = viewportElement.value
    engine.enableElement({ viewportId, type: core.Enums.ViewportType.STACK, element })
    const observer = new ResizeObserver(() => engine.resize())
    observer.observe(element)
    cleanup = () => { observer.disconnect(); engine.destroy(); dicom.wadouri.fileManager.remove(fileIndex) }
    const viewport = engine.getViewport<Types.IStackViewport>(viewportId)
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    try {
      await Promise.race([
        viewport.setStack([imageId]),
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => reject(new Error('DICOM decode timed out')), 15000)
        }),
      ])
    } finally {
      if (timeoutId) clearTimeout(timeoutId)
    }
    if (ownGeneration !== generation) return
    viewport.render()
  } catch {
    if (ownGeneration === generation) error.value = 'DICOM 无法显示，请确认文件格式与浏览器图形能力。'
    cleanup?.()
    cleanup = undefined
  } finally {
    if (ownGeneration === generation) loading.value = false
  }
}, { immediate: true })

onBeforeUnmount(() => { generation++; cleanup?.() })
</script>
