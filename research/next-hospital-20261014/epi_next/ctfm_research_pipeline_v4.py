"""Versioned source-group CT-FM cache/head/evaluation entry.

Default CLI is read-only binding validation. Real execution requires new chief
approval, exclusive dispatch and the existing pinned shared supervisor.
The old patient-VERIFIED V1 contract and training entry are unchanged.
"""
from __future__ import annotations
import argparse
import ast
import gc
import hashlib
import importlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import time
import weakref

import numpy as np
from .ctfm_research_math_v4 import baselines, binary_metrics, probability, signed_f0
from .encoder_real_input import center_ledger
from .encoder_volume_dry_run import full_fov_ledger
from .encoder_volume_guard import stream_area_input
from .encoder_volume_runner import PrivateArtifacts

DATA_CONTRACT_SHA = '054b4f66baf0964ec7fdc9f01c26f522603ae9625fc7bde71f3f4acf0207c6a0'
MODEL_SHA = 'b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215'
SHARED_PACKAGE = 'epinext_wave1_recovery_chain_v1'
SHARED_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
COUNTS = {'train_weak': {'COVID-19': 10, 'CAP': 10, 'Normal': 20},
          'val_classification': {'COVID-19': 5, 'CAP': 5, 'Normal': 10}}
PHASES = {
    'cache': dict(forward=60, backward=0, updates=0, seconds=3600, per_case=120,
                  assets=128*1024**2, rss=5*1024**3),
    'train': dict(forward=100, backward=100, updates=100, seconds=120, per_case=None,
                  assets=16*1024**2, rss=1024**3),
    'evaluate': dict(forward=2, backward=0, updates=0, seconds=30, per_case=None,
                     assets=16*1024**2, rss=1024**3)}
PREPROCESS = dict(shape=[1,1,64,64,64], clip=[-1024,2048], scale=3072,
                  orientation='SPL', resample='voxel-edge area average', crop='NONE',
                  native_max_bytes=512*1024**2, downsampling_only=True)


class Blocked(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def safe_path(value):
    p = Path(value)
    if not p.is_absolute() or any(q.is_symlink() for q in (p, *p.parents)):
        raise Blocked('ABSOLUTE_NONSYMLINK_REFERENCE_REQUIRED')
    return p


def file_sha(path, check=lambda: None, limit=None):
    path = safe_path(path)
    if limit is not None and path.stat().st_size > limit:
        raise Blocked('BOUND_INPUT_SIZE_LIMIT')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            check()
            chunk = stream.read(1024*1024)
            if not chunk:
                return h.hexdigest()
            h.update(chunk)


def bound_json(ref, check=lambda: None):
    path = safe_path(ref['path'])
    if file_sha(path, check, 4*1024**2) != ref['sha256']:
        raise Blocked('BOUND_JSON_DIGEST_MISMATCH')
    return json.loads(path.read_bytes())


def source_closure():
    """Static local import closure, including lazy imports; no model import."""
    directory = Path(__file__).resolve().parent
    pending, found = [Path(__file__).resolve()], set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom) and node.level == 1:
                names = [node.module] if node.module else [alias.name for alias in node.names]
                for name in names:
                    child = directory/(name.split('.')[0]+'.py')
                    if child.is_file():
                        pending.append(child)
    return sorted(found)


