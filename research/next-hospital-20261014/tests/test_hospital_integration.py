from copy import deepcopy
import json

import numpy as np
import pytest
from scipy.ndimage import affine_transform

from epi_next.artifacts import canonical_json, sha256
from epi_next.hospital_contract import (ALGORITHMS, map_region, request_hash,
                                       transform_chain, validate_request, validate_result)
from epi_next import hospital_runtime as runtime
from epi_next.hospital_release import acceptance_gate, select_algorithm, dispatch_selected, ACCEPTANCE_CHECKS
from epi_next.hospital_contract import SPATIAL_CHECKS


def request(algorithm="E1"):
    shape = [1, 4, 5] if algorithm in {"E1", "E2"} else [3, 4, 5]
    return {"schema": "EPI-NEXT-HOSPITAL-INPUT-1", "run_id": "EPI-NEXT-TEST-" + algorithm,
            "source_git_sha": "a" * 40, "source": "SYNTHETIC", "case_id": "SYNTHETIC-CASE",
            "study_uid": "SYNTHETIC-STUDY", "series_uid": "SYNTHETIC-SERIES",
            "input_manifest_sha256": "a" * 64, "algorithm_id": algorithm,
            "algorithm_config": {}, "algorithm_config_sha256": sha256(canonical_json({})),
            "algorithm_version": ALGORITHMS[algorithm]["version"], "model_id": "SYNTHETIC-MODEL",
            "model_version": "v1", "model_sha256": "b" * 64, "preprocessing_version": "identity-v1",
            "preprocessing_sha256": "c" * 64,
            "model_input_dtype": "float32", "model_input_channels": 1,
            "task": {"definition_id": "SYNTHETIC-ONLY", "target_label": "test", "target_class": 1,
                     "definition_sha256": "d" * 64},
            "resource_budget": {"device": "cpu", "max_model_calls": 10, "max_input_voxels": 100,
                                "max_input_bytes": 1000, "max_seconds": 60,
                                "deadline_enforcement": "BETWEEN_FORWARDS"},
            "spatial": {"convention": "ZYX_CENTERS_TO_LPS_MM", "native_shape_zyx": shape,
                        "model_shape_zyx": shape, "native_affine_lps": np.eye(4).tolist(),
                        "model_to_native_zyx": np.eye(4).tolist(),
                        "operations": [{"operation": "identity", "input_shape_zyx": shape, "output_shape_zyx": shape}],
                        "source_sops": [f"SYNTHETIC-S{z}" for z in range(shape[0])],
                        "source_file_sha256": ["e" * 64] * shape[0]}}


def candidate(r):
    bounds = [[0, 1], [0, 2], [1, 3]]
    return {"bounds_zyx": bounds, "spatial": map_region(bounds, r["spatial"]),
            "response": {key:.25 for key in ALGORITHMS[r["algorithm_id"]]["response_fields"]}, "support": {"status": "SYNTHETIC"}}


def registered(r, function):
    fields = {key: r[key] for key in ("algorithm_id", "algorithm_version", "model_id", "model_version",
                                       "model_sha256", "preprocessing_version", "preprocessing_sha256")}
    return runtime.RegisteredRuntime(**fields, device=r["resource_budget"]["device"], function=function)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_each_version_retains_distinct_evidence_and_full_logits(algorithm):
    r = request(algorithm)
    validate_request(r)
    result = runtime.output_envelope(r, {"status": "OK", "logits": [-1., 2.],
                                       "candidate_regions": [candidate(r)]}, calls=1)
    assert result["status"] == "SUCCESS"
    assert result["evidence_type"] == ALGORITHMS[algorithm]["evidence_type"]
    assert result["logits"] == [-1., 2.]
    assert result["hospital_candidate"] is False
    result["evidence_type"] = "EXPERT_REFERENCE"
    with pytest.raises(ValueError, match="evidence mismatch"):
        validate_result(r, result)


