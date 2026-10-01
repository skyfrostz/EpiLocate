<template>
  <div class="cornerstone-viewer">
    <div v-if="file" class="cornerstone-stage">
      <div ref="viewportElement" class="cornerstone-viewport" aria-label="单切片 DICOM 查看器" />
      <canvas ref="overlayCanvas" class="cornerstone-overlay" aria-label="模型响应叠加图层" />
    </div>
    <div v-else class="viewer-placeholder"><span class="viewer-corner corner-tl"/><span class="viewer-corner corner-tr"/><span class="viewer-corner corner-bl"/><span class="viewer-corner corner-br"/><span class="viewer-cross"/><p :role="inputState === 'error' ? 'alert' : 'status'">{{ placeholderTitle }}</p><small v-if="inputMessage">{{ inputMessage }}</small><button v-if="inputState === 'error'" class="recovery-action" type="button" @click="emit('retry')">重试读取影像</button></div>
    <div v-if="ready" class="viewer-controls" aria-label="影像视图控制">
      <button type="button" aria-label="放大 CT" @click="zoom(1.25)">＋</button>
      <button type="button" aria-label="缩小 CT" @click="zoom(0.8)">－</button>
      <button type="button" @click="resetView">重置视图</button>
      <span>拖动平移 · 滚轮缩放</span>
    </div>
    <p v-if="loading" class="viewer-note" role="status">正在解码 DICOM…</p>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <button v-if="error && file" class="recovery-action" type="button" @click="decodeAttempt++">重试解码</button>
    <p v-if="overlayError" class="notice notice-error" role="alert">{{ overlayError }}</p>
    <p v-if="ready && !loading && !error" class="viewer-note">单切片 DICOM 已恢复。支持平移、缩放和重置；当前未提供窗宽窗位工具。</p>
    <p v-if="overlay && !overlayCompatible(overlay, sliceId, sliceWidth, sliceHeight)" class="viewer-note">图层与当前 Slice 或已核验几何不一致，已禁用叠加。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Types } from '@cornerstonejs/core'
import { canvasAffineFromCorners, overlayCompatible, rawEdgeToWorld, type Point, type ViewerCameraState, type ViewerOverlayInput } from './geometry'

let loaderInitialized = false
const props = withDefaults(defineProps<{
  file: File | null
  sliceId: string | null
  sliceWidth: number | null
  sliceHeight: number | null
  overlay?: ViewerOverlayInput | null
  overlayVisible?: boolean
  overlayOpacity?: number
  initialView?: ViewerCameraState | null
  inputState?: 'empty' | 'loading' | 'ready' | 'expired' | 'error'
  inputMessage?: string | null
}>(), { overlay: null, overlayVisible: true, overlayOpacity: 0.5, initialView: null, inputState: 'empty', inputMessage: null })
const emit = defineEmits<{ cameraChanged: [state: ViewerCameraState]; retry: [] }>()
const decodeAttempt = ref(0)
const placeholderTitle = computed(() => ({ empty: '尚未读取原始 DICOM', loading: '正在读取原始 DICOM…', ready: '正在准备影像…', expired: '原始影像已过期', error: '原始影像读取失败' })[props.inputState])
const viewportElement = ref<HTMLDivElement | null>(null)
const overlayCanvas = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const ready = ref(false)
const error = ref<string | null>(null)
const overlayError = ref<string | null>(null)
let cleanup: (() => void) | undefined
let generation = 0
let imageGeneration = 0
let frame = 0
let activeViewport: Types.IStackViewport | null = null
let overlayImage: HTMLImageElement | null = null

function clearCanvas() {
  const canvas = overlayCanvas.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) return
  context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, canvas.width, canvas.height)
}