def validate_records(records):
    """Consumer of DATA's unique manifest; never selects/splits/relabels cases."""
    if not isinstance(records, list) or len(records) != 60:
        raise Blocked('EXACT_60_DATA_RECORDS_REQUIRED_NO_SUBSET')
    seen_ids, seen_groups, tensors = set(), set(), set()
    counts = {s: {k: 0 for k in c} for s, c in COUNTS.items()}
    for row in records:
        required = {'record_id', 'source_group_id', 'source_group_status', 'split',
                    'task_label', 'source_diagnosis', 'label_provenance',
                    'tensor_artifact', 'geometry_ledger', 'research_status',
                    'source_dicom_identity_status', 'clinical_patient_independence_status',
                    'GEOMETRY_QA', 'complete_selected_stack', 'affine_LPS', 'spacing_ZYX_mm',
                    'cross_group_duplicate_audit', 'label_definition_id', 'pretraining_overlap_status',
                    'approved_consumer_use'}
        if not required.issubset(row):
            raise Blocked('DATA_CONSUMER_REQUIRED_FIELDS_MISSING:' + ','.join(sorted(required-set(row))))
        if (row['research_status'] != 'RESEARCH_READY_SOURCE_DEFINED_EXPLORATORY'
                or row['source_group_status'] != 'PUBLISHER_SOURCE_SUBJECT_LOCKED'
                or row['GEOMETRY_QA'] != 'PASS_COMPLETE_SELECTED_STACK'
                or row['complete_selected_stack'] is not True or row['cross_group_duplicate_audit'] != 'PASS'
                or row['clinical_patient_independence_status'] != 'UNKNOWN'
                or row['pretraining_overlap_status'] != 'UNKNOWN'
                or row['source_dicom_identity_status'] not in {'NOT_EVALUATED', 'SOURCE_DICOM_ID_NONCONFORMANT'}
                or row['label_definition_id'] != 'MD_SOURCE_DIAGNOSIS_WEAK_V1'
                or not row['label_provenance']):
            raise Blocked('DATA_RESEARCH_QUALIFICATION_REJECTED')
        s, diagnosis = row['split'], row['source_diagnosis']
        if s not in counts or diagnosis not in counts[s] or type(row['task_label']) is not int or row['task_label'] != int(diagnosis != 'Normal'):
            raise Blocked('DATA_LABEL_OR_SPLIT_MISMATCH')
        if not row['record_id'] or not row['source_group_id'] or row['record_id'] in seen_ids or row['source_group_id'] in seen_groups:
            raise Blocked('DUPLICATE_OR_EMPTY_SOURCE_GROUP')
        artifact = row['tensor_artifact']
        if artifact.get('axis_order') != 'Z,Y,X' or len(artifact.get('shape', [])) != 3 or min(artifact['shape']) < 64:
            raise Blocked('NATIVE_FULL_STACK_DOWNSAMPLING_REQUIRED')
        if artifact['sha256'] in tensors:
            raise Blocked('DUPLICATE_NATIVE_TENSOR')
        for ref in (artifact, row['geometry_ledger']):
            safe_path(ref['path'])
            if not re.fullmatch('[a-f0-9]{64}', ref['sha256']):
                raise Blocked('DATA_ASSET_SHA_REQUIRED')
        seen_ids.add(row['record_id']); seen_groups.add(row['source_group_id'])
        tensors.add(artifact['sha256']); counts[s][diagnosis] += 1
    if counts != COUNTS:
        raise Blocked('FIXED_SOURCE_CATEGORY_COUNTS_REQUIRED')
    return records


class Meter:
    """Local attempt/update receipt plus the existing durable shared call guard."""
    def __init__(self, phase, guard=None, delivery_root=None):
        self.phase, self.guard = phase, guard
        self.limits = PHASES[phase]
        self.started = time.monotonic()
        self.forward = self.backward = self.updates = 0
        self.returned_forward = self.returned_backward = 0
        self.returned_updates = 0
        self.case_started = None
        self.events = []
        self.delivery_root = safe_path(delivery_root) if delivery_root else None
        self.last_disk_check = 0.

    def check(self):
        if self.guard:
            self.guard.check()
        now = time.monotonic()
        if now-self.started >= self.limits['seconds']:
            raise Blocked('PHASE_WALL_LIMIT')
        if self.case_started is not None and now-self.case_started >= self.limits['per_case']:
            raise Blocked('CASE_WALL_LIMIT')
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = rss if sys.platform == 'darwin' else rss*1024
        if rss >= self.limits['rss']:
            raise Blocked('PROCESS_HIGH_WATER_RSS_LIMIT')
        if self.delivery_root and now-self.last_disk_check >= .05:
            # Reuse the existing complete scanner; three whole rescans on rename.
            view = type('DeliveryView', (), {'directory':self.delivery_root})()
            for _ in range(3):
                try:
                    snapshot = PrivateArtifacts._disk_snapshot(view)
                    break
                except FileNotFoundError:
                    continue
            else:
                raise Blocked('DELIVERY_SCAN_UNSTABLE')
            if sum(info[3] for info in snapshot.values()) >= 512*1024**2:
                raise Blocked('TOTAL_DELIVERY_LIMIT')
            self.last_disk_check = now

    def before(self, kind):
        self.check()
        if getattr(self, kind) >= self.limits[kind]:
            raise Blocked('LOCAL_CALL_OR_UPDATE_LIMIT')
        if self.guard and kind != 'updates':
            getattr(self.guard, 'before_'+kind)()
        setattr(self, kind, getattr(self, kind)+1)
        self.events.append(dict(kind=kind, attempt=getattr(self, kind), seconds=time.monotonic()-self.started))

    def begin(self, key):
        self.check()
        self.case_started = time.monotonic()
        if self.guard:
            self.guard.begin_case(key)

    def end(self):
        if self.guard:
            self.guard.end_case()
        self.case_started = None

    def report(self):
        return dict(phase=self.phase, attempted_forward=self.forward, attempted_backward=self.backward,
                    attempted_optimizer_updates=self.updates, optimizer_updates=self.returned_updates, returned_forward=self.returned_forward,
                    returned_backward=self.returned_backward, elapsed_seconds=time.monotonic()-self.started,
                    ru_maxrss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    ru_maxrss_unit='bytes' if sys.platform == 'darwin' else 'KiB',
                    events=self.events, scope='source-group exploratory; not clinical validation')