@pytest.mark.parametrize("raw_status,status", [("OK", "SUCCESS"), ("NO_FEASIBLE_MASK", "NO_RELIABLE_RESPONSE"),
    ("PARTIAL_BUDGET", "PARTIAL_BUDGET"), ("FAILED", "FAILED"), ("GEOMETRY_INVALID", "BLOCKED"),
    ("NOT RUN", "NOT RUN")])
def test_six_execution_states_preserve_original_reason(raw_status, status):
    r = request()
    result = runtime.output_envelope(r, {"status": raw_status, "reason": "synthetic", "logits": [0., 1.],
                                       "candidate_regions": [candidate(r)]}, calls=1)
    assert result["status"] == status and result["algorithm_status"] == raw_status
    if status not in {"SUCCESS", "PARTIAL_BUDGET"}:
        assert result["candidate_regions"] == []


def test_invalid_geometry_with_real_logits_never_exposes_candidate():
    r = request()
    result = runtime.output_envelope(r, {"status": "GEOMETRY_INVALID", "logits": [0, 1],
                                       "candidate_regions": [candidate(r)]}, calls=1)
    assert result["geometry_status"] == "INVALID" and result["candidate_regions"] == []
    result["candidate_regions"] = [candidate(r)]
    with pytest.raises(ValueError):
        validate_result(r, result)


def test_sop_bounds_and_world_corners_cannot_be_relabelled():
    r = request("F1")
    s = r["spatial"]
    # Native ZYX -> LPS: slice +Z, row -Y, column -X, unequal spacing.
    s["native_affine_lps"] = [[0, 0, -3, 10], [0, -2, 0, 20], [4, 0, 0, 30], [0, 0, 0, 1]]
    mapped = map_region([[1,2],[2,4],[1,3]], s)
    assert mapped["source_sops"] == ["SYNTHETIC-S1"]
    assert mapped["corners_lps_mm"][0] == [8.5, 17., 32.]
    result = runtime.output_envelope(r, {"status": "OK", "logits": [0,1], "candidate_regions": [candidate(r)]}, calls=1)
    result["candidate_regions"][0]["spatial"]["source_sops"] = ["UNKNOWN-SOP"]
    with pytest.raises(ValueError, match="mapping mismatch"):
        validate_result(r, result)


def test_actual_crop_resize_half_pixel_uses_independent_intensity_landmarks():
    s = request("F1")["spatial"]
    native = np.fromfunction(lambda z,y,x: 100*z+10*y+x, (3,4,5), dtype=float)
    cropped = native[:,1:4,1:5]
    ratio = np.array([1.,3/2,4/2])
    resized = affine_transform(cropped, np.diag(ratio), offset=(ratio-1)/2,
                               output_shape=(3,2,2), order=1, mode="nearest", prefilter=False)
    s["operations"] = [{"operation":"crop", "input_shape_zyx":[3,4,5], "output_shape_zyx":[3,3,4], "start_zyx":[0,1,1]},
                       {"operation":"resize", "input_shape_zyx":[3,3,4], "output_shape_zyx":[3,2,2], "convention":"half_pixel_align_corners_false"}]
    mapping = np.diag([1.,1.5,2.,1.]); mapping[:3,3] = [0,1.25,1.5]
    s["model_shape_zyx"] = [3,2,2]; s["model_to_native_zyx"] = mapping.tolist()
    np.testing.assert_allclose(transform_chain(s), mapping)
    assert resized[2,1,1] == 231.  # native centre (2,2.75,3.5)
    s["operations"][1]["convention"] = "align_corners_true"
    with pytest.raises(ValueError, match="convention"):
        transform_chain(s)


