import type { CaseDetail, HeatmapLayer, ResultRecord, ScaleSummary } from '../api/types'

/** Only the frozen code audited at integration commit 02c8ef9 is eligible. */
export const AUDITED_GEOMETRY = {
  modelId: 'baseline_resnet18',
  modelVersion: '548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
  preprocessingVersion: 'formal-resnet18-baseline-rule-b-v1',
  protocolId: 'stage1-occlusion-instability-v1',
  modelWidth: 224,
  modelHeight: 224,
} as const

export interface Point { x: number; y: number }
export interface ViewerCameraState { zoom: number; pan: [number, number] }
export interface VerifiedGeometry {
  rawWidth: number
  rawHeight: number
  modelWidth: 224
  modelHeight: 224
  rasterWidth: number
  rasterHeight: number
}
export interface ViewerOverlayInput {
  url: string
  sliceId: string
  layer: HeatmapLayer
  geometry?: VerifiedGeometry
}
export type GeometryGate = { ok: true; geometry: VerifiedGeometry } | { ok: false; reason: string }

function positiveInteger(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0
}

export function resolveOverlayGeometry(
  result: ResultRecord,
  caseDetail: CaseDetail | null,
  dicomSha256: string | null,
  summary: ScaleSummary | null,
  layer: HeatmapLayer | null,
): GeometryGate {
  if (result.source !== 'LIVE_CASE' || result.status !== 'COMPLETED' || result.kind !== 'OCCLUSION') {
    return { ok: false, reason: '仅已完成的真实遮挡结果可叠加。' }
  }
  if (result.model_id !== AUDITED_GEOMETRY.modelId || result.model_version !== AUDITED_GEOMETRY.modelVersion ||
      result.preprocessing_version !== AUDITED_GEOMETRY.preprocessingVersion || result.protocol_id !== AUDITED_GEOMETRY.protocolId) {
    return { ok: false, reason: '模型或预处理版本尚无经过核验的几何映射。' }
  }
  if (!caseDetail || caseDetail.case_id !== result.case_id) {
    return { ok: false, reason: '病例与结果不一致。' }
  }
  const slice = caseDetail.studies.flatMap(study => study.series.flatMap(series => series.slices))
    .find(item => item.slice_id === result.slice_id)
  if (!slice || !positiveInteger(slice.width_px) || !positiveInteger(slice.height_px)) {
    return { ok: false, reason: '缺少当前切片的原始像素尺寸。' }
  }
  const sourceHash = result.provenance.input_sha256
  if (typeof sourceHash !== 'string' || !/^[a-f0-9]{64}$/i.test(sourceHash) ||
      !dicomSha256 || sourceHash.toLowerCase() !== dicomSha256.toLowerCase()) {
    return { ok: false, reason: '原始 DICOM 与推理输入的摘要不一致或不可验证。' }
  }
  if (!summary || ![16, 32, 64].includes(summary.block_size) || !layer ||
      !result.scale_summaries.some(item => item.block_size === summary.block_size) ||
      ![summary.response_layer?.asset_id, summary.candidate_layer?.asset_id,
        summary.comparison_grid_layer?.asset_id].includes(layer.asset_id)) {
    return { ok: false, reason: '选定图层不属于当前尺度。' }
  }
  if (layer.layer_kind === 'CANDIDATE_TOP10' && summary.candidate_status !== 'valid') {
    return { ok: false, reason: '当前尺度的候选响应无效。' }
  }
  const summaryLayer = layer.layer_kind === 'CANDIDATE_RESPONSE' ? summary.response_layer
    : layer.layer_kind === 'CANDIDATE_TOP10' ? summary.candidate_layer : summary.comparison_grid_layer
  if (!summaryLayer || Object.entries(summaryLayer).some(([key, value]) =>
    layer[key as keyof HeatmapLayer] !== value)) {
    return { ok: false, reason: '图层字段与尺度摘要不一致。' }
  }
  const expected = layer.layer_kind === 'COMPARISON_GRID'
    ? { space: 'COMPARISON_14', size: 14 }
    : layer.layer_kind === 'CANDIDATE_RESPONSE' || layer.layer_kind === 'CANDIDATE_TOP10'
      ? { space: 'ALGORITHM_224', size: 224 } : null
  if (!expected || layer.coordinate_space !== expected.space || layer.width !== expected.size ||
      layer.height !== expected.size || layer.origin !== 'TOP_LEFT_PIXEL_EDGE' ||
      layer.x_axis !== 'RIGHT' || layer.y_axis !== 'DOWN' || layer.display_interpolation_only !== true) {
    return { ok: false, reason: '图层坐标空间、轴向或尺寸不符合已核验契约。' }
  }
  const descriptor = result.assets.find(asset => asset.asset_id === layer.asset_id)
  if (!descriptor || descriptor.layer_kind !== layer.layer_kind || descriptor.coordinate_space !== layer.coordinate_space ||
      descriptor.width !== layer.width || descriptor.height !== layer.height || descriptor.media_type !== 'image/png') {
    return { ok: false, reason: '图层与 Result 资产清单不一致。' }
  }
  return { ok: true, geometry: {
    rawWidth: slice.width_px, rawHeight: slice.height_px,
    modelWidth: 224, modelHeight: 224,
    rasterWidth: layer.width, rasterHeight: layer.height,
  } }
}

