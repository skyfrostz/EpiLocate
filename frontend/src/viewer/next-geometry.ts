import type { ResultRecord } from '../api/types'
import type { ApplicationLayer } from '../api/next-algorithm'
import { applicationIdentityValid } from '../api/next-algorithm'
import type { GeometryGate } from './geometry'
export function resolveApplicationOverlay(result: ResultRecord, layer: ApplicationLayer | null, displayHash: string | null): GeometryGate {
  const req=result.application_request, output=result.application
  if (!applicationIdentityValid(result) || !req || !output) return {ok:false,reason:'新算法结果身份尚未通过校验。'}
  if (output.execution_status!=='SUCCESS') return {ok:false,reason:`${output.execution_status}：保留诊断结果，叠加关闭。`}
  if (!req.input.mapping_verified) return {ok:false,reason:'原生空间映射未验证。'}
  const input=req.input
  if (!layer || layer.layer_kind==='BASE_IMAGE' || displayHash!==input.display_sha256 || layer.display_sha256!==displayHash ||
      layer.mapping_qa_sha256!==input.mapping_qa_sha256 || layer.geometry_ledger_sha256!==input.geometry_ledger_sha256 ||
      layer.native_slice_index!==input.native_slice_index || layer.width!==input.native_shape_zyx[2] || layer.height!==input.native_shape_zyx[1] ||
      layer.coordinate_space!=='RAW_PIXEL_EDGE' || layer.origin!=='TOP_LEFT_PIXEL_EDGE' || layer.x_axis!=='RIGHT' || layer.y_axis!=='DOWN' || layer.display_interpolation_only!==true ||
      layer.evidence_type!==layer.layer_kind || !(req.algorithm_mode==='E2' ? ['OPTIMIZED_INPUT_MASK','HSPI_CPF_GAP','HSPI_CPF_PSMI_PATCH_SUPPORT','HSPI_PSMI_WHOLE_PATCH_SUPPORT']:['SIGNED_FEATURE_CONTRIBUTION']).includes(layer.layer_kind) ||
      !output.layers.some(l=>l.asset_id===layer.asset_id)) return {ok:false,reason:'图层、原图摘要或原生几何记录不一致。'}
  const descriptor=result.assets.find(a=>a.asset_id===layer.asset_id)
  if (!descriptor || !descriptor.sha256 || descriptor.width!==layer.width || descriptor.height!==layer.height || descriptor.coordinate_space!==layer.coordinate_space || descriptor.layer_kind!==layer.layer_kind) return {ok:false,reason:'资产清单未通过校验。'}
  return {ok:true,geometry:{rawWidth:layer.width,rawHeight:layer.height,modelWidth:layer.width,modelHeight:layer.height,rasterWidth:layer.width,rasterHeight:layer.height}}
}