def test_global_queue_and_replay_before_compute(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "QUEUE_ROOT", tmp_path / "shared-device-queue")
    r = request()
    calls = []
    def run(req, before):
        before(); calls.append(req["run_id"])
        return {"status":"OK", "logits":[0.,1.]}, {"numeric.json": b"{}"}
    bound = registered(r, run)
    with runtime.device_lease("cpu"):
        blocked = runtime.execute_registered(r, bound, tmp_path / "out-A")
        assert blocked["status"] == "BLOCKED" and blocked["reason"] == "DEVICE_QUEUE_BUSY"
    first = runtime.execute_registered(r, bound, tmp_path / "out-A")
    assert first["status"] == "SUCCESS"
    assert runtime.execute_registered(r, bound, tmp_path / "out-A") == first
    assert len(calls) == 1
    blocked = runtime.execute_registered(r, bound, tmp_path / "out-B")
    assert blocked["reason"] == "UNKNOWN_TRANSACTION_RECONCILE_REQUIRED" and len(calls) == 1
    r["task"]["target_label"] = "changed"
    assert runtime.execute_registered(r, registered(r, run), tmp_path / "out-A")["reason"] == "RESULT_CONFLICT"


def test_mps_owner_unknown_and_formal_data_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime,"QUEUE_ROOT",tmp_path / "queue")
    r = request(); r["resource_budget"]["device"] = "mps"
    def forbidden(*_): pytest.fail("model should not run")
    bound = registered(r,forbidden)
    assert runtime.execute_registered(r,bound,tmp_path / "out")["reason"] == "MPS_RESERVED_FOR_ENCODER"
    r["source"] = "LIVE_CASE"; r["access_approval_sha256"] = "f" * 64
    assert runtime.execute_registered(r,registered(r,forbidden),tmp_path / "out")["reason"] == "BLOCKED_BY_HOSPITAL_RUNTIME_HANDOFF"
    r = request(); (tmp_path / "out" / r["run_id"]).mkdir(parents=True)
    assert runtime.execute_registered(r,registered(r,forbidden),tmp_path / "out")["reason"] == "UNKNOWN_TRANSACTION"


def test_budget_and_failure_are_immutable_and_accounted(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,"QUEUE_ROOT",tmp_path / "queue")
    r = request(); r["resource_budget"]["max_model_calls"] = 1
    def exhaust(req,before):
        before(); before(); pytest.fail("budget was not enforced")
    result = runtime.execute_registered(r,registered(r,exhaust),tmp_path / "out")
    assert result["status"] == "PARTIAL_BUDGET" and result["actual_model_calls"] == 1
    assert result["logits"] == [] and result["candidate_regions"] == []
    r = request("F0")
    def fail(req,before):
        before(); raise RuntimeError("PRIVATE_IDENTIFIER_DO_NOT_SERIALIZE")
    result = runtime.execute_registered(r,registered(r,fail),tmp_path / "out")
    assert result["status"] == "FAILED" and "PRIVATE_IDENTIFIER" not in canonical_json(result).decode()


def manifest():
    return {"schema":"EPI-NEXT-HOSPITAL-RELEASE-1", "source_git_sha":"a"*40,
            "data_handoff_sha256":None, "real_e2e_status":"BLOCKED_BY_DATA_HANDOFF",
            "algorithms":{"E1":{"algorithm_version":ALGORITHMS["E1"]["version"],"status":"NOT RUN",
                                  "model_sha256":None,"preprocessing_sha256":None,"acceptance":{}}}}


def test_unaccepted_algorithm_cannot_be_selected_and_rollback_preserves_files(tmp_path):
    m = manifest()
    assert "THREE_CONSECUTIVE_REAL_RUNS_REQUIRED" in acceptance_gate(m,"E1",tmp_path)
    flag = tmp_path / "rollback-v1.json"
    assert select_algorithm(m,"FrozenBaseline",tmp_path,flag)["mode"] == "LEGACY_ROLLBACK"
    with pytest.raises(FileExistsError): select_algorithm(m,"Occlusion16",tmp_path,flag)
    with pytest.raises(RuntimeError,match="HOSPITAL_SELECTION_BLOCKED"):
        select_algorithm(m,"E1",tmp_path,tmp_path / "unaccepted.json")
    assert not (tmp_path / "unaccepted.json").exists()


