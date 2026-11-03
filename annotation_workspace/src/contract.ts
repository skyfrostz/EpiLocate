export type Point = [number, number]
export interface Geometry {width:number;height:number;ipp:number[];iop:number[];spacing:number[]}
export interface Binding {case_id:string;slice_id:string;study_uid:string;series_uid:string;sop_instance_uid:string;frame_of_reference_uid:string;ct_sha256:string;geometry_sha256:string;geometry_version:'DICOM_NATIVE_CENTRES_LPS_V1'}
export interface Revision {annotation_id:string;operation_id:string;version:number;binding:Binding;vertices:Point[];world_vertices_lps_mm:number[][];category:string;state:'ACTIVE'|'WITHDRAWN';note:string;author:string;author_id:string;created_at:string;updated_at:string;review_status:string;revision_sha256:string;training_gt_eligible:false}
export function nativeToWorld([x,y]:Point,g:Geometry):[number,number,number] {
  return g.ipp.map((v,i)=>v+x*g.spacing[1]!*g.iop[i]!+y*g.spacing[0]!*g.iop[i+3]!) as [number,number,number]
}
export function worldToNative(p:number[],g:Geometry):Point {
  if(p.length!==3||!p.every(Number.isFinite))throw Error('非有限世界坐标')
  const d=p.map((v,i)=>v-g.ipp[i]!)
  const x=d.reduce((s,v,i)=>s+v*g.iop[i]!,0)/g.spacing[1]!
  const y=d.reduce((s,v,i)=>s+v*g.iop[i+3]!,0)/g.spacing[0]!
  const back=nativeToWorld([x,y],g)
  if(back.some((v,i)=>Math.abs(v-p[i]!)>1e-3))throw Error('顶点不在绑定的原生切片平面')
  return [x,y]
}
export function finiteInBounds(points:Point[],g:Geometry) {
  return points.length>=3&&points.length<=256&&points.every(p=>p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[0]<=g.width-1&&p[1]>=0&&p[1]<=g.height-1)
}
export function bindingOnly(value:Binding&{geometry:Geometry}):Binding {const {geometry:_,...binding}=value;return binding}
export class ApiError extends Error {constructor(public status:number,public code:string){super(code)}}
let csrf=''
export const REQUEST_TIMEOUT_MS=10000
export function setCsrf(value:string){csrf=value}
export async function api(path:string,body?:unknown) {
 const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',signal:AbortSignal.timeout(REQUEST_TIMEOUT_MS),headers:body===undefined?{}:{'Content-Type':'application/json','x-csrf-token':csrf},body:body===undefined?undefined:JSON.stringify(body)})
 if(!response.ok){let code='REQUEST_FAILED';try{code=(await response.json()).code??code}catch{};throw new ApiError(response.status,code)}
 return response.status===204?null:response.json()
}