function drawOverlay() {
  frame = 0
  const canvas = overlayCanvas.value
  const element = viewportElement.value
  if (!canvas || !element) return
  const width = element.clientWidth
  const height = element.clientHeight
  const ratio = window.devicePixelRatio || 1
  const pixelWidth = Math.round(width * ratio)
  const pixelHeight = Math.round(height * ratio)
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth
    canvas.height = pixelHeight
  }
  clearCanvas()
  const overlay = props.overlay
  if (!props.overlayVisible || !overlay || !overlayImage || !activeViewport ||
      !overlayCompatible(overlay, props.sliceId, props.sliceWidth, props.sliceHeight)) return
  const geometry = overlay.geometry!
  try {
    const stackImage = activeViewport.getImageData()
    if (stackImage.dimensions[0] !== geometry.rawWidth || stackImage.dimensions[1] !== geometry.rawHeight) {
      throw new Error('Rendered image dimensions mismatch')
    }
    const indexToWorld = stackImage.imageData.indexToWorld
    if (!indexToWorld) throw new Error('Missing rendered image transform')
    const canvasPoint = (point: Point): Point => {
      const world = rawEdgeToWorld(point, index => indexToWorld(index))
      const [x, y] = activeViewport!.worldToCanvas(world)
      return { x, y }
    }
    const affine = canvasAffineFromCorners(geometry,
      canvasPoint({ x: 0, y: 0 }), canvasPoint({ x: geometry.rawWidth, y: 0 }),
      canvasPoint({ x: 0, y: geometry.rawHeight }),
      canvasPoint({ x: geometry.rawWidth, y: geometry.rawHeight }))
    if (!affine) throw new Error('Non-affine image-to-canvas mapping')
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas unavailable')
    context.setTransform(ratio * affine.a, ratio * affine.b, ratio * affine.c,
      ratio * affine.d, ratio * affine.e, ratio * affine.f)
    context.globalAlpha = Math.max(0, Math.min(1, props.overlayOpacity))
    context.imageSmoothingEnabled = overlay.layer.layer_kind === 'CANDIDATE_RESPONSE'
    context.drawImage(overlayImage, 0, 0, geometry.rawWidth, geometry.rawHeight)
    context.globalAlpha = 1
    overlayError.value = null
  } catch {
    clearCanvas()
    overlayError.value = 'Cornerstone 无法验证当前画布映射，已停止叠加。'
  }
}
function scheduleOverlay() {
  if (!frame) frame = requestAnimationFrame(drawOverlay)
}
function publishCamera() {
  if (!ready.value || !activeViewport) return
  const zoom = activeViewport.getZoom()
  const pan = activeViewport.getPan()
  if (Number.isFinite(zoom) && pan.every(Number.isFinite)) emit('cameraChanged', { zoom, pan: [pan[0], pan[1]] })
}
function onCameraModified() {
  scheduleOverlay()
  publishCamera()
}
function zoom(factor: number) {
  if (!activeViewport) return
  activeViewport.setZoom(Math.max(0.25, Math.min(8, activeViewport.getZoom() * factor)))
  activeViewport.render()
  scheduleOverlay()
  publishCamera()
}
function resetView() {
  if (!activeViewport) return
  activeViewport.resetCamera()
  activeViewport.render()
  scheduleOverlay()
  publishCamera()
}

