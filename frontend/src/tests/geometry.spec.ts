import { describe, expect, it } from 'vitest'
import type { CaseDetail, HeatmapLayer, ResultRecord, ScaleSummary } from '../api/types'
import {
  canvasAffineFromCorners, canvasToRawEdge, modelEdgeToRaw, occlusionBlockToRaw,
  overlayCompatible, rasterEdgeToModel, rasterEdgeToRaw, rawEdgeToCanvas,
  rawEdgeToModel, rawEdgeToWorld, resolveOverlayGeometry, type VerifiedGeometry,
} from '../viewer/geometry'

const geometry: VerifiedGeometry = {
  rawWidth: 112, rawHeight: 80, modelWidth: 224, modelHeight: 224,
  rasterWidth: 224, rasterHeight: 224,
}
const hash = '8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee'
const makeLayer = (kind: HeatmapLayer['layer_kind'], size = 224): HeatmapLayer => ({
  asset_id: `${kind}-${size}.png`, layer_kind: kind, width: size, height: size,
  coordinate_space: size === 14 ? 'COMPARISON_14' : 'ALGORITHM_224',
  value_min: 0, value_max: 1, origin: 'TOP_LEFT_PIXEL_EDGE',
  x_axis: 'RIGHT', y_axis: 'DOWN', display_interpolation_only: true,
})
const response = makeLayer('CANDIDATE_RESPONSE')
const candidate = makeLayer('CANDIDATE_TOP10')
const comparison = makeLayer('COMPARISON_GRID', 14)
const summary: ScaleSummary = {
  block_size: 16, stride: 8, fill: 0.5, baseline_positive_probability: 0.2,
  median_absolute_probability_change: 0.01, flip_rate: 0,
  candidate_status: 'valid', candidate_area_fraction: 0.1,
  response_layer: response, candidate_layer: candidate, comparison_grid_layer: comparison,
}
const caseDetail: CaseDetail = {
  case_id: 'case_test', patient_id: 'pat_test', status: 'READY',
  created_at: '2026-09-27T00:00:00Z', input_expires_at: '2026-10-04T00:00:00Z',
  studies: [{ study_id: 'study_test', series: [{ series_id: 'series_test',
    slices: [{ slice_id: 'slice_test', ordinal: 0, width_px: 112, height_px: 80 }] }] }],
}
const result: ResultRecord = {
  result_id: 'result_test', job_id: 'job_test', case_id: 'case_test', slice_id: 'slice_test',
  kind: 'OCCLUSION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline_resnet18',
  model_version: '548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
  preprocessing_version: 'formal-resnet18-baseline-rule-b-v1',
  protocol_id: 'stage1-occlusion-instability-v1', prediction: null,
  scale_summaries: [summary], cross_scale: [], provenance: { input_sha256: hash },
  assets: [response, candidate, comparison].map(layer => ({
    asset_id: layer.asset_id, layer_kind: layer.layer_kind, width: layer.width,
    height: layer.height, coordinate_space: layer.coordinate_space, media_type: 'image/png',
  })), created_at: '2026-09-27T00:00:00Z',
}

describe('audited raw DICOM → model → raster edge mapping', () => {
  it('maps all four corners and the center of the non-square 112×80 fixture without swapping axes', () => {
    expect(rawEdgeToModel({ x: 0, y: 0 }, geometry)).toEqual({ x: 0, y: 0 })
    expect(rawEdgeToModel({ x: 112, y: 0 }, geometry)).toEqual({ x: 224, y: 0 })
    expect(rawEdgeToModel({ x: 0, y: 80 }, geometry)).toEqual({ x: 0, y: 224 })
    expect(rawEdgeToModel({ x: 112, y: 80 }, geometry)).toEqual({ x: 224, y: 224 })
    expect(rawEdgeToModel({ x: 56, y: 40 }, geometry)).toEqual({ x: 112, y: 112 })
    expect(modelEdgeToRaw({ x: 224, y: 112 }, geometry)).toEqual({ x: 112, y: 40 })
  })

  it('keeps half-pixel centers on an arbitrary 101×73 image with direct resize and no crop/pad', () => {
    const odd: VerifiedGeometry = { ...geometry, rawWidth: 101, rawHeight: 73 }
    const first = rawEdgeToModel({ x: 0.5, y: 0.5 }, odd)
    expect(first.x).toBeCloseTo(112 / 101, 12)
    expect(first.y).toBeCloseTo(112 / 73, 12)
    const back = modelEdgeToRaw(first, odd)
    expect(back.x).toBeCloseTo(0.5, 12)
    expect(back.y).toBeCloseTo(0.5, 12)
    expect(rawEdgeToModel({ x: 50.5, y: 36.5 }, odd)).toEqual({ x: 112, y: 112 })
  })

  it('keeps 16/32/64 squares inside model bounds and maps their edges to the same raw slice', () => {
    for (const [block, finalStart] of [[16, 208], [32, 192], [64, 160]] as const) {
      const mapped = occlusionBlockToRaw(finalStart, finalStart, block, geometry)
      expect(mapped.bottomRight).toEqual({ x: 112, y: 80 })
      expect(mapped.topLeft.x).toBeCloseTo(finalStart / 2, 12)
      expect(mapped.topLeft.y).toBeCloseTo(finalStart / 2.8, 12)
    }
  })

  it('maps each 14×14 comparison cell to a 16×16 model area without pretending to add resolution', () => {
    const coarse: VerifiedGeometry = { ...geometry, rasterWidth: 14, rasterHeight: 14 }
    expect(rasterEdgeToModel({ x: 1, y: 1 }, coarse)).toEqual({ x: 16, y: 16 })
    expect(rasterEdgeToRaw({ x: 1, y: 1 }, coarse)).toEqual({ x: 8, y: 80 / 14 })
    expect(rasterEdgeToRaw({ x: 14, y: 14 }, coarse)).toEqual({ x: 112, y: 80 })
  })
})

