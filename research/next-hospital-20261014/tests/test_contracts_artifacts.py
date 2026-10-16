from copy import deepcopy
import json

import numpy as np
import pytest

from epi_next.artifacts import (canonical_json, exclusive_local_queue, persist_run,
                                reconcile_run, sha256)
from epi_next.contracts import (AlgorithmStatus, EvidenceType, PredictionResult,
                                RunManifest, VolumeRecord)


def volume():
    return VolumeRecord("SYNTHETIC", "synthetic", "SYNTHETIC-SERIES", ["S1", "S2"],
                        sha256(b"synthetic-volume"), np.zeros((2, 3, 4)),
                        np.ones((2, 3, 4), dtype=bool), np.eye(4),
                        [{"operation": "identity", "source": "synthetic"}],
                        "synthetic-task-v1", {"covid_status": "unknown"},
                        "SYNTHETIC_FULL_DOMAIN", (2, 3, 4))


def prediction():
    return PredictionResult("EPI-NEXT-TOY", sha256(b"toy"), sha256(b"identity"), 1,
                            [0., 100.], 1., None, None, [], EvidenceType.INPUT_OCCLUSION,
                            AlgorithmStatus.NO_RELIABLE_RESPONSE, "EPI-NEXT-TEST",
                            "synthetic zero response", "SYNTHETIC_FULL_DOMAIN")


def test_volume_roundtrip_and_sealed_rejection():
    v = volume()
    v.validate()
    for split in ("test", "sealed", "val", "unknown"):
        v.split = split
        with pytest.raises(ValueError):
            v.validate()


def test_real_volume_requires_explicit_membership():
    v = volume()
    v.split = "train"
    with pytest.raises(ValueError, match="approved membership"):
        v.validate()
    v.validate({"SYNTHETIC": {"split": "train", "series_uids": ["SYNTHETIC-SERIES"]}})


def test_unavailable_serializes_no_fabricated_logits():
    p = prediction()
    p.status = AlgorithmStatus.MODEL_UNAVAILABLE
    p.logits = []
    p.prediction_score = None
    p.checkpoint_sha = None
    assert p.to_dict()["logits"] == []
    p.prediction_score = .5
    with pytest.raises(ValueError, match="fabricated"):
        p.validate()


def test_map_cannot_impersonate_expert_reference():
    p = prediction()
    p.status = AlgorithmStatus.OK
    p.candidate_map = {"path": "map.npy", "sha256": "a" * 64,
                       "coordinate_space": "LPS", "evidence_type": "EXPERT_REFERENCE"}
    with pytest.raises(ValueError, match="expert"):
        p.validate()


@pytest.mark.parametrize("field,value", [
    ("source_sops", ["S1", "S1"]), ("valid_mask", np.ones((2, 3, 4))),
    ("valid_mask", np.zeros((2, 3, 4), dtype=bool)),
    ("affine_lps", np.zeros((4, 4))), ("volume_hu", np.full((2, 3, 4), np.nan)),
    ("transform_ledger", []), ("raw_hash", "unverified"),
    ("native_shape", (3, 3, 4)), ("coordinate_convention", "XYZ_RAS"),
])
def test_invalid_volume(field, value):
    v = volume()
    setattr(v, field, value)
    with pytest.raises(ValueError):
        v.validate()


def test_prediction_keeps_evidence_and_abstention():
    p = prediction()
    assert p.to_dict()["status"] == "NO_RELIABLE_RESPONSE"
    assert p.to_dict()["calibration_status"] == "UNCALIBRATED"
    p.evidence_type = EvidenceType.EXPERT_REFERENCE
    with pytest.raises(ValueError):
        p.validate()
    p = prediction()
    p.candidate_map = {"path": "fake"}
    with pytest.raises(ValueError):
        p.validate()


@pytest.mark.parametrize("field,value", [("target", 2), ("target", True),
    ("logits", [0, float("inf")]), ("prediction_score", float("nan")),
    ("checkpoint_sha", "missing"), ("calibration_status", "CLINICAL_PROBABILITY")])