watch([() => props.file, decodeAttempt], async ([file]) => {
  generation++
  cleanup?.()
  cleanup = undefined
  activeViewport = null
  ready.value = false
  loading.value = false
  error.value = null
  overlayError.value = null
  clearCanvas()
  if (!file) return
  const ownGeneration = generation
  loading.value = true
  await nextTick()
  if (!viewportElement.value || ownGeneration !== generation) {
    if (ownGeneration === generation) loading.value = false
    return
  }
  try {
    const core = await import('@cornerstonejs/core')
    const dicom = await import('@cornerstonejs/dicom-image-loader')
    const metadata = await import('@cornerstonejs/metadata')
    if (ownGeneration !== generation) return
    if (!loaderInitialized) {
      core.init()
      dicom.init({ maxWebWorkers: 2 })
      loaderInitialized = true
    }
    const imageId = dicom.wadouri.fileManager.add(file)
    const fileIndex = Number(imageId.split(':')[1])
    const datasetUri = String(fileIndex)
    let disposed = false
    let engine: InstanceType<typeof core.RenderingEngine> | undefined
    const releaseOwnedCache = () => {
      if (core.cache.getImageLoadObject(imageId)) core.cache.removeImageLoadObject(imageId, { force: true })
      // A load removed before its dataset finishes may not yet have a decache hook.
      if (dicom.wadouri.dataSetCacheManager.isLoaded(datasetUri)) dicom.wadouri.dataSetCacheManager.unload(datasetUri)
      // The default loader stores naturalized DICOM (including pixel data) separately.
      // clearQuery also removes this image's pending-add and derived metadata caches.
      metadata.metaData.clearQuery(metadata.Enums.MetadataModules.NATURALIZED, imageId)
    }
    const releaseResources = () => {
      if (disposed) return
      disposed = true
      const pendingImage = core.cache.getImageLoadObject(imageId)?.promise
      // Renderer teardown cannot cancel every worker decode; release late datasets too.
      if (pendingImage) void pendingImage.then(releaseOwnedCache, releaseOwnedCache)
      try { engine?.destroy() } finally {
        releaseOwnedCache()
        dicom.wadouri.fileManager.remove(fileIndex)
      }
    }
    cleanup = releaseResources
    engine = new core.RenderingEngine(`epilocate-viewer-${crypto.randomUUID()}`)
    const viewportId = 'single-slice'
    const element = viewportElement.value
    engine.enableElement({ viewportId, type: core.Enums.ViewportType.STACK, element })
    const viewport = engine.getViewport<Types.IStackViewport>(viewportId)
    let dragging: { x: number; y: number } | null = null
    const pointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return
      dragging = { x: event.clientX, y: event.clientY }
      element.setPointerCapture(event.pointerId)
    }
    const pointerMove = (event: PointerEvent) => {
      if (!dragging) return
      const dx = event.clientX - dragging.x
      const dy = event.clientY - dragging.y
      dragging = { x: event.clientX, y: event.clientY }
      const pan = viewport.getPan()
      viewport.setPan([pan[0] + dx, pan[1] + dy])
      viewport.render()
      scheduleOverlay()
      publishCamera()
    }
    const pointerUp = () => { dragging = null }
    const wheel = (event: WheelEvent) => {
      event.preventDefault()
      zoom(Math.exp(-event.deltaY * 0.001))
    }
    element.addEventListener('pointerdown', pointerDown)
    element.addEventListener('pointermove', pointerMove)
    element.addEventListener('pointerup', pointerUp)
    element.addEventListener('pointercancel', pointerUp)
    element.addEventListener('wheel', wheel, { passive: false })
    element.addEventListener(core.Enums.Events.CAMERA_MODIFIED, onCameraModified)
    element.addEventListener(core.Enums.Events.IMAGE_RENDERED, scheduleOverlay)
    const observer = new ResizeObserver(() => { engine?.resize(); scheduleOverlay() })
    observer.observe(element)
    cleanup = () => {
      observer.disconnect()
      element.removeEventListener('pointerdown', pointerDown)
      element.removeEventListener('pointermove', pointerMove)
      element.removeEventListener('pointerup', pointerUp)
      element.removeEventListener('pointercancel', pointerUp)
      element.removeEventListener('wheel', wheel)
      element.removeEventListener(core.Enums.Events.CAMERA_MODIFIED, onCameraModified)
      element.removeEventListener(core.Enums.Events.IMAGE_RENDERED, scheduleOverlay)
      if (frame) cancelAnimationFrame(frame)
      frame = 0
      releaseResources()
    }
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    try {
      const decoding = viewport.setStack([imageId])
      void decoding.then(() => { if (disposed) releaseOwnedCache() }, () => { if (disposed) releaseOwnedCache() })
      await Promise.race([
        decoding,
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => reject(new Error('DICOM decode timed out')), 15000)
        }),
      ])
    } finally {
      if (timeoutId) clearTimeout(timeoutId)
    }
    if (ownGeneration !== generation) return
    const decoded = viewport.getCornerstoneImage()
    if (decoded.columns !== props.sliceWidth || decoded.rows !== props.sliceHeight) {
      throw new Error('Decoded DICOM dimensions mismatch')
    }
    const savedView = props.initialView
    if (savedView && Number.isFinite(savedView.zoom) && savedView.zoom >= 0.25 && savedView.zoom <= 8 &&
        savedView.pan.every(value => Number.isFinite(value) && Math.abs(value) <= 100000)) {
      viewport.setZoom(savedView.zoom)
      viewport.setPan(savedView.pan)
    }
    activeViewport = viewport
    ready.value = true
    viewport.render()
    scheduleOverlay()
    publishCamera()
  } catch (cause) {
    if (ownGeneration === generation) {
      const message = cause instanceof Error ? cause.message : ''
      error.value = message === 'DICOM decode timed out' ? 'DICOM 解码超时，请重试。'
        : message === 'Decoded DICOM dimensions mismatch' ? 'DICOM 尺寸与病例元数据不一致，已停止显示。'
          : 'DICOM 无法解码，请确认影像格式或重试。'
      cleanup?.()
      cleanup = undefined
    }
  } finally {
    if (ownGeneration === generation) loading.value = false
  }
}, { immediate: true })

watch(() => props.overlay, async overlay => {
  const ownGeneration = ++imageGeneration
  overlayImage = null
  overlayError.value = null
  clearCanvas()
  if (!overlay || !overlayCompatible(overlay, props.sliceId, props.sliceWidth, props.sliceHeight)) return
  const image = new Image()
  image.src = overlay.url
  try {
    await image.decode()
    if (ownGeneration !== imageGeneration) return
    if (image.naturalWidth !== overlay.layer.width || image.naturalHeight !== overlay.layer.height) {
      overlayError.value = '响应图解码尺寸与图层元数据不一致，已停止叠加。'
      return
    }
    overlayImage = image
    scheduleOverlay()
  } catch {
    if (ownGeneration === imageGeneration) overlayError.value = '响应图无法解码，已停止叠加。'
  }
}, { immediate: true })
watch(() => [props.overlayVisible, props.overlayOpacity], scheduleOverlay)
onBeforeUnmount(() => {
  generation++
  imageGeneration++
  loading.value = false
  ready.value = false
  cleanup?.()
  activeViewport = null
})
</script>