def test_default_and_rollback_dispatch_leave_legacy_result_unchanged(tmp_path):
    m = manifest(); r = request()
    old = {"schema":"Result-2.0", "kind":"OCCLUSION", "scales":[16,32,64]}
    def legacy(algorithm, received):
        assert received is r
        assert algorithm in {"FrozenBaseline","Occlusion32"}
        return old
    assert dispatch_selected(r,m,tmp_path,tmp_path,legacy_runner=legacy) is old
    flag = select_algorithm(m,"Occlusion32",tmp_path,tmp_path / "flags-v1.json")
    assert dispatch_selected(r,m,tmp_path,tmp_path,flag=flag,legacy_runner=legacy) is old
    flag['release_manifest_sha256'] = '0' * 64
    with pytest.raises(ValueError,match='manifest mismatch'):
        dispatch_selected(r,m,tmp_path,tmp_path,flag=flag,legacy_runner=legacy)


def full_fixture_acceptance(tmp_path):
    """Fabricated receipt fixtures ONLY; never saved as actual hospital evidence."""
    m = manifest(); m.update(data_handoff_sha256='d'*64,real_e2e_status='PASS')
    entry = m['algorithms']['E1']; entry.update(model_sha256='b'*64,preprocessing_sha256='c'*64,status='ENGINEERING_ACCEPTED')
    r = request(); entry.update(algorithm_config_sha256=r['algorithm_config_sha256'],resource_budget_sha256=sha256(canonical_json(r['resource_budget'])))
    m['task_definition_sha256'] = r['task']['definition_sha256']
    identity = dict(source_git_sha=m['source_git_sha'],algorithm_id='E1',algorithm_version=entry['algorithm_version'],
                    model_sha256='b'*64,preprocessing_sha256='c'*64,data_handoff_sha256='d'*64)
    identity.update(algorithm_config_sha256=entry['algorithm_config_sha256'],resource_budget_sha256=entry['resource_budget_sha256'],task_definition_sha256=m['task_definition_sha256'])
    def save(name,payload):
        data = canonical_json(payload); (tmp_path / name).write_bytes(data)
        return {'path':name,'sha256':sha256(data)}
    acceptance = entry['acceptance']
    for key in ACCEPTANCE_CHECKS:
        acceptance[key] = save(key+'.json',{'check':key,'status':'PASS','source':'LIVE_CASE','identity':identity})
    acceptance['spatial_checks'] = {key:save('spatial-'+key+'.json',{'check':'spatial:'+key,'status':'PASS','source':'LIVE_CASE','identity':identity}) for key in SPATIAL_CHECKS}
    acceptance['consecutive_demo_runs'] = [save(f'run-{i}.json',{'source':'LIVE_CASE','identity':identity,'status':'PASS','sequence':i,
        'workflow_run_id':f'FIXTURE-{i}','blocking_faults':0,'checks':{key:'PASS' for key in ACCEPTANCE_CHECKS}}) for i in range(3)]
    r = request(); r.update(source='LIVE_CASE',access_approval_sha256='d'*64)
    result = runtime.output_envelope(r,{'status':'OK','logits':[0.,1.]},calls=1)
    acceptance['precomputed_result'] = save('precomputed_result.json',{'schema':'EPI-NEXT-HOSPITAL-PRECOMPUTED-1',
        'source':'LIVE_CASE','identity':identity,'status':'PASS','request_reference':save('request.json',r),
        'result_reference':save('result.json',result)})
    acceptance['rollback_receipt'] = save('rollback_receipt.json',{'source':'LIVE_CASE','identity':identity,'status':'PASS','fallback_algorithm':'FrozenBaseline'})
    recording = b'\x1a\x45\xdf\xa3' + b'GENERATED_TEST_FIXTURE_NOT_A_REAL_RECORDING'
    (tmp_path / 'fixture.webm').write_bytes(recording)
    acceptance['backup_recording'] = {'path':'fixture.webm','sha256':sha256(recording)}
    acceptance['backup_recording_review'] = save('recording-review.json',{'identity':identity,'status':'PASS',
        'recording_sha256':sha256(recording),'playback_verified':True})
    return m


