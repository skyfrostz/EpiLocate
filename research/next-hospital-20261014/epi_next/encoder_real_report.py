"""Package existing private M2 evidence; no Torch import or new inference."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics

import numpy as np
from .encoder_ctfm_mps_smoke import file_sha,write_new
from .encoder_real_smoke import full_compare


def package(run,output):
    run=Path(run);output=Path(output)
    manifest=json.loads((run/'manifest.json').read_bytes())
    config=json.loads((run/'config.json').read_bytes())
    if file_sha(run/'config.json')!=manifest['config_sha256']: raise ValueError('config SHA mismatch')
    if file_sha(run/'consumer_receipt.json')!=manifest['consumer_receipt_sha256']: raise ValueError('consumer SHA mismatch')
    if manifest['source_sha256']!=file_sha(Path(__file__).with_name('encoder_real_smoke.py')) or manifest['input_source_sha256']!=file_sha(Path(__file__).with_name('encoder_real_input.py')):
        raise ValueError('executed source bytes changed')
    rows=[];delivery_cases=[]
    all_trials=manifest['synthetic']+manifest['real']
    for n,trial in enumerate(all_trials):
        kind='synthetic' if n<2 else 'real_center_block'
        ordinal=n-1 if kind=='real_center_block' else None
        folder=run/(f'synthetic_{config["synthetic_sizes"][n]}' if kind=='synthetic' else f'real_case_{ordinal}')
        r=json.loads((folder/'receipt.json').read_bytes())
        if r!=trial['result'] or r['status']!='PASS' or trial['exit_code']!=0 or trial['process_running']:
            raise ValueError('incomplete or mismatched actual execution receipt')
        if r['config_sha256']!=manifest['config_sha256'] or r['actual_encoder_calls']!=8:
            raise ValueError('trial config/call count changed')
        for name,expected in r['output_hashes'].items():
            if file_sha(folder/name)!=expected: raise ValueError('full feature output SHA mismatch')
        checks=[]
        for i in range(3):
            a=np.load(folder/f'cpu_features_{i}.npy',allow_pickle=False)
            b=np.load(folder/f'mps_features_{i}.npy',allow_pickle=False)
            check=full_compare(a,b,config['tolerance'])
            if check!=r['comparisons'][i] or check['status']!='PASS': raise ValueError('full numeric recomputation mismatch')
            checks.append(check)
        row=dict(trial=folder.name,kind=kind,case_index=ordinal,status='PASS',input_shape=r['input_shape'],feature_shape=r['feature_shape'],
            comparisons=checks,loading_seconds=r['loading_seconds'],device_transfer_seconds=r['transfer_seconds'],
            cpu_warmup_seconds=r['cpu_warmup_seconds'],mps_warmup_seconds=r['mps_warmup_seconds'],
            cpu_inference_seconds=r['cpu_inference_seconds'],mps_inference_seconds=r['mps_inference_seconds'],
            cpu_inference_mean_seconds=statistics.mean(r['cpu_inference_seconds']),mps_inference_mean_seconds=statistics.mean(r['mps_inference_seconds']),
            readback_seconds=r['readback_seconds'],peak_process_rss_bytes=r['peak_process_rss_bytes'],mps_memory=r['mps_memory'],
            cpu_repeat_max_difference=r['cpu_repeat_max_difference'],mps_repeat_max_difference=r['mps_repeat_max_difference'],
            actual_encoder_calls=r['actual_encoder_calls'],module_observations=r['mps_warmup_module_observations'],
            cpu_module_tensors=r['cpu_module_tensors'],fallback_warning_detected=r['fallback_warning_detected'],warnings=r['warnings'],
            feature_lattice=r['feature_lattice'],source_sha256=r['source_sha256'],input_content_sha256=r['input_content_sha256'],
            output_hashes=r['output_hashes'],environment=r['environment'],subprocess_exit_code=trial['exit_code'],
            supervisor_elapsed_seconds=trial['elapsed_seconds'],failure_reason=None)
        if kind=='real_center_block':
            ledger_path=run/f'case_{ordinal}_ledger.json';ledger=json.loads(ledger_path.read_bytes())
            if file_sha(ledger_path)!=manifest['prepared_ledger_hashes'][f'case_{ordinal}']: raise ValueError('ledger SHA mismatch')
            if ledger['input_content_sha256']!=r['input_content_sha256']: raise ValueError('input/ledger content mismatch')
            # Public metadata contains no SOP identifiers, transforms or image pixels.
            row['geometry']={k:ledger[k] for k in ['crop_start_spl','spacing_spl_mm','voxel_edge_extent_mm',
                'center_offset_voxels_spl','roundtrip_max_voxel_error','lps_roundtrip_max_voxel_error',
                'lps_roundtrip_max_mm_error','independent_sample_checks','official_conformance']}
            row['input_ledger_sha256']=file_sha(ledger_path)
            delivery_cases.append(dict(case_index=ordinal,input_path=str((run/f'case_{ordinal}_input.npy').resolve()),
                input_sha256=manifest['prepared_input_hashes'][f'case_{ordinal}'],
                geometry_ledger_path=str(ledger_path.resolve()),geometry_ledger_sha256=file_sha(ledger_path),
                native_hu_volume_sha256=ledger['native_volume_sha256'],case_manifest_sha256=ledger['case_manifest_sha256'],
                cpu_feature_path=str((folder/'cpu_features_0.npy').resolve()),cpu_feature_sha256=r['output_hashes']['cpu_features_0.npy'],
                mps_feature_path=str((folder/'mps_features_0.npy').resolve()),mps_feature_sha256=r['output_hashes']['mps_features_0.npy'],
                feature_shape=r['feature_shape'],feature_to_native=ledger['feature_lattice']['feature_to_native'],
                feature_transform_scope='nominal k3/p1 stride16 convolution lattice; not lesion accuracy or full-volume equivalence'))
        rows.append(row)
    if len(rows)!=5 or sum(r['actual_encoder_calls'] for r in rows)!=40: raise ValueError('authorized trial scope incomplete')
    delivery=dict(schema='ENCODER_MODEL_INPUT_FEATURE_DELIVERY_V1',status='PASS',case_count=3,
        data_delivery_sha256=config['data_delivery_sha256'],config_sha256=manifest['config_sha256'],
        checkpoint_sha256=config['checkpoint_sha256'],cases=delivery_cases,
        requested_independent_consumer='DATA-EVAL spatial geometry QA',independent_DATA_QA='PENDING',
        clinical_efficacy='NOT RUN',head_training='NOT RUN',patch_full_volume_equivalence='NOT ASSERTED')
    delivery_path=run/'model_input_feature_delivery.json';write_new(delivery_path,delivery)
    output.mkdir(parents=True,exist_ok=False)
    common=dict(data_delivery_sha256=config['data_delivery_sha256'],run_manifest_sha256=file_sha(run/'manifest.json'),
        consumer_receipt_sha256=file_sha(run/'consumer_receipt.json'),config_sha256=manifest['config_sha256'],
        actual_run_source_sha256=manifest['source_sha256'],actual_preprocessing_source_sha256=manifest['input_source_sha256'],
        actual_run_git_sha=manifest['git_sha'],checkpoint_sha256=config['checkpoint_sha256'],
        model_revision='527b0d1c262b433396c85ff2de84c427b26945a1',actual_encoder_calls=40,
        real_case_count=3,remote_rtx_3090='PAUSED',clinical_metrics=None,pretraining_overlap_status='unknown')
    write_new(output/'MPS_COMPATIBILITY.json',dict(status='PASS',scope='new predeclared FP32 32/64 synthetic and three64 center blocks',
        predeclared_config=config,all_full_output_pairs_checked=15,independent_warmup_runs_per_device_per_trial=1,
        timed_repeats_per_device_per_trial=3,strict_fallback_disabled=True,
        internal_kernel_profiler='NOT RUN',old_M1_acceptance='UNCHANGED_EXPLORATORY',trials=rows,**common))
    write_new(output/'RESOURCE_BENCHMARK.json',dict(status='PASS',scope='bounded 32/64 synthetic and three64 center patches',
        trials=rows,rss_limit_bytes=config['rss_limit_bytes'],mps_driver_limit_bytes=config['mps_driver_limit_bytes'],timeout_seconds_per_trial=120,
        larger_volume_runs='NOT RUN',memory_caveat='sampled MPS high-water every20ms; whole child RSS; unified figures overlap',
        full_CT_speedup='NOT ASSERTED',**common))
    write_new(output/'THREE_CASE_SMOKE.json',dict(status='PASS',scope='three engineering center patches only; DATA-produced native HU reused',
        cases=rows[2:],geometry_selection_before_model_forward=True,raw_DICOM_decode='DATA v3 upstream technical PASS; not repeated',
        input_inverse_mapping='PASS',nominal_feature_lattice='469RF/16stride/0offset verified from loaded model',
        preprocessing_full_official_conformance=False,preprocessing_scope='official SPL/HU scaling; center crop/native anisotropic spacing variant',
        preprocessing_seconds=None,preprocessing_time_measurement='NOT SEPARATELY MEASURED',
        independent_DATA_spatial_QA='PENDING',model_input_feature_delivery_sha256=file_sha(delivery_path),
        GT_annotation_fields_parsed=False,GT_manifest_bytes_hashed_for_provenance=True,**common))
    write_new(output/'F0.json',dict(status='BLOCKED',reason='NO_TASK_MATCHED_AUTHORIZED_HEAD; CLINICAL_TARGET_LABELS_UNKNOWN; TRAINING_NOT_AUTHORIZED',
        existing_local_checkpoint_inventory='verified CT-FM encoder only; no task-matched head found',head_training='NOT RUN',
        training_checkpoint=None,raw_logits=None,class_prediction=None,spatial_coarse_candidate_map=None,
        model_version=None,encoder_version_available=common['model_revision'],clinical_metrics=None,
        training_proposal='F0_MINIMAL_TRAINING_PROPOSAL.md',**{k:v for k,v in common.items() if k!='clinical_metrics'}))
    print(json.dumps(dict(status='PASS',model_input_feature_delivery_path=str(delivery_path),
        model_input_feature_delivery_sha256=file_sha(delivery_path),public_output=str(output),new_model_calls=0)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();package(a.run,a.output)


if __name__=='__main__':main()
