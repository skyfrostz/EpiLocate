"""E2 serialization only. Algorithms and native rasterization remain LOC-owned."""
import hashlib
import gzip
import io
import itertools
import json
from pathlib import Path
from PIL import Image
from .contracts import HandlerResult, Layer
from .runner import HandlerOutput


def plain(value):
    if hasattr(value,'detach'):return value.detach().cpu().tolist()
    if hasattr(value,'tolist'):return value.tolist()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def save_json(directory,name,value,maximum):
    raw=json.dumps(plain(value),sort_keys=True,allow_nan=False).encode()
    used=sum(p.stat().st_size for p in Path(directory).rglob('*') if p.is_file())
    if used+len(raw)>maximum:raise ValueError('E2_DIAGNOSTICS_OUTPUT_BUDGET')
    with (Path(directory)/name).open('xb') as stream:
        stream.write(raw);stream.flush()
    (Path(directory)/name).chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def save_compressed_json(directory,name,value,maximum,*,append=False):
    # Preserve exact numeric records without duplicating dense native grids as
    # unbounded plain JSON. Concatenated gzip members retain every trace row.
    raw=json.dumps(plain(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    packed=gzip.compress(raw+b'\n',mtime=0)
    used=sum(p.stat().st_size for p in Path(directory).rglob('*') if p.is_file())
    if used+len(packed)>maximum:raise ValueError('E2_DIAGNOSTICS_OUTPUT_BUDGET')
    path=Path(directory)/name
    with path.open('ab' if append else 'xb') as stream:stream.write(packed);stream.flush()
    path.chmod(0o600)
    return hashlib.sha256(packed).hexdigest()


def world_bounds(bounds,index,affine):
    y0,y1,x0,x1=bounds
    points=[]
    for z,y,x in itertools.product((index-.5,index+.5),(y0-.5,y1-.5),(x0-.5,x1-.5)):
        points.append([sum(row[j]*v for j,v in enumerate((z,y,x,1))) for row in affine[:3]])
    return (tuple(min(p[j] for p in points) for j in range(3)),tuple(max(p[j] for p in points) for j in range(3)))


def output_from_saved_e2(req,raw,directory,context,start,*,replay=False,source_result_sha256=None):
    i=req.input
    if raw['schema'] not in {'EPI_NEXT_E2_HANDLER_V4','EPI_NEXT_E2_HANDLER_V5'} or raw['native_space']['native_slice_index']!=i.native_slice_index:raise ValueError('E2_NATIVE_RESULT_BINDING_MISMATCH')
    raw_hash=save_compressed_json(directory,'e2-handler-result.json.gz',raw,req.budget.output_bytes//2)
    layers=[];assets={}
    def add_layer(name,kind,values):
        rows=plain(values)
        if len(rows)!=i.native_shape_zyx[1] or any(len(row)!=i.native_shape_zyx[2] for row in rows):raise ValueError('E2_NATIVE_RESULT_SHAPE_MISMATCH')
        flat=[v for row in rows for v in row];lo=min(flat);hi=max(flat)
        pixels=bytes(round(255*(v-lo)/(hi-lo)) if hi>lo else 0 for v in flat)
        png=io.BytesIO();Image.frombytes('L',(len(rows[0]),len(rows)),pixels).save(png,format='PNG');assets[name]=png.getvalue()
        layers.append(Layer(asset_id=name,layer_kind=kind,evidence_type=kind,width=len(rows[0]),height=len(rows),coordinate_space='RAW_PIXEL_EDGE',origin='TOP_LEFT_PIXEL_EDGE',x_axis='RIGHT',y_axis='DOWN',display_interpolation_only=True,value_min=lo,value_max=hi,raw_values=rows,display_sha256=i.display_sha256,geometry_ledger_sha256=i.geometry_ledger_sha256,mapping_qa_sha256=i.mapping_qa_sha256,native_slice_index=i.native_slice_index))
    add_layer('cpf-gap.png','HSPI_CPF_GAP',raw['native_space']['scores'])
    add_layer('cpf-psmi-support.png','HSPI_CPF_PSMI_PATCH_SUPPORT',raw['native_space']['reliable'])
    if 'psmi_whole_patch_support' in raw:add_layer('psmi-whole-patch.png','HSPI_PSMI_WHOLE_PATCH_SUPPORT',raw['psmi_whole_patch_support']['native_values'])
    for n,mask in enumerate(raw['optimized_input_masks']):add_layer(f'mask-{n}.png','OPTIMIZED_INPUT_MASK',mask['native_values'])
    original=plain(raw['original_logits']);prediction=None
    if original is not None:
        logits=original[0];pred=raw['original_class'];prediction=dict(logits=logits,predicted_class=pred,class_label=req.task.class_labels[pred],probabilities=None)
    status=raw['execution_status'];elapsed=context.clock()-context.start
    if elapsed>req.budget.seconds:
        status='FAILED' if status=='FAILED' else 'PARTIAL_BUDGET'
        if not context.stop_events:context.stop_events.append(dict(kind='TIME_BUDGET',elapsed_seconds=elapsed,deadline_elapsed_seconds=req.budget.seconds,new_work_after_stop=False))
    candidates=[]
    if status=='SUCCESS' and i.mapping_verified:
        for c in raw.get('candidates',[]):
            candidates.append(dict(response=c['response'],evidence_type='HSPI_CPF_PSMI_PATCH_SUPPORT',bbox_lps_mm=world_bounds(c['native_bounds_yx_half_open'],i.native_slice_index,i.affine_lps),stage=c['stage']))
    sources={'handler_result':raw_hash,'core':raw['core_sha256'],'prepared_input':raw['input_binding']['input_sha256']}
    if source_result_sha256:sources['precomputed_source_result']=source_result_sha256
    diagnostics=dict(method=raw['method'],psmi=raw['psmi'],planned_branches=raw['planned_branches'],full_plan_completed=raw['full_plan_completed'],skipped_branches=raw['skipped_branches'],unrun_branches=raw['unrun_branches'],candidate_provisional=raw['candidate_provisional'],reused_historical_observations=raw['reused_historical_observations'],source_execution_cost=raw['new_cost'],source_evidence_type=raw['evidence_type'],precomputed_replay=replay)
    if raw['schema']=='EPI_NEXT_E2_HANDLER_V5':
        diagnostics.update(source_handler_schema=raw['schema'],target_contract=raw['target_contract'],source_model_binding=raw['input_binding'])
    return HandlerOutput(HandlerResult(execution_status=status,algorithm_status=raw['method'],reason=None if status=='SUCCESS' else str(raw['new_cost'].get('stop_reason') or status),prediction=prediction,candidates=candidates,layers=layers,actual_forward=context.forward_count,actual_backward=context.backward_count,actual_updates=context.update_count,runtime_seconds=elapsed,stop_events=context.stop_events,source_artifacts=sources,diagnostics=diagnostics),assets)