export function overlayCompatible(overlay: ViewerOverlayInput | null, sliceId: string | null,
  width: number | null, height: number | null): boolean {
  const geometry = overlay?.geometry
  return Boolean(overlay && geometry && sliceId && overlay.sliceId === sliceId &&
    geometry.rawWidth === width && geometry.rawHeight === height &&
    positiveInteger(geometry.rawWidth) && positiveInteger(geometry.rawHeight) &&
    geometry.modelWidth === 224 && geometry.modelHeight === 224 &&
    geometry.rasterWidth === overlay.layer.width && geometry.rasterHeight === overlay.layer.height &&
    overlay.layer.origin === 'TOP_LEFT_PIXEL_EDGE' && overlay.layer.x_axis === 'RIGHT' &&
    overlay.layer.y_axis === 'DOWN' && overlay.layer.display_interpolation_only === true &&
    (overlay.layer.layer_kind === 'COMPARISON_GRID'
      ? overlay.layer.coordinate_space === 'COMPARISON_14' && overlay.layer.width === 14 && overlay.layer.height === 14
      : overlay.layer.coordinate_space === 'ALGORITHM_224' && overlay.layer.width === 224 && overlay.layer.height === 224))
}

/** Continuous pixel-edge coordinates. Raw x=column, y=row. */
export function rawEdgeToModel(point: Point, geometry: VerifiedGeometry): Point {
  return { x: point.x * geometry.modelWidth / geometry.rawWidth,
    y: point.y * geometry.modelHeight / geometry.rawHeight }
}
export function modelEdgeToRaw(point: Point, geometry: VerifiedGeometry): Point {
  return { x: point.x * geometry.rawWidth / geometry.modelWidth,
    y: point.y * geometry.rawHeight / geometry.modelHeight }
}
export function rasterEdgeToModel(point: Point, geometry: VerifiedGeometry): Point {
  return { x: point.x * geometry.modelWidth / geometry.rasterWidth,
    y: point.y * geometry.modelHeight / geometry.rasterHeight }
}
export function rasterEdgeToRaw(point: Point, geometry: VerifiedGeometry): Point {
  return modelEdgeToRaw(rasterEdgeToModel(point, geometry), geometry)
}
export function occlusionBlockToRaw(x: number, y: number, blockSize: 16 | 32 | 64,
  geometry: VerifiedGeometry): { topLeft: Point; bottomRight: Point } {
  return { topLeft: modelEdgeToRaw({ x, y }, geometry),
    bottomRight: modelEdgeToRaw({ x: x + blockSize, y: y + blockSize }, geometry) }
}

/** Cornerstone imageData origin is the first pixel center; edge (0,0) is index (-0.5,-0.5).
 * Use the rendered imageData transform, whose spacing/direction agree with the StackViewport.
 */
export function rawEdgeToWorld(point: Point, indexToWorld: (index: [number, number, number]) => ArrayLike<number>): [number, number, number] {
  const world = indexToWorld([point.x - 0.5, point.y - 0.5, 0])
  if (world.length < 3 || ![world[0], world[1], world[2]].every(value => Number.isFinite(value))) {
    throw new Error('Invalid Cornerstone image index-to-world mapping')
  }
  return [world[0]!, world[1]!, world[2]!]
}

/** Affine from four Cornerstone-reported raw-image edge anchors to CSS pixels. */
export interface CanvasAffine { a: number; b: number; c: number; d: number; e: number; f: number }
export function canvasAffineFromCorners(
  geometry: VerifiedGeometry,
  topLeft: Point,
  topRight: Point,
  bottomLeft: Point,
  bottomRight: Point,
): CanvasAffine | null {
  const { rawWidth: width, rawHeight: height } = geometry
  const affine = {
    a: (topRight.x - topLeft.x) / width, b: (topRight.y - topLeft.y) / width,
    c: (bottomLeft.x - topLeft.x) / height, d: (bottomLeft.y - topLeft.y) / height,
    e: topLeft.x, f: topLeft.y,
  }
  if (Object.values(affine).some(value => !Number.isFinite(value)) ||
      Math.abs(affine.a * affine.d - affine.b * affine.c) < 1e-9) return null
  const predicted = rawEdgeToCanvas({ x: width, y: height }, affine)
  if (Math.hypot(predicted.x - bottomRight.x, predicted.y - bottomRight.y) > 0.25) return null
  return affine
}
export function rawEdgeToCanvas(point: Point, affine: CanvasAffine): Point {
  return { x: affine.a * point.x + affine.c * point.y + affine.e,
    y: affine.b * point.x + affine.d * point.y + affine.f }
}
export function canvasToRawEdge(point: Point, affine: CanvasAffine): Point {
  const det = affine.a * affine.d - affine.b * affine.c
  const x = point.x - affine.e
  const y = point.y - affine.f
  return { x: (affine.d * x - affine.c * y) / det,
    y: (-affine.b * x + affine.a * y) / det }
}