def test_invalid_prediction(field, value):
    p = prediction()
    setattr(p, field, value)
    with pytest.raises(ValueError):
        p.validate()


def test_result_retry_conflict_corruption_and_unknown(tmp_path):
    data = {"result.json": canonical_json(prediction().to_dict())}
    first = persist_run(tmp_path, "EPI-NEXT-TEST", data)
    assert first["state"] == "COMMITTED"
    assert persist_run(tmp_path, "EPI-NEXT-TEST", data) == first
    with pytest.raises(RuntimeError, match="RESULT_CONFLICT"):
        persist_run(tmp_path, "EPI-NEXT-TEST", {"result.json": b"changed"})
    (tmp_path / "EPI-NEXT-TEST" / "result.json").write_bytes(b"tampered")
    assert reconcile_run(tmp_path, "EPI-NEXT-TEST")["state"] == "CORRUPT"
    with pytest.raises(RuntimeError, match="CORRUPT"):
        persist_run(tmp_path, "EPI-NEXT-TEST", data)
    (tmp_path / "EPI-NEXT-PENDING").mkdir()
    with pytest.raises(RuntimeError, match="UNKNOWN_TRANSACTION"):
        persist_run(tmp_path, "EPI-NEXT-PENDING", data)


def test_concurrent_writer_fails_and_lock_releases(tmp_path):
    with exclusive_local_queue(tmp_path):
        with pytest.raises(RuntimeError, match="LOCAL_QUEUE_BUSY"):
            persist_run(tmp_path, "EPI-NEXT-BUSY", {"a": b"a"})
    assert persist_run(tmp_path, "EPI-NEXT-BUSY", {"a": b"a"})["state"] == "COMMITTED"


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/b", "..", "", "receipt.json"])
def test_asset_names_cannot_escape_or_override(tmp_path, name):
    with pytest.raises(ValueError):
        persist_run(tmp_path, "EPI-NEXT-SAFE", {name: b"x"})


def test_symlink_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "EPI-NEXT-LINK").symlink_to(outside)
    with pytest.raises(RuntimeError, match="CONFLICT"):
        persist_run(tmp_path, "EPI-NEXT-LINK", {"a": b"a"})


def test_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"score": float("nan")})


@pytest.mark.parametrize("receipt", [[], {"run_id": "EPI-NEXT-BAD", "artifact_hashes": ["a"]},
    {"run_id": "EPI-NEXT-BAD", "artifact_hashes": {"a": "not-a-hash"}}])
def test_corrupt_receipt_types_preserved(tmp_path, receipt):
    directory = tmp_path / "EPI-NEXT-BAD"
    directory.mkdir()
    (directory / "a").write_bytes(b"a")
    (directory / "receipt.json").write_bytes(canonical_json(receipt))
    assert reconcile_run(tmp_path, "EPI-NEXT-BAD")["state"] == "CORRUPT"


def test_runner_reconciles_before_compute(tmp_path, monkeypatch):
    from argparse import Namespace
    from epi_next import cli
    def fail(_):
        raise AssertionError("must not rerun model")
    monkeypatch.setattr(cli, "_baseline_synthetic_new", fail)
    args = Namespace(enable_research=True, output=tmp_path,
                     run_id="EPI-NEXT-REPLAY", checkpoint_sha="a" * 64)
    data = {"run_manifest.json": canonical_json({"model_sha": "a" * 64}),
            "config.json": canonical_json({"experiment": "EPI-NEXT-BASELINE-SYNTHETIC-NUMERICS-v1"})}
    persist_run(tmp_path, args.run_id, data)
    assert cli.baseline_synthetic(args)["state"] == "COMMITTED"
    args.checkpoint_sha = "b" * 64
    with pytest.raises(RuntimeError, match="RESULT_CONFLICT"):
        cli.baseline_synthetic(args)
    args.run_id = "EPI-NEXT-UNKNOWN"
    (tmp_path / args.run_id).mkdir()
    with pytest.raises(RuntimeError, match="UNKNOWN_TRANSACTION"):
        cli.baseline_synthetic(args)
