"""Metadata-only whole-Series geometry/cost planning; no Torch or CT pixels."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import resource
import time

import numpy as np

from .encoder_real_input import DATA_V3_SHA, read_bound_json
from .encoder_ctfm_mps_smoke import file_sha, write_new

M2_MANIFEST_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
DATA_QA_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
MODEL_CONFIG = dict(blocks_down=[1,2,2,4,4], in_channels=1, init_filters=32, spatial_dims=3)
FEATURE_STRIDE = 16


def axis_starts(length, window, step, alignment=FEATURE_STRIDE):
    if any(not isinstance(v,int) or v < 1 for v in (length,window,step,alignment)):
        raise ValueError('positive integer geometry required')
    if window % alignment or step % alignment or step > window:
        raise ValueError('window/step must align to feature lattice and cover without gaps')
    padded = max(window, math.ceil(length/alignment)*alignment)
    starts = list(range(0,padded-window+1,step))
    if starts[-1] != padded-window:
        starts.append(padded-window)
    return padded,starts


def feature_cell_widths(length, stride=FEATURE_STRIDE):
    """Voronoi proxy cells clipped to voxel edges; these are not receptive fields."""
    centers = np.arange(math.ceil(length/stride),dtype=float)*stride
    edges = np.r_[-.5,(centers[:-1]+centers[1:])/2,length-.5]
    widths = np.diff(edges)
    if np.any(widths <= 0) or not np.isclose(widths.sum(),length):
        raise ValueError('invalid proxy cell partition')
    return widths


def window_plan(shape,window,step):
    shape = tuple(int(n) for n in shape)
    axes = [axis_starts(n,window,step) for n in shape]
    padded = [a[0] for a in axes]; starts = [a[1] for a in axes]
    voxel_counts=[]; feature_counts=[]; widths=[]
    for n,p,ss in zip(shape,padded,starts):
        vc=np.zeros(n,dtype=np.uint16);fc=np.zeros(p//FEATURE_STRIDE,dtype=np.uint16)
        for s in ss:
            vc[s:min(s+window,n)]+=1
            fc[s//FEATURE_STRIDE:(s+window)//FEATURE_STRIDE]+=1
        if not np.all(vc) or not np.all(fc):raise ValueError('uncovered voxel/feature coordinate')
        voxel_counts.append(vc); feature_counts.append(fc); widths.append(feature_cell_widths(n))
    windows=[];mass=0.;weight_min=1.;weight_max=0.
    for start in itertools.product(*starts):
        # Each duplicate nominal feature center gets 1/multiplicity. Patient
        # weight is its clipped proxy cell volume / total native voxel volume.
        pieces=[]
        for a,s in enumerate(start):
            lo=s//FEATURE_STRIDE;hi=(s+window)//FEATURE_STRIDE
            pieces.append(widths[a][lo:hi]/feature_counts[a][lo:hi])
        w=np.einsum('i,j,k->ijk',*pieces)/math.prod(shape)
        mass+=float(w.sum());weight_min=min(weight_min,float(w.min()));weight_max=max(weight_max,float(w.max()))
        stop=[min(s+window,n) for s,n in zip(start,shape)]
        windows.append(dict(start_spl=list(start),valid_stop_spl=stop,
            new_air_padding_after=[max(0,s+window-n) for s,n in zip(start,shape)]))
    if abs(mass-1)>1e-10:raise ValueError('overlap-normalized patient weights do not sum to one')
    features_per_window=(window//FEATURE_STRIDE)**3
    grid=math.prod(p//FEATURE_STRIDE for p in padded)
    return dict(shape_spl=list(shape),padded_shape_spl=padded,window=window,step=step,
        axis_starts=starts,window_count=len(windows),windows=windows,
        native_voxel_count=math.prod(shape),geometric_uncovered_native_voxels=0,
        nominal_feature_grid_shape=[p//FEATURE_STRIDE for p in padded],
        feature_center_multiplicity_min=math.prod(int(c.min()) for c in feature_counts),
        feature_center_multiplicity_max=math.prod(int(c.max()) for c in feature_counts),
        factorized_feature_center_counts=[c.tolist() for c in feature_counts],
        factorized_native_proxy_cell_widths=[w.tolist() for w in widths],
        normalized_patient_weight_sum=mass,local_feature_weight_min=weight_min,local_feature_weight_max=weight_max,
        aggregation='sum_j cell_volume(j)/native_volume * mean_{windows containing nominal center j}(f_window,j)',
        weight_scope='geometric proxy partition; not independent16-cube cells or receptive-field coverage',
        all_window_feature_storage_fp32_bytes=len(windows)*512*features_per_window*4,
        all_window_input_storage_fp32_bytes=len(windows)*window**3*4,
        stitched_coarse_feature_fp32_bytes=grid*512*4,
        stitched_coarse_accumulator_fp64_bytes=grid*512*8,
        stitched_weight_fp64_bytes=grid*8,
        prohibited_dense_native_512channel_fp32_bytes=math.prod(shape)*512*4,
        batch_size=1,sw_device='MPS only after shape approval',stitch_device='CPU streaming coarse grid',
        patch_full_volume_equivalence='NOT ASSERTED',real_encoder_forwards=0)


def full_fov_ledger(old,target=(128,128,128)):
    native_shape=np.asarray(old['oriented_shape'],dtype=int);target=np.asarray(target,dtype=int)
    ratio=native_shape/target
    model_to_orient=np.eye(4);model_to_orient[:3,:3]=np.diag(ratio)
    model_to_orient[:3,3]=.5*ratio-.5
    orient_to_native=np.asarray(old['orient_to_native'])
    model_to_native=orient_to_native@model_to_orient
    native_to_lps=np.asarray(old['patch_to_lps'])@np.linalg.inv(np.asarray(old['patch_to_native']))
    model_to_lps=native_to_lps@model_to_native
    # Match all voxel-edge corners, not just the transform's own inverse.
    points=np.array(list(itertools.product(*[(-.5,float(n)-.5) for n in target])))
    h=np.column_stack([points,np.ones(len(points))]).T
    mapped=model_to_orient@h
    expected=np.array(list(itertools.product(*[(-.5,float(n)-.5) for n in native_shape])))
    edge_error=float(np.max(np.abs(mapped[:3].T-expected)))
    roundtrip=float(np.max(np.abs(np.linalg.inv(model_to_native)@model_to_native@h-h)))
    if max(edge_error,roundtrip)>1e-8:raise ValueError('full-FOV edge/inverse geometry failed')
    return dict(input_shape=[1,1,*target.tolist()],feature_shape=[1,512,*(target//16).tolist()],
        native_shape_spl=native_shape.tolist(),resample_shape_spl=target.tolist(),
        resampling='separable volume-cell area average; deterministic voxel-edge preserving, float32 output',
        model_to_orient=model_to_orient.tolist(),model_to_native=model_to_native.tolist(),
        model_to_lps=model_to_lps.tolist(),native_to_model=np.linalg.inv(model_to_native).tolist(),
        nominal_feature_to_native=(model_to_native@np.diag([16,16,16,1])).tolist(),
        proposed_spacing_spl_mm=(np.asarray(old['spacing_spl_mm'])*ratio).tolist(),
        voxel_edge_extent_mm=(np.asarray(old['spacing_spl_mm'])*native_shape).tolist(),
        edge_corner_max_error_voxels=edge_error,inverse_max_error_voxels=roundtrip,
        declared_support='all voxels of the approved selected Series FOV; anatomical completeness unknown',
        geometric_uncovered_native_voxels=0,crop='NONE_FULL_APPROVED_SERIES_FOV',new_input_padding='NONE',
        patient_aggregation='GAP of last-stage512-channel spatial features; reuse CaseLinearHead on pooled vector',
        normalization='clip native HU[-1024,2048] then scale to[0,1] before deterministic area averaging',
        dtype='float32',small_target_information_loss='UNVALIDATED; anti-aliased coarse averages attenuate small targets',
        encoding_status='NOT RUN',real_encoder_forwards=0)


def area_matrix(source,target):
    if not 1<=target<=source:raise ValueError('downsampling only')
    left=np.arange(target)*source/target;right=(np.arange(target)+1)*source/target
    cells=np.arange(source)
    return np.maximum(0,np.minimum(right[:,None],cells+1)-np.maximum(left[:,None],cells))/(source/target)


def area_resize_control(volume,target):
    """Small synthetic control only; no real-pixel CLI or model inference."""
    value=np.asarray(volume,dtype=np.float64)
    for axis,n in enumerate(target):
        matrix=area_matrix(value.shape[axis],int(n))
        value=np.moveaxis(np.tensordot(matrix,value,axes=(1,axis)),0,axis)
    return value


def toy_conv(volume):
    pad=np.pad(volume,1);out=np.zeros(tuple((n+1)//2 for n in volume.shape))
    for delta in itertools.product(range(3),repeat=3):
        out+=pad[tuple(slice(d,d+n,2) for d,n in zip(delta,volume.shape))]/27
    return out


def synthetic_controls():
    constant=area_resize_control(np.full((17,19,23),.37),(7,8,9))
    impulse=np.zeros((32,32,32));impulse[15,16,17]=1
    coarse=area_resize_control(impulse,(8,8,8))
    rng=np.random.default_rng(17);volume=rng.random((32,32,32))
    whole=toy_conv(volume);numerator=np.zeros_like(whole);count=np.zeros_like(whole)
    for start in itertools.product((0,8,16),repeat=3):
        patch=volume[tuple(slice(s,s+16) for s in start)]
        output=toy_conv(patch)
        dest=tuple(slice(s//2,s//2+8) for s in start)
        numerator[dest]+=output;count[dest]+=1
    merged=numerator/count;difference=np.abs(whole-merged)
    if np.any(count<1):raise ValueError('synthetic nominal feature grid has holes')
    return dict(status='PASS',seed=17,constant_downsample_max_absolute_error=float(np.max(np.abs(constant-.37))),
        one_voxel_impulse_before_peak=1.,one_voxel_impulse_after_peak=float(coarse.max()),
        impulse_volume_integral_absolute_error=float(abs(coarse.sum()*64-1)),
        toy_operator='numpy3x3x3 mean Conv/stride2/pad1; not CT-FM',
        toy_whole_and27_window_operator_evaluations=28,toy_uncovered_feature_centers=0,
        toy_whole_vs_overlap_average_max_abs_error=float(difference.max()),
        toy_whole_vs_overlap_average_mean_abs_error=float(difference.mean()),
        conclusion='overlap normalization preserves weights, not full-volume operator equivalence; no clinical power inferred',
        actual_ctfm_encoder_forwards=0,backward_calls=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--m2-run',type=Path,required=True)
    parser.add_argument('--data-qa',type=Path,required=True);parser.add_argument('--private-output',type=Path,required=True)
    parser.add_argument('--public-output',type=Path,required=True)
    args=parser.parse_args();started=time.perf_counter();os.umask(0o077)
    data=read_bound_json(args.data,DATA_V3_SHA)
    manifest=read_bound_json(args.m2_run/'manifest.json',M2_MANIFEST_SHA)
    qa=read_bound_json(args.data_qa,DATA_QA_SHA)
    if (data['case_count']!=3 or data['sop_count']!=715 or manifest['real_case_count']!=3
            or qa['encoder_manifest_sha256']!=M2_MANIFEST_SHA):raise ValueError('fixed three-case evidence mismatch')
    args.private_output.mkdir(parents=True,exist_ok=False,mode=0o700)
    cases=[];ledgers=[]
    strategies=[('old64_half_overlap',64,32),('native96_half_overlap',96,48),
                ('native128_half_overlap',128,64),('native128_minimum_overlap',128,128)]
    for index,mapping in enumerate(data['spatial_mapping']['cases'],1):
        old_path=args.m2_run/f'case_{index}_ledger.json'
        old=read_bound_json(old_path,manifest['prepared_ledger_hashes'][f'case_{index}'])
        if (old['native_volume_sha256']!=mapping['native_hu_volume_sha256']
                or old['native_shape_krc']!=mapping['shape_krc']):raise ValueError('native metadata drift')
        full=full_fov_ledger(old);plans={name:window_plan(old['oriented_shape'],w,s) for name,w,s in strategies}
        private=dict(case_index=index,DATA_v3_sha256=DATA_V3_SHA,M2_input_ledger_sha256=file_sha(old_path),
            model_full_fov_proposal=full,window_plans=plans)
        private_path=args.private_output/f'case_{index}_volume_geometry.json';write_new(private_path,private)
        ledgers.append(dict(case_index=index,path=str(private_path.resolve()),sha256=file_sha(private_path)))
        full_public={k:v for k,v in full.items() if k not in ('model_to_orient','model_to_native','model_to_lps','native_to_model','nominal_feature_to_native')}
        windows={name:{k:v for k,v in plan.items() if k not in ('windows','factorized_feature_center_counts','factorized_native_proxy_cell_widths')} for name,plan in plans.items()}
        old_count=64**3;native_count=math.prod(old['oriented_shape'])
        cases.append(dict(case_index=index,native_shape_spl=old['oriented_shape'],native_spacing_spl_mm=old['spacing_spl_mm'],
            prior_actual64_center_encoded_input_voxels=old_count,prior_actual64_center_unencoded_input_voxels=native_count-old_count,
            prior_actual64_center_input_fraction=old_count/native_count,full_fov_proposal=full_public,window_geometry_dry_run=windows,
            this_wave_real_encoded_voxels=0,this_wave_unencoded_native_voxels=native_count))
    import sys
    if 'torch' in sys.modules:raise RuntimeError('dry-run must not import Torch')
    public=dict(schema='CTFM_INPUT_AND_VOLUME_PROTOCOL_V2',status='PASS',scope='metadata geometry/cost and small numpy controls only',
        data_delivery_sha256=DATA_V3_SHA,M2_manifest_sha256=M2_MANIFEST_SHA,independent_DATA_QA_sha256=DATA_QA_SHA,
        source_sha256=file_sha(__file__),checkpoint_sha256=manifest['synthetic'][0]['result']['checkpoint_sha256'],
        official_model_config=MODEL_CONFIG,actual_nominal_lattice=manifest['synthetic'][0]['result']['feature_lattice'],
        cases=cases,private_geometry_ledgers=ledgers,synthetic_controls=synthetic_controls(),
        full_window_counts={name:sum(c['window_geometry_dry_run'][name]['window_count'] for c in cases) for name,_,_ in strategies},
        new_real_encoder_calls=0,new_mps_calls=0,backward_calls=0,real_pixels_reopened=False,GT_or_new_label_body_read=False,
        preferred_increment='one whole-approved-Series-FOV128cube per case; experimental geometry compression, not clinical input validation',
        incremental_encoding_status='NOT RUN',incremental_budget_status='BLOCKED_PENDING_APPROVAL',
        proposed_new128_per_case_calls=dict(cpu_warmup=1,cpu_timed=3,mps_warmup=1,mps_timed=3),
        proposed_new128_total_encoder_calls=24,proposed_timed_full_pairs=9,proposed_batch_size=1,
        proposed_timeout_seconds_per_trial=120,proposed_total_soft_timeout_seconds=1200,
        proposed_rss_limit_bytes=6*1024**3,proposed_mps_driver_limit_bytes=6*1024**3,
        proposed_total_output_limit_bytes=128*1024**2,
        proposed_inputs_and18_timed_features_fp32_bytes=3*128**3*4+18*512*8**3*4,
        new128_runtime_seconds=None,new128_activation_peak_bytes=None,
        minimum_overlap_full_windows_plus_three_shape_checks_required_calls=96-3+24,
        head_training='NOT RUN',F0='BLOCKED',F1='BLOCKED',remote_RTX3090='PAUSED',
        elapsed_seconds=time.perf_counter()-started,peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    args.public_output.parent.mkdir(parents=True,exist_ok=True)
    write_new(args.public_output,public)
    print(json.dumps(dict(status='PASS',output=str(args.public_output),sha256=file_sha(args.public_output),
        full_window_counts=public['full_window_counts'],new_real_encoder_calls=0,elapsed_seconds=public['elapsed_seconds'],peak_process_rss_bytes=public['peak_process_rss_bytes'])))


if __name__=='__main__':main()