def test_gate_requires_same_real_identity_distinct_consecutive_runs_and_all_assets(tmp_path):
    m = full_fixture_acceptance(tmp_path)
    assert acceptance_gate(m,'E1',tmp_path) == []
    a = m['algorithms']['E1']['acceptance']; refs = a['consecutive_demo_runs']
    original = deepcopy(refs); a['consecutive_demo_runs'] = [refs[0],refs[0],refs[2]]
    assert 'DEMO_RUNS_MUST_BE_DISTINCT_AND_CONSECUTIVE' in acceptance_gate(m,'E1',tmp_path)
    a['consecutive_demo_runs'] = original
    report = json.loads((tmp_path / 'run-1.json').read_bytes()); report['source'] = 'SYNTHETIC'
    data = canonical_json(report); (tmp_path / 'run-1.json').write_bytes(data); a['consecutive_demo_runs'][1]['sha256'] = sha256(data)
    assert 'INVALID_REAL_DEMO_RUN' in acceptance_gate(m,'E1',tmp_path)
    (tmp_path / 'fixture.webm').write_bytes(b'tampered')
    assert 'MISSING_OR_INVALID_EVIDENCE:backup_recording' in acceptance_gate(m,'E1',tmp_path)


def test_zero_call_candidates_nonnumeric_response_and_bytes_budget_rejected():
    r = request()
    with pytest.raises(ValueError,match='recorded inference'):
        runtime.output_envelope(r,{'status':'PARTIAL_BUDGET','candidate_regions':[candidate(r)]})
    bad = candidate(r); bad['response']['signed_margin_delta'] = 'made-up'
    with pytest.raises(ValueError,match='finite'):
        runtime.output_envelope(r,{'status':'OK','logits':[0.,1.],'candidate_regions':[bad]},calls=1)
    r['resource_budget']['max_input_bytes'] = 1
    with pytest.raises(ValueError,match='byte budget'):
        validate_request(r)


def test_gate_rejects_incomplete_or_unregistered_models_and_failed_backup(tmp_path):
    m = full_fixture_acceptance(tmp_path)
    entry = m['algorithms']['E1']; entry['status'] = 'NOT RUN'
    assert 'ALGORITHM_NOT_ACCEPTED' in acceptance_gate(m,'E1',tmp_path)
    entry['algorithm_version'] = 'LATEST_UNREGISTERED'
    assert 'UNREGISTERED_ALGORITHM_VERSION' in acceptance_gate(m,'E1',tmp_path)
    data = canonical_json({'source':'LIVE_CASE','identity':{},'status':'FAILED'})
    (tmp_path / 'precomputed_result.json').write_bytes(data)
    entry['acceptance']['precomputed_result']['sha256'] = sha256(data)
    assert 'MISSING_OR_INVALID_EVIDENCE:precomputed_result' in acceptance_gate(m,'E1',tmp_path)


def test_intent_creation_race_blocks_without_compute(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'QUEUE_ROOT',tmp_path / 'queue')
    actual_open = runtime.os.open
    def raced(path, flags, *args):
        if str(path).endswith('EPI-NEXT-TEST-E1.json'):
            raise FileExistsError('another device created intent')
        return actual_open(path,flags,*args)
    monkeypatch.setattr(runtime.os,'open',raced)
    def forbidden(*args): pytest.fail('duplicate compute')
    r = request()
    result = runtime.execute_registered(r,registered(r,forbidden),tmp_path / 'out')
    assert result['status'] == 'BLOCKED' and result['reason'] == 'UNKNOWN_TRANSACTION_RECONCILE_REQUIRED'
