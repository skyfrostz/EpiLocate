"""Bind existing real E1/E2 assets to native CT and DATA's partial reference.

Only reads SHA-fixed results, native HU and official published union masks.
No model call, GT reconstruction, label filtering, ranking or metric evaluation.
Medical PNG/HTML outputs must remain in the approved ignored local directory.
"""
import argparse
import html
import io
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from .artifacts import canonical_json, persist_run, reconcile_run
from .first_real_preparation import file_sha, read_locked_json, ROOT


E1_MODEL_ID = "EPI-NEXT-E1-baseline-resnet18-fixed-target-margin-v1"
E2_MODEL_ID = "EPI-NEXT-E2-baseline-resnet18-HSPI-inspired-single-stage-v1"


def validate_native_bundle(reference, record, shape):
    if file_sha(reference['path']) != reference['sha256']:
        raise ValueError('NATIVE_BUNDLE_HASH_MISMATCH')
    with np.load(reference['path'], allow_pickle=False) as data:
        if (data['SOPInstanceUID'].item() != record['source_sop_uid']
                or data['native_case_manifest_sha256'].item() != record['native_manifest_sha256']
                or data['native_slice_index'].item() != record['native_slice_index_zero_based']
                or data['scores'].shape != shape or data['reliable'].shape != shape
                or data['reliable'].dtype != np.bool_ or not np.isfinite(data['scores']).all()):
            raise ValueError('NATIVE_BUNDLE_IDENTITY_OR_SHAPE_MISMATCH')
        return data['scores'].copy(), data['reliable'].copy()


def label_direction(vector):
    labels = (('R','L'),('A','P'),('I','S'))
    axis = int(np.abs(vector).argmax())
    return labels[axis][int(vector[axis] > 0)]


def render_comparison(hu, e1, e2, references, geometry, case_index, statuses):
    figure = Figure(figsize=(15,10), dpi=140, facecolor='#10151c')
    FigureCanvasAgg(figure)
    rows, columns = hu.shape
    affine = np.asarray(geometry['native_affine_lps'])
    aspect = np.linalg.norm(affine[:3,1]) / np.linalg.norm(affine[:3,2])
    axes = figure.subplots(2,3)
    for ax in axes.flat:
        ax.imshow(hu, cmap='gray', vmin=-1350, vmax=150, origin='upper', interpolation='nearest')
        ax.set_xlim(-.5, columns-.5); ax.set_ylim(rows-.5,-.5); ax.set_aspect(aspect)
        ax.set_xlabel('native column', color='#b7c3d2');ax.set_ylabel('native row',color='#b7c3d2')
        ax.tick_params(colors='#b7c3d2',labelsize=7)
        ax.set_facecolor('#10151c')
    axes[0,0].set_title('Original native HU / window -600, 1500',color='white',fontsize=10)
    for ax, scale in zip([axes[0,1],axes[0,2],axes[1,0]], (16,32,64)):
        scores, reliable=e1[scale]
        limit=float(np.max(np.abs(scores)))
        if limit>0:
            image=ax.imshow(scores,cmap='coolwarm',vmin=-limit,vmax=limit,origin='upper',interpolation='nearest',alpha=.42)
            bar=figure.colorbar(image,ax=ax,fraction=.046,pad=.02);bar.ax.tick_params(labelsize=7,colors='#b7c3d2')
        if reliable.any() and not reliable.all():ax.contour(reliable.astype(float),levels=[.5],colors='#ffc857',linewidths=.5)
        ax.set_title(f'E1 {scale}px | signed margin response\norange: published accepted support',color='white',fontsize=9)
    ax=axes[1,1]
    if e2[1].any():ax.contour(e2[1].astype(float),levels=[.5],colors='#b99aff',linewidths=.6)
    ax.set_title(f"E2 / {statuses['E2']}\n{int(e2[1].sum())} retained pixels; no substitute heatmap",color='white',fontsize=9)
    ax=axes[1,2]
    for i,(category,mask) in enumerate(references):
        color=['#39ddd3','#a9e46f','#ea95ed'][i%3]
        if mask.any() and not mask.all():ax.contour(mask.astype(float),levels=[.5],colors=color,linewidths=.9)
        ax.plot([],[],color=color,label=category)
    if references:ax.legend(loc='lower left',fontsize=7,facecolor='#17202c',labelcolor='white')
    ax.set_title('Official partial reference / native mask\nunannotated regions UNKNOWN; not consensus GT',color='white',fontsize=9)
    figure.suptitle(f'Case {case_index} / fixed slice {geometry["native_slice_index_zero_based"]} | E1 {statuses["E1"]} | E2 {statuses["E2"]}',color='white',fontsize=13)
    figure.text(.02,.016,f'+column -> {label_direction(affine[:3,2])}; +row -> {label_direction(affine[:3,1])} (DICOM LPS) | native pixel centres | E1 color limits are scale-specific | LOCAL DEVELOPMENT ONLY',color='#b7c3d2',fontsize=8)
    figure.subplots_adjust(left=.055,right=.95,top=.90,bottom=.07,wspace=.34,hspace=.30)
    stream=io.BytesIO();figure.savefig(stream,format='png',facecolor=figure.get_facecolor());figure.clear()
    return stream.getvalue()