def prepare(row, meter):
    ref = row['tensor_artifact']
    if file_sha(ref['path'], meter.check, PREPROCESS['native_max_bytes']+4096) != ref['sha256']:
        raise Blocked('NATIVE_TENSOR_SHA_MISMATCH')
    volume = np.load(ref['path'], mmap_mode='r', allow_pickle=False)
    if volume.dtype != np.float32 or list(volume.shape) != ref['shape'] or volume.nbytes > PREPROCESS['native_max_bytes']:
        raise Blocked('NATIVE_TENSOR_SHAPE_DTYPE_OR_SIZE')
    geo = bound_json(row['geometry_ledger'], meter.check)
    if geo['GEOMETRY_QA'] != 'PASS_COMPLETE_SELECTED_STACK' or geo['shape'] != list(volume.shape) or geo['axis_order'] != 'Z,Y,X':
        raise Blocked('GEOMETRY_BINDING_MISMATCH')
    if (geo.get('PIXEL_QA') != 'PASS' or geo.get('RESCALE_QA') != 'PASS_DECLARED_HU'
            or geo.get('PROVENANCE_BOUND') is not True
            or geo.get('tensor_artifact') != ref
            or geo.get('source_diagnosis') != row['source_diagnosis']
            or geo.get('task_label') != row['task_label']):
        raise Blocked('BOUND_DATA_LEDGER_PIXEL_HU_PROVENANCE_REQUIRED')
    affine = np.asarray(geo['affine_LPS'], dtype=np.float64)
    if not np.array_equal(affine, row['affine_LPS']) or geo['spacing_ZYX_mm'] != row['spacing_ZYX_mm']:
        raise Blocked('CONSUMER_GEOMETRY_LEDGER_MISMATCH')
    if not np.allclose(np.linalg.norm(affine[:3,:3], axis=0), geo['spacing_ZYX_mm'], atol=1e-7, rtol=1e-7):
        raise Blocked('GEOMETRY_SPACING_MISMATCH')
    old = center_ledger(volume.shape, affine, patch_shape=(1,1,1))
    ledger = full_fov_ledger(old, target=(64,64,64))
    ledger.update(native_shape_ZYX=list(volume.shape), native_to_lps=affine.tolist(),
                  native_spacing_ZYX_mm=geo['spacing_ZYX_mm'], data_geometry_sha=row['geometry_ledger']['sha256'],
                  source_qa=dict(PIXEL_QA=geo['PIXEL_QA'],RESCALE_QA=geo['RESCALE_QA'],PROVENANCE_BOUND=True),
                  feature_lattice_semantics='nominal centers stride16 offset0; receptive field469 spans full input; not a lesion support',
                  encoding_status='PREPARED_NO_FORWARD_YET')
    oriented = volume.transpose(old['permutation'])
    for axis, flip in enumerate(old['flips']):
        if flip:
            oriented = np.flip(oriented, axis)
    value = stream_area_input(oriented, target=(64,64,64), check=meter.check)
    return value, ledger


def cache_phase(records, manifest_sha, config_sha, code_commit, model_sha, output, encoder, meter, *, evidence_type):
    from .encoder import FeatureCache, canonical_json
    import torch
    validate_records(records)
    store = PrivateArtifacts(safe_path(output), PHASES['cache']['assets'])
    cache = FeatureCache(store.directory/'features')
    rows = []
    for index, row in enumerate(records):
        meter.begin(row['record_id'])
        value, geometry = prepare(row, meter)
        prefix = f'case_{index:02d}'
        input_sha = store.array(prefix+'_input.npy', value)
        geometry_sha = store.json(prefix+'_geometry.json', geometry)
        identity = dict(input_sha=input_sha, model_sha=model_sha,
                        preprocess_sha=digest(encoded(PREPROCESS)), geometry_sha=geometry_sha,
                        config_sha=config_sha, code_sha=code_commit, split_manifest_sha=manifest_sha,
                        split='train' if row['split']=='train_weak' else 'observed_validation')
        tensor = torch.from_numpy(value)
        meter.before('forward')
        features = encoder(tensor)
        meter.returned_forward += 1
        meter.check()
        if features.device.type != 'cpu' or features.dtype != torch.float32 or tuple(features.shape) != (1,512,4,4,4) or not torch.isfinite(features).all():
            raise Blocked('FEATURE_SHAPE_DTYPE_DEVICE_OR_FINITE')
        # Existing immutable cache writes a temporary and hardlink. Reserve both.
        with store._write_lock:
            store.check_disk(2*(features.numel()*4+len(canonical_json(identity))+8192))
            key = cache.write(identity, features)
            cache_path = store.directory/'features'/(key+'.npz')
            store._asset_sizes['features/'+key+'.npz'] = cache_path.stat().st_size
            store.assets['features/'+key+'.npz'] = file_sha(cache_path, meter.check)
        gap = features.numpy().astype(np.float64).mean(axis=(2,3,4))
        gap_sha = store.array(prefix+'_gap512.npy', gap)
        rows.append(dict(record_id=row['record_id'], source_group_id=row['source_group_id'],
                         split=row['split'], source_diagnosis=row['source_diagnosis'], task_label=row['task_label'],
                         identity=identity, feature_key=key,
                         feature=dict(path=str(cache_path), sha256=store.assets['features/'+key+'.npz']),
                         gap=dict(path=str(store.directory/(prefix+'_gap512.npy')), sha256=gap_sha),
                         geometry=dict(path=str(store.directory/(prefix+'_geometry.json')), sha256=geometry_sha),
                         input=dict(path=str(store.directory/(prefix+'_input.npy')), sha256=input_sha),
                         seconds=time.monotonic()-meter.case_started))
        del tensor, features, value, gap
        meter.end()
    result = dict(schema='CTFM_RESEARCH_CACHE_RECEIPT_V4', status='PASS', evidence_type=evidence_type,
                  data_manifest_sha256=manifest_sha, config_sha256=config_sha, source_commit=code_commit,
                  model_sha256=model_sha, rows=rows, calls=meter.report(), medical_forward=60,
                  extra_pilot_or_warmup=0, medical_backward=0, clinical_patient_independence='UNKNOWN',
                  artifacts=store.assets.copy())
    store.json('cache-receipt.json', result)
    return result