describe('Cornerstone rendered image geometry', () => {
  it('uses first-pixel-center origin and renderer spacing for rotated unequal-spacing DICOM', () => {
    const indexToWorld = ([column, row]: [number, number, number]) =>
      [12 - 0.7 * row, 34 + 1.2 * column, 56]
    expect(rawEdgeToWorld({ x: 0, y: 0 }, indexToWorld)).toEqual([12.35, 33.4, 56])
    expect(rawEdgeToWorld({ x: 112, y: 80 }, indexToWorld)).toEqual([12 - 0.7 * 79.5, 34 + 1.2 * 111.5, 56])
    expect(rawEdgeToWorld({ x: 0.5, y: 0.5 }, indexToWorld)).toEqual([12, 34, 56])
  })
})

describe('Cornerstone viewport affine reconstruction', () => {
  const corners = [
    { x: 500, y: 20 }, { x: 500, y: 356 },
    { x: 180, y: 20 }, { x: 180, y: 356 },
  ] as const
  it('follows a rotated viewport, pan and zoom without vertical inversion or half-pixel drift', () => {
    const affine = canvasAffineFromCorners(geometry, ...corners)
    expect(affine).not.toBeNull()
    expect(rawEdgeToCanvas({ x: 56, y: 40 }, affine!)).toEqual({ x: 340, y: 188 })
    expect(canvasToRawEdge({ x: 340, y: 188 }, affine!)).toEqual({ x: 56, y: 40 })
    expect(rawEdgeToCanvas({ x: 0.5, y: 0.5 }, affine!)).toEqual({ x: 498, y: 21.5 })
  })

  it('recomputes after viewport resize or pan instead of reusing old CSS bounds', () => {
    const original = canvasAffineFromCorners(geometry,
      { x: 10, y: 20 }, { x: 234, y: 20 }, { x: 10, y: 180 }, { x: 234, y: 180 })!
    const changed = canvasAffineFromCorners(geometry,
      { x: 50, y: 70 }, { x: 498, y: 70 }, { x: 50, y: 390 }, { x: 498, y: 390 })!
    expect(rawEdgeToCanvas({ x: 56, y: 40 }, original)).toEqual({ x: 122, y: 100 })
    expect(rawEdgeToCanvas({ x: 56, y: 40 }, changed)).toEqual({ x: 274, y: 230 })
  })

  it('rejects a non-affine or degenerate viewport rather than visually stretching the overlay', () => {
    expect(canvasAffineFromCorners(geometry,
      { x: 0, y: 0 }, { x: 224, y: 0 }, { x: 0, y: 160 }, { x: 226, y: 160 })).toBeNull()
    expect(canvasAffineFromCorners(geometry,
      { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 160 }, { x: 0, y: 160 })).toBeNull()
  })
})

describe('overlay contract gate', () => {
  it('allows only a matching LIVE_CASE response, candidate, or comparison asset', () => {
    for (const layer of [response, candidate, comparison]) {
      const gate = resolveOverlayGeometry(result, caseDetail, hash, summary, layer)
      expect(gate.ok).toBe(true)
      if (gate.ok) expect(overlayCompatible({ url: 'blob:test', sliceId: 'slice_test', layer,
        geometry: gate.geometry }, 'slice_test', 112, 80)).toBe(true)
    }
  })

  it('rejects wrong source hash, slice, asset dimensions, and an invalid candidate', () => {
    expect(resolveOverlayGeometry(result, caseDetail, '0'.repeat(64), summary, response).ok).toBe(false)
    expect(resolveOverlayGeometry({ ...result, slice_id: 'slice_other' }, caseDetail, hash, summary, response).ok).toBe(false)
    expect(resolveOverlayGeometry({ ...result, assets: [{ ...result.assets[0]!, width: 112 }] },
      caseDetail, hash, summary, response).ok).toBe(false)
    expect(resolveOverlayGeometry(result, caseDetail, hash,
      { ...summary, candidate_status: 'insufficient_positive_response' }, candidate).ok).toBe(false)
    expect(overlayCompatible({ url: 'blob:test', sliceId: 'slice_other', layer: response,
      geometry }, 'slice_test', 112, 80)).toBe(false)
  })

  it('keeps overlay disabled for future crop/padding versions or incomplete geometry metadata', () => {
    expect(resolveOverlayGeometry({ ...result, preprocessing_version: 'future-crop-pad-v2' },
      caseDetail, hash, summary, response).ok).toBe(false)
    expect(resolveOverlayGeometry({ ...result, provenance: {} }, caseDetail, hash, summary, response).ok).toBe(false)
    expect(resolveOverlayGeometry(result, caseDetail, hash, summary,
      { ...response, origin: 'UNKNOWN' as HeatmapLayer['origin'] }).ok).toBe(false)
  })
})
