import type { HeatmapLayer } from '../api/types'

/** Component input only; no additional Backend API fields. */
export interface ViewerOverlayInput {
  url: string
  sliceId: string
  layer: HeatmapLayer
}

export function overlayCompatible(
  overlay: ViewerOverlayInput | null,
  sliceId: string | null,
  width: number | null,
  height: number | null,
): boolean {
  return Boolean(overlay && sliceId && overlay.sliceId === sliceId &&
    overlay.layer.coordinate_space === 'RAW_PIXEL_EDGE' &&
    overlay.layer.width === width && overlay.layer.height === height &&
    overlay.layer.origin === 'TOP_LEFT_PIXEL_EDGE' &&
    overlay.layer.x_axis === 'RIGHT' && overlay.layer.y_axis === 'DOWN')
}