def read_cache(receipt, records, manifest_sha, meter):
    from .encoder import FeatureCache
    validate_records(records)
    if receipt['schema'] != 'CTFM_RESEARCH_CACHE_RECEIPT_V4' or receipt['status'] != 'PASS' or receipt['data_manifest_sha256'] != manifest_sha or len(receipt['rows']) != 60:
        raise Blocked('CACHE_RECEIPT_BINDING')
    gaps, spatial, geometries = [], [], []
    models, configs, commits, preprocess = set(), set(), set(), set()
    for row, cached in zip(records, receipt['rows']):
        if any(cached[k] != row[k] for k in ('record_id','source_group_id','split','task_label','source_diagnosis')):
            raise Blocked('CACHE_RECORD_BINDING')
        identity = cached['identity']
        if (identity['split_manifest_sha'] != manifest_sha or identity['model_sha'] != receipt['model_sha256']
                or identity['config_sha'] != receipt['config_sha256'] or identity['code_sha'] != receipt['source_commit']
                or identity['preprocess_sha'] != digest(encoded(PREPROCESS))
                or identity['split'] != ('train' if row['split']=='train_weak' else 'observed_validation')
                or identity['geometry_sha'] != cached['geometry']['sha256']
                or identity['input_sha'] != cached['input']['sha256']):
            raise Blocked('CACHE_IDENTITY_BINDING')
        for name in ('feature','gap','geometry','input'):
            if file_sha(cached[name]['path'], meter.check) != cached[name]['sha256']:
                raise Blocked('CACHE_ASSET_DIGEST_MISMATCH')
        path = safe_path(cached['feature']['path'])
        if path.name != cached['feature_key']+'.npz':
            raise Blocked('CACHE_KEY_PATH_MISMATCH')
        f = FeatureCache(path.parent).read(identity).numpy()
        gap = np.load(cached['gap']['path'], allow_pickle=False)
        expected = f.astype(np.float64).mean(axis=(2,3,4))
        if f.shape != (1,512,4,4,4) or f.dtype != np.float32 or gap.shape != (1,512) or gap.dtype != np.float64 or not np.array_equal(gap, expected):
            raise Blocked('CACHE_GAP_SPATIAL_MISMATCH')
        geometry = bound_json(cached['geometry'], meter.check)
        if (geometry['input_shape'] != [1,1,64,64,64] or geometry['feature_shape'] != [1,512,4,4,4]
                or geometry['crop'] != 'NONE_FULL_APPROVED_SERIES_FOV'
                or geometry['data_geometry_sha'] != row['geometry_ledger']['sha256']
                or geometry['source_qa'] != dict(PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',PROVENANCE_BOUND=True)):
            raise Blocked('CACHE_GEOMETRY_SCOPE')
        gaps.append(gap[0]); spatial.append(f); geometries.append(geometry)
        models.add(identity['model_sha']); configs.add(identity['config_sha'])
        commits.add(identity['code_sha']); preprocess.add(identity['preprocess_sha'])
    if any(len(values) != 1 for values in (models, configs, commits, preprocess)):
        raise Blocked('MIXED_CACHE_VERSION')
    return np.stack(gaps), spatial, geometries


def train_phase(records, receipt, manifest_sha, cache_receipt_sha, output, meter):
    import torch
    from .encoder import CaseLinearHead
    gap, _, _ = read_cache(receipt, records, manifest_sha, meter)
    mask = np.array([r['split']=='train_weak' for r in records])
    x = torch.from_numpy(gap[mask]).float()
    labels = torch.tensor([r['task_label'] for r in records], dtype=torch.long)[mask]
    store = PrivateArtifacts(safe_path(output), PHASES['train']['assets'])
    losses = []
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        head = CaseLinearHead(512, 2)
        head.mean.copy_(x.mean(0))
        head.scale.copy_(x.std(0, unbiased=False).clamp_min(1e-6))
        optimizer = torch.optim.AdamW(head.parameters(), lr=.001, weight_decay=.0001)
        for _ in range(100):
            optimizer.zero_grad(set_to_none=True)
            meter.before('forward')
            logits = head(x)
            meter.returned_forward += 1
            loss = torch.nn.functional.cross_entropy(logits, labels, reduction='mean')
            if not torch.isfinite(loss):
                raise Blocked('NONFINITE_TRAIN_LOSS')
            meter.before('backward')
            loss.backward()
            meter.returned_backward += 1
            if any(p.grad is None or not torch.isfinite(p.grad).all() for p in head.parameters()):
                raise Blocked('NONFINITE_OR_ABSENT_GRADIENT')
            # Reserve update immediately before call; count success after return.
            meter.before('updates')
            optimizer.step()
            meter.returned_updates += 1
            losses.append(float(loss.detach()))
    meter.check()
    if (meter.forward, meter.backward, meter.returned_updates) != (100,100,100):
        raise Blocked('NO_PARTIAL_FINAL_CHECKPOINT')
    head.eval()
    state = {name: tensor.detach().numpy().copy() for name,tensor in head.state_dict().items()}
    assets = {}
    for name, value in state.items():
        fname = name.replace('.', '_')+'.npy'
        sha = store.array(fname, value)
        assets[name] = dict(path=str(store.directory/fname), sha256=sha)
    result = dict(schema='CTFM_RESEARCH_HEAD_CHECKPOINT_V4', status='PASS', evidence_type=receipt['evidence_type'], seed=17,
                  optimizer='AdamW', learning_rate=.001, weight_decay=.0001, batch=40,
                  standardization='train-only FP32 population std floor1e-6',
                  training_dtype='float32', evaluation_dtype='float64; promote final FP32 parameters',
                  final_update=100, selection='final fixed update; no validation model selection',
                  threshold=.5, tie='Normal', losses=losses, state=assets,
                  cache_receipt_sha256=cache_receipt_sha, data_manifest_sha256=manifest_sha,
                  model_sha256=receipt['model_sha256'], calls=meter.report(), medical_forward=0,
                  clinical_patient_independence='UNKNOWN', calibration='UNCALIBRATED')
    store.json('head-checkpoint.json', result)
    return result


def evaluate_phase(records, receipt, checkpoint, manifest_sha, cache_receipt_sha, checkpoint_sha, output, meter):
    import torch
    from .encoder import CaseLinearHead
    gap, spatial, geometry = read_cache(receipt, records, manifest_sha, meter)
    if (checkpoint['schema'] != 'CTFM_RESEARCH_HEAD_CHECKPOINT_V4' or checkpoint['status'] != 'PASS'
            or checkpoint['data_manifest_sha256'] != manifest_sha or checkpoint['cache_receipt_sha256'] != cache_receipt_sha
            or checkpoint['model_sha256'] != receipt['model_sha256']
            or checkpoint['final_update'] != 100 or checkpoint['seed'] != 17 or checkpoint['threshold'] != .5
            or checkpoint['optimizer'] != 'AdamW' or checkpoint['tie'] != 'Normal'):
        raise Blocked('FINAL_HEAD_CHECKPOINT_BINDING')
    state = {}
    for name, ref in checkpoint['state'].items():
        if file_sha(ref['path'], meter.check, 64*1024) != ref['sha256']:
            raise Blocked('HEAD_ASSET_SHA')
        array = np.load(ref['path'], allow_pickle=False)
        if array.dtype != np.float32 or not np.isfinite(array).all():
            raise Blocked('HEAD_STATE_DTYPE_FINITE')
        state[name] = torch.from_numpy(array.copy()).double()
    with torch.random.fork_rng(devices=[]):
        head = CaseLinearHead(512,2).double()
    head.load_state_dict(state, strict=True); head.eval()
    store = PrivateArtifacts(safe_path(output), PHASES['evaluate']['assets'])
    y = np.array([r['task_label'] for r in records])
    train_mask = np.array([r['split']=='train_weak' for r in records])
    scores = np.zeros(60); logits_all = np.zeros((60,2)); metrics = {}
    for split in ('train_weak','val_classification'):
        mask = np.array([r['split']==split for r in records])
        meter.before('forward')
        with torch.no_grad():
            logits = head(torch.from_numpy(gap[mask])).numpy()
        meter.returned_forward += 1
        meter.check()
        logits_all[mask] = logits; scores[mask] = probability(logits)
        metrics[split] = dict(model=binary_metrics(y[mask],scores[mask]), baselines=baselines(y[train_mask],y[mask]))
    f0 = []
    for i, row in enumerate(records):
        meter.check()
        contribution, bias, rebuilt, error = signed_f0(spatial[i], state['linear.weight'].numpy(),
            state['linear.bias'].numpy(), state['mean'].numpy(), state['scale'].numpy())
        if not np.allclose(rebuilt[0], logits_all[i], atol=1e-10, rtol=1e-12):
            raise Blocked('F0_EVALUATED_LOGIT_MISMATCH')
        centers = np.array(list(itertools.product(range(4), repeat=3)),dtype=float)
        homogeneous = np.column_stack([centers,np.ones(64)])
        native = homogeneous @ np.asarray(geometry[i]['nominal_feature_to_native']).T
        lps = native @ np.asarray(geometry[i]['native_to_lps']).T
        back = native @ np.linalg.inv(np.asarray(geometry[i]['nominal_feature_to_native'])).T
        lps_back = lps @ np.linalg.inv(np.asarray(geometry[i]['native_to_lps'])).T
        inverse_error = float(max(np.max(np.abs(back-homogeneous)),np.max(np.abs(lps_back-native))))
        if inverse_error > 1e-8:
            raise Blocked('F0_NATIVE_LPS_INVERSE')
        name = f'case_{i:02d}_signed_contribution.npy'
        sha = store.array(name, contribution)
        f0.append(dict(record_id=row['record_id'], predicted_class=int(scores[i] > .5),
                       predicted_label='COVID-19_OR_CAP_SOURCE' if scores[i] > .5 else 'Normal_SOURCE',
                       positive_probability=float(scores[i]), raw_logits=logits_all[i].tolist(),
                       effective_bias=bias.tolist(), signed_contribution=dict(path=str(store.directory/name),sha256=sha),
                       native_nominal_centers_ZYX=native[:,:3].tolist(), LPS_centers_mm=lps[:,:3].tolist(),
                       geometry=receipt['rows'][i]['geometry'], reconstruction_max_absolute_error=error,
                       geometry_valid=True, native_map='sparse 4x4x4 lattice with native coordinates; no dense segmentation',
                       inverse_mapping_max_absolute_error=inverse_error,
                       semantics='signed coarse source-class contribution; no ReLU; not lesion probability or 2D E2',
                       model_version=dict(backbone_sha256=receipt['model_sha256'],head_checkpoint_sha256=checkpoint_sha,
                                          feature_cache_receipt_sha256=cache_receipt_sha,
                                          data_manifest_sha256=manifest_sha,source_commit=receipt['source_commit'],
                                          config_sha256=receipt['config_sha256'],seed=17,
                                          precision='FP32 feature/train, FP64 GAP/evaluation/contribution')))
    result = dict(schema='CTFM_RESEARCH_EVALUATION_V4',status='PASS',evidence_type=receipt['evidence_type'],metrics=metrics,F0=f0,
                  calls=meter.report(),medical_forward=0,head_forward=2,head_backward=0,
                  clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN',
                  independent_test_claim=False,clinical_accuracy_claim=False,
                  limitations=['40/20 development source groups; no clinical patient independence established',
                               'source diagnosis is weak supervision; no per-slice lesion truth',
                               'full-FOV64 small lesion retention unvalidated; coarse map not segmentation',
                               'validation reused for development reporting; no independent test'])
    store.json('evaluation.json',result)
    return result


def authority(request, request_sha, approval_ref, dispatch_ref):
    approval, dispatch = bound_json(approval_ref), bound_json(dispatch_ref)
    for receipt, schema, status in ((approval,'CTFM_RESEARCH_APPROVAL_V4','APPROVED_NEW_SCOPE'),
                                    (dispatch,'CTFM_RESEARCH_DISPATCH_V4','EXCLUSIVE_SLOT_ASSIGNED')):
        if (receipt.get('schema')!=schema or receipt.get('status')!=status
                or receipt.get('request_sha256')!=request_sha or receipt.get('owner')!='ENCODER'
                or receipt.get('phase')!=request['phase'] or receipt.get('task_key')!=request['spec']['task_key']
                or receipt.get('retry') is not False):
            raise Blocked('NEW_EXACT_CHIEF_APPROVAL_AND_DISPATCH_REQUIRED')
    if dispatch.get('approval_sha256') != approval_ref['sha256']:
        raise Blocked('DISPATCH_APPROVAL_SHA')
    return approval, dispatch


def load_shared(request):
    bundle = request['supervisor']
    path = safe_path(bundle['package_path'])
    if path.name != SHARED_PACKAGE or bundle['dependency_sha256'] != SHARED_SHA:
        raise Blocked('PINNED_RECOVERY_CHAIN_REQUIRED')
    receipt = bound_json(bundle['bundle_receipt'])
    if receipt['package'] != SHARED_PACKAGE:
        raise Blocked('SHARED_RECEIPT_PACKAGE')
    for name, ref in bundle['modules'].items():
        if safe_path(ref['path']) != path/(name+'.py') or file_sha(ref['path']) != ref['sha256']:
            raise Blocked('SHARED_SOURCE_DRIFT')
    if file_sha(path/'__init__.py') != bundle['initializer_sha256']:
        raise Blocked('SHARED_INITIALIZER_DRIFT')
    sys.path.insert(0,str(path.parent))
    shared = importlib.import_module(SHARED_PACKAGE+'.wave1_supervisor')
    loaded = shared.verify_loaded_bundle(bundle['dependency_root'], SHARED_SHA)
    if loaded != bundle['modules']:
        raise Blocked('SHARED_LOADED_MODULE_DRIFT')
    return shared


def validate_request(request):
    if request['schema'] != 'CTFM_RESEARCH_RESOLVED_EXECUTION_V4' or request['phase'] not in PHASES:
        raise Blocked('RESOLVED_PHASE_REQUEST_REQUIRED')
    phase = request['phase']; limits = PHASES[phase]; spec = request['spec']
    expected = dict(owner='ENCODER',device='cpu',max_forward=limits['forward'],
                    max_backward=limits['backward'],timeout_seconds=limits['seconds'],
                    per_case_seconds=limits['per_case'])
    if any(spec.get(k)!=v for k,v in expected.items()) or request['retry'] is not False or request['warmup'] != 0 or request['config']['planned_counts'] != COUNTS:
        raise Blocked('FIXED_V4_SCOPE_REQUIRED')
    if request['config']['preprocess'] != PREPROCESS or request['config']['phases'] != PHASES:
        raise Blocked('FIXED_V4_CONFIG_REQUIRED')
    if request['config']['head'] != dict(seed=17,updates=100,optimizer='AdamW',learning_rate=.001,
            weight_decay=.0001,batch=40,threshold=.5,tie='Normal',training_dtype='float32',
            gap_dtype='float64',evaluation_dtype='float64',f0_atol=1e-10,f0_rtol=1e-12):
        raise Blocked('FIXED_HEAD_PRECISION_AND_CONFIGURATION_REQUIRED')
    if request['data_contract']['sha256'] != DATA_CONTRACT_SHA:
        raise Blocked('EXACT_DATA_CONTRACT_V2_REQUIRED')
    bound_json(request['data_contract'])
    if not request.get('sources') or not re.fullmatch('[a-f0-9]{40}',request['source_commit']):
        raise Blocked('SOURCE_CLOSURE_REQUIRED')
    if {safe_path(ref['path']) for ref in request['sources']} != set(source_closure()):
        raise Blocked('COMPLETE_LOCAL_IMPORT_CLOSURE_REQUIRED')
    for ref in request['sources']:
        if file_sha(ref['path']) != ref['sha256']:
            raise Blocked('SOURCE_CLOSURE_DRIFT')
        root = Path(__file__).resolve().parents[3]
        try:
            relative = safe_path(ref['path']).relative_to(root)
            committed = subprocess.check_output(['git','-C',str(root),'show',
                request['source_commit']+':'+str(relative)],stderr=subprocess.DEVNULL,timeout=5)
        except (ValueError,subprocess.SubprocessError):
            raise Blocked('EXACT_COMMITTED_ENC_SOURCE_REQUIRED')
        if digest(committed) != ref['sha256']:
            raise Blocked('COMMITTED_SOURCE_DIGEST_MISMATCH')
    if request['runtime']['packages'] != dict(torch='2.14.0',numpy='2.4.6',monai='1.5.1',safetensors='0.5.3') or request['runtime']['python_version'] != '3.11.15':
        raise Blocked('DECLARED_EXISTING_RUNTIME_REQUIRED')
    for ref in request['runtime']['references']:
        if file_sha(ref['path']) != ref['sha256']:
            raise Blocked('DECLARED_RUNTIME_REFERENCE_DRIFT')
    root = safe_path(request['delivery_root'])
    for name in ('output','supervisor_output'):
        path = safe_path(request[name])
        if root not in path.parents:
            raise Blocked('OUTPUT_OUTSIDE_BOUND_DELIVERY')
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--request-sha',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    for name in ('approval','approval-sha','dispatch','dispatch-sha'):
        parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    guard = meter = adapter = extract = None
    try:
        request = validate_request(bound_json(dict(path=args.request,sha256=args.request_sha)))
        if not args.execute:
            print(json.dumps(dict(status='BLOCKED',reason='NEW_AUTHORITY_AND_QUALIFIED_DATA_REQUIRED',torch_imported='torch' in sys.modules,real_execution='NOT RUN')))
            return 3
        if not all((args.approval,args.approval_sha,args.dispatch,args.dispatch_sha)):
            raise Blocked('APPROVAL_AND_DISPATCH_REQUIRED_BEFORE_REAL_ACCESS')
        authority(request,args.request_sha,dict(path=args.approval,sha256=args.approval_sha),dict(path=args.dispatch,sha256=args.dispatch_sha))
        shared = load_shared(request)
        if not args.child:
            recovery = request['administrative_recovery']
            child = [sys.executable,'-m',__name__,'--request',args.request,'--request-sha',args.request_sha,
                     '--approval',args.approval,'--approval-sha',args.approval_sha,
                     '--dispatch',args.dispatch,'--dispatch-sha',args.dispatch_sha,'--execute','--child']
            result = shared.run_supervised(shared.SupervisionSpec(**request['spec']),child,
                     request['supervisor_output'],request['supervisor']['dependency_root'],SHARED_SHA,
                     recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
            print(json.dumps(dict(status=result['status'],slot_completed=result['slot_completed'])))
            return 0 if result['status']=='SUCCESS' and result['slot_completed'] else 2
        guard = shared.ChildGuard.from_environment()
        if vars(guard.spec) != vars(shared.SupervisionSpec(**request['spec'])):
            raise Blocked('SHARED_CHILD_IDENTITY_MISMATCH')
        meter = Meter(request['phase'],guard,request['delivery_root'])
        records = validate_records(bound_json(request['data_manifest'],meter.check))
        for name, version in request['runtime']['packages'].items():
            if importlib.metadata.version(name) != version:
                raise Blocked('EXACT_LOCAL_RUNTIME_VERSION_REQUIRED')
        if sys.version.split()[0] != request['runtime']['python_version']:
            raise Blocked('EXACT_PYTHON_VERSION_REQUIRED')
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        if request['phase']=='cache':
            from .encoder import load_ctfm_local
            if request['checkpoint']['sha256'] != MODEL_SHA:
                raise Blocked('OFFICIAL_EXISTING_CHECKPOINT_REQUIRED')
            adapter = load_ctfm_local(request['checkpoint']['path'],MODEL_SHA)
            reference = weakref.ref(adapter)
            extract = adapter.extract
            cache_phase(records,request['data_manifest']['sha256'],digest(encoded(request['config'])),
                        request['source_commit'],MODEL_SHA,request['output'],extract,meter,evidence_type='REAL_CT_FM')
            extract = adapter = None;gc.collect()
            if reference() is not None:
                raise Blocked('CPU_ENCODER_REFERENCE_NOT_RELEASED')
        else:
            cached = bound_json(request['cache_receipt'],meter.check)
            if cached.get('evidence_type') != 'REAL_CT_FM' or cached.get('model_sha256') != MODEL_SHA:
                raise Blocked('REAL_VERSIONED_CACHE_REQUIRED')
            if cached['config_sha256'] != digest(encoded(request['config'])) or cached['source_commit'] != request['source_commit']:
                raise Blocked('CACHE_EXECUTION_SOURCE_CONFIG_MISMATCH')
            if request['phase']=='train':
                train_phase(records,cached,request['data_manifest']['sha256'],request['cache_receipt']['sha256'],request['output'],meter)
            else:
                checkpoint = bound_json(request['head_checkpoint'],meter.check)
                evaluate_phase(records,cached,checkpoint,request['data_manifest']['sha256'],request['cache_receipt']['sha256'],
                               request['head_checkpoint']['sha256'],request['output'],meter)
            gc.collect()
        meter.check()
        guard.complete('SUCCESS',device_recovered=True,actual_forward=meter.returned_forward,actual_backward=meter.returned_backward)
        print(json.dumps(dict(status='PASS',calls=meter.report(),GPU='NOT RUN')))
        return 0
    except Exception as exc:
        extract = adapter = None;gc.collect()
        if guard:
            guard.complete('FAILED',reason=type(exc).__name__,device_recovered=False,
                           actual_forward=meter.returned_forward if meter else 0,
                           actual_backward=meter.returned_backward if meter else 0)
        print(json.dumps(dict(status='BLOCKED' if isinstance(exc,Blocked) else 'FAIL',reason=str(exc) if isinstance(exc,Blocked) else type(exc).__name__,real_execution='no automatic retry')))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
