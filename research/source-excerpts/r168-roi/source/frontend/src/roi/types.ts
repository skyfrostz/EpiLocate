import type { Vertex } from './geometry'
export interface RoiSource { result_id?: string; source_image_id?: string; source_asset_id?: string; sha256: string; native_z: number; width: number; height: number; coordinate_system: 'RAW_PIXEL_EDGE'; geometry_version: 'RAW_PIXEL_EDGE_V1' }
export interface RoiGeometry { type: 'POLYGON'; closed: true; points: Vertex[] }
export interface RoiContext { ai_visible: boolean }
export interface RoiCreate { source: RoiSource; geometry: RoiGeometry; label: string; note: string; purpose: 'QA_TEST'|'RESEARCH_DISCUSSION'; context: RoiContext }
export interface RoiUpdate { expected_revision: number; geometry: RoiGeometry; label: string; note: string; context: RoiContext }
export interface RoiRecord { annotation_id: string; case_id: string; source_image_id: string; source_asset_sha256: string; native_z: number; width: number; height: number; coordinate_system: 'RAW_PIXEL_EDGE'; geometry_version: 'RAW_PIXEL_EDGE_V1'; geometry: RoiGeometry; label: string; note: string; purpose: 'QA_TEST'|'RESEARCH_DISCUSSION'; context: RoiContext; revision: number; review_status: 'UNREVIEWED'; soft_deleted: boolean; created_at: string; updated_at: string }