def comparison_html(cases):
    sections=[]
    for case in cases:
        summary=case['summary'];idx=summary['case_index']
        sections.append(f'''<section id="case-{idx}"><h2>开发例 {idx} · 固定切片 {summary['native_slice_index']}</h2>
<p>E1：{html.escape(summary['E1_status'])} · E2：{html.escape(summary['E2_status'])} · 原始 logits：{html.escape(str(summary['baseline_logits']))}</p>
<img src="case-{idx}-comparison.png" width="2100" height="1400" alt="开发例{idx}原始CT、E1三个尺度、E2状态与官方部分参考，全部原生像素坐标">
<details><summary>运行及资产关联</summary><pre>{html.escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details></section>''')
    return ('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'">
<title>EPI-NEXT · 本地原生坐标对照</title><style>body{margin:0;background:#10151c;color:#e9eef6;font:16px/1.6 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:28px}h1{font-size:28px}h2{font-size:22px}section{margin:36px 0;border-top:1px solid #384252;padding-top:18px}img{display:block;width:100%;height:auto}a{color:#55ddd3}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}nav a{margin-right:18px}.status{border-left:3px solid #ffc857;padding:12px;background:#17202c}</style>
<main><h1>CT / E1 / E2 / 官方部分参考</h1><p class="status">获准本地研发对照，非医院展示。E1是旧模型固定目标遮挡margin响应，E2是HSPI-inspired variant，全logits一致性；均非病灶概率。部分参考的未标注区域UNKNOWN，不计算新的临床准确率。</p>
<nav><a href="#case-1">开发例1</a><a href="#case-2">开发例2</a><a href="#case-3">开发例3</a></nav>'''+''.join(sections)+
'''<footer>同坐标本地读取与资产绑定不是三次真实模型演示、独立DATA空间验收或临床有效性。医院默认算法未决。</footer></main></html>''').encode()


def build_comparison(args):
    run_id='EPI-NEXT-REAL-COMPARISON-v1'
    output=Path(args.output).resolve()
    local_root=(ROOT/'research/next-hospital-20261014/.local').resolve()
    if local_root not in output.parents:raise ValueError('PROTECTED_LOCAL_OUTPUT_REQUIRED')
    if output.name!=run_id:raise ValueError('OUTPUT_NAME_MUST_MATCH_BINDING_RUN_ID')
    if output.exists():raise RuntimeError('EXISTING_COMPARISON_RECONCILE_NO_OVERWRITE')
    delivery=read_locked_json(args.run_delivery,args.run_sha)
    prepared=read_locked_json(delivery['prepared_delivery_path'],delivery['prepared_delivery_sha256'])
    data=read_locked_json(args.data_delivery,delivery['data_delivery_sha256'])
    read_locked_json(data['gt_vnext']['path'],data['gt_vnext']['manifest_sha256'])
    gt_root=Path(data['gt_vnext']['path']).parent.resolve()
    if (delivery['schema']!='EPI-NEXT-FIRST-REAL-E1E2-RESULT-1' or delivery['patient_count']!=3
            or delivery['slice_count']!=3 or delivery['slice_lock_sha256']!=prepared['slice_lock_sha256']
            or delivery['config_sha256']!=prepared['algorithm_config_sha256']
            or delivery['checkpoint_sha256']!=prepared['checkpoint_sha256']):
        raise ValueError('UPSTREAM_RUN_PREPARED_BINDING_MISMATCH')
    evaluation=read_locked_json(args.evaluation,'55dbe1c71dbb3836f28ae3a4352f2a9c0d257b403b97e6ac4a7f65929856b477')
    if evaluation['run_delivery_sha256']!=args.run_sha or evaluation['candidate_inverse_mapping_status']!='PASS':
        raise ValueError('INDEPENDENT_DATA_MAPPING_HANDOFF_MISMATCH')
    artifacts={};cases=[]
    for record in delivery['records']:
        result=read_locked_json(record['result_path'],record['result_sha256'])
        p=next(r for r in prepared['records'] if r['case_index']==record['case_index'])
        if (result['prepared_record']!=p or result['input_sha256']!=p['prepared_contract']['input_sha256']
                or result['geometry_source_sha256']!=p['geometry']['sha256']
                or result['locked_config_sha256']!=delivery['config_sha256']):
            raise ValueError('RESULT_INPUT_OR_GEOMETRY_MISMATCH')
        geometry=read_locked_json(p['geometry']['path'],p['geometry']['sha256'])
        mapping=next(r for r in data['spatial_mapping']['cases'] if r['manifest_sha256']==p['native_manifest_sha256'])
        manifest=read_locked_json(mapping['manifest_path'],mapping['manifest_sha256'])
        sop=next(r for r in manifest['sops'] if r['SOPInstanceUID']==p['source_sop_uid'])
        z=p['native_slice_index_zero_based']
        if sop['native_slice_index']!=z or manifest['native_volume']['ordered_sop_uids'][z]!=p['source_sop_uid']:
            raise ValueError('DATA_SOURCE_SOP_MISMATCH')
        if file_sha(mapping['native_hu_volume_path'])!=p['native_volume_sha256']:raise ValueError('NATIVE_HU_HASH_MISMATCH')
        hu=np.load(mapping['native_hu_volume_path'],mmap_mode='r',allow_pickle=False)[z]
        refs=result['candidate_maps']['evaluation_native_npz'];e1={};e2=None;bound=[]
        for ref in refs:
            scores,reliable=validate_native_bundle(ref,p,hu.shape)
            if ref['algorithm']=='E1':e1[int(ref['scale'])]=(scores,reliable)
            elif ref['algorithm']=='E2':e2=(scores,reliable)
            else:raise ValueError('UNKNOWN_ALGORITHM_ASSET')
            bound.append(ref)
        if set(e1)!={16,32,64} or e2 is None:raise ValueError('MISSING_NATIVE_ALGORITHM_ASSETS')
        if result['E2']['status'] in {'NO_FEASIBLE_MASK','NO_RELIABLE_RESPONSE'} and (e2[1].any() or np.any(e2[0])):
            raise ValueError('E2_ABSTENTION_HAS_FABRICATED_MASK_OR_SCORE')
        references=[];reference_receipts=[]
        for union in sop['category_unions']:
            path=(gt_root/union['mask_path']).resolve()
            if gt_root not in path.parents or file_sha(path)!=union['mask_sha256']:raise ValueError('OFFICIAL_REFERENCE_HASH_OR_PATH_MISMATCH')
            with Image.open(path) as image:mask=np.array(image.convert('L'))>0
            if mask.shape!=hu.shape:raise ValueError('OFFICIAL_REFERENCE_NATIVE_SHAPE_MISMATCH')
            references.append((union['category'],mask))
            reference_receipts.append({'path':str(path),'sha256':union['mask_sha256'],'category':union['category'],'semantics':union['semantics']})
        baseline=result['E1']['records'][0]['baseline_logits'] if result['E1']['records'] else None
        summary={'case_index':p['case_index'],'native_slice_index':z,'E1_status':result['E1']['status'],'E2_status':result['E2']['status'],
                 'baseline_logits':baseline,'E1_model_id':E1_MODEL_ID,'E2_model_id':E2_MODEL_ID,
                 'E1_candidates':len(result['E1']['candidates']),'E2_candidates':len(result['E2']['candidates']),
                 'actual_model_calls':result['actual_model_calls'],'actual_classifier_forwards':result['actual_classifier_forwards'],
                 'source_result_sha256':record['result_sha256'],'source_geometry_sha256':p['geometry']['sha256'],
                 'source_ct_sha256':p['source_ct_sha256'],'coverage_status':sop['coverage_status'],'annotation_complete':sop['annotation_complete'],
                 'unannotated_region_status':sop['unannotated_region_status'],'GT_categories':[u['category'] for u in sop['category_unions']],
                 'native_plot_shape_rc':list(hu.shape),'source_model_elapsed_seconds':result['elapsed_seconds']}
        png=render_comparison(hu,e1,e2,references,geometry,p['case_index'],{'E1':summary['E1_status'],'E2':summary['E2_status']})
        artifacts[f"case-{p['case_index']}-comparison.png"]=png
        cases.append({'summary':summary,'source_result_path':record['result_path'],'source_sop_uid':p['source_sop_uid'],
                      'source_study_uid':p['study_uid'],'source_series_uid':p['series_uid'],'native_algorithm_assets':bound,
                      'official_reference_assets':reference_receipts})
    manifest={'schema':'EPI-NEXT-LOCAL-RESULT-BINDING-1','status':'LOCAL_RESEARCH_COMPARISON_READY',
              'source_git_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
              'run_delivery_sha256':args.run_sha,'prepared_delivery_sha256':delivery['prepared_delivery_sha256'],
              'data_delivery_sha256':delivery['data_delivery_sha256'],'checkpoint_sha256':delivery['checkpoint_sha256'],
              'cases':cases,'model_calls_by_binding':0,'GT_recalculated':False,'GT_filtered':False,
              'new_metrics_calculated':False,'independent_DATA_mapping_QA':'PASS_AS_PUBLISHED_BY_DATA',
              'independent_DATA_evaluation_path':str(args.evaluation),
              'independent_DATA_evaluation_sha256':'55dbe1c71dbb3836f28ae3a4352f2a9c0d257b403b97e6ac4a7f65929856b477',
              'hospital_default_algorithm':None,'hospital_display_authorized':False,'clinical_validation':'NOT RUN'}
    artifacts['binding_manifest.json']=canonical_json(manifest);artifacts['index.html']=comparison_html(cases)
    persist_run(output.parent,run_id,artifacts)
    return {'status':manifest['status'],'index_path':str(output/'index.html'),'receipt_sha256':file_sha(output/'receipt.json'),
            'binding_manifest_sha256':file_sha(output/'binding_manifest.json'),'new_model_calls':0}


def readback(root):
    root=Path(root)
    observed=reconcile_run(root.parent,root.name)
    if observed['state']!='COMMITTED':raise RuntimeError('BINDING_RECONCILIATION_'+observed['state'])
    manifest=json.loads((root/'binding_manifest.json').read_bytes())
    for case in manifest['cases']:
        if file_sha(case['source_result_path'])!=case['summary']['source_result_sha256']:raise ValueError('UPSTREAM_RESULT_CHANGED')
        for reference in case['native_algorithm_assets']:
            if file_sha(reference['path'])!=reference['sha256']:raise ValueError('NATIVE_ASSET_CHANGED')
        for reference in case['official_reference_assets']:
            if file_sha(reference['path'])!=reference['sha256']:raise ValueError('OFFICIAL_REFERENCE_CHANGED')
        with Image.open(root/f"case-{case['summary']['case_index']}-comparison.png") as image:
            image.verify()
    return {'state':'COMMITTED','binding_manifest_sha256':file_sha(root/'binding_manifest.json'),'asset_hashes':observed['receipt']['artifact_hashes']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build')
    for key in ('run-delivery','data-delivery','evaluation','output'):build.add_argument('--'+key,type=Path,required=True)
    build.add_argument('--run-sha',required=True)
    read=sub.add_parser('readback');read.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();result=build_comparison(args) if args.command=='build' else readback(args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
