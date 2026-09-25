#!/usr/bin/env python3
"""Frozen Stage 1 occlusion response runner for smoke and formal validation."""
import argparse
import hashlib
import itertools
import json
import math
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import torch
import torchvision
import yaml
from scipy.stats import spearmanr
from torchvision.models import ResNet18_Weights
from torchvision.transforms import functional as TF

from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest
from src.model import build_model
from src.preprocessing import preprocess_dicom


EPSILON_NUM = 1e-6
COMPARISON_GRID = (14, 14)
BOOTSTRAP_SEED = 20260925
BOOTSTRAP_RESAMPLES = 1000


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def load_stage_config(path="configs/occlusion_instability_v1.yaml"):
    config_path = PROJECT_ROOT / path
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle), config_path


def parse_hashes(path):
    return {line.split(maxsplit=1)[1]: line.split(maxsplit=1)[0]
            for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}


def verify_frozen_inputs(stage_config, stage_config_path):
    freeze_path = PROJECT_ROOT / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/protocol_v1_freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    protocol_path = PROJECT_ROOT / freeze["protocol_path"]
    assert freeze["status"] == "FROZEN"
    assert stage_config["status"] == "FROZEN"
    assert stage_config["protocol_id"] == freeze["protocol_id"]
    assert sha256_file(protocol_path) == freeze["protocol_sha256"]
    assert sha256_file(stage_config_path) == freeze["config_sha256"]
    checkpoint = PROJECT_ROOT / stage_config["baseline"]["checkpoint"]
    assert sha256_file(checkpoint) == stage_config["baseline"]["checkpoint_sha256"]
    assert sha256_file(checkpoint) == freeze["baseline_checkpoint_sha256"]
    assert int(stage_config["baseline"]["best_epoch"]) == 2

    split_dir = PROJECT_ROOT / stage_config["data"]["split_dir"]
    expected = parse_hashes(split_dir / "SHA256SUMS")
    assert expected == freeze["formal_split_hashes"]
    actual = {name: sha256_file(split_dir / name) for name in expected}
    assert actual == expected
    assert stage_config["data"]["test_set_status"] == "SEALED"
    return freeze, checkpoint, split_dir


def build_grid(image_size, block_size, stride):
    if image_size <= 0 or block_size <= 0 or stride <= 0 or block_size > image_size:
        raise ValueError("invalid grid dimensions")
    starts = list(range(0, image_size - block_size + 1, stride))
    if starts[-1] != image_size - block_size:
        starts.append(image_size - block_size)
    positions = [(x, y) for y in starts for x in starts]
    for x, y in positions:
        if x < 0 or y < 0 or x + block_size > image_size or y + block_size > image_size:
            raise AssertionError("grid block crosses image boundary")
    return positions


def expected_grid_counts():
    return {b: len(build_grid(224, b, b // 2)) for b in (16, 32, 64)}


def normalize_resized(resized):
    if resized.ndim != 3 or resized.shape[0] != 1:
        raise ValueError("expected resized grayscale tensor [1,H,W]")
    rgb = resized.repeat(3, 1, 1)
    return TF.normalize(rgb, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])


def mask_resized(resized, x, y, block_size, fill=0.5):
    masked = resized.clone()
    masked[:, y:y + block_size, x:x + block_size] = float(fill)
    return normalize_resized(masked)


def safe_probability(logits):
    probabilities = torch.softmax(logits, dim=1)
    if not torch.isfinite(logits).all() or not torch.isfinite(probabilities).all():
        raise FloatingPointError("non-finite logits or probabilities")
    return probabilities


def infer_logits(model, tensors, device, batch_size=32):
    chunks = []
    with torch.inference_mode():
        for start in range(0, len(tensors), batch_size):
            batch = torch.stack(tensors[start:start + batch_size]).to(device)
            logits = model(batch)
            if not torch.isfinite(logits).all():
                raise FloatingPointError("non-finite inference logits")
            chunks.append(logits.detach().cpu())
    logits = torch.cat(chunks, dim=0)
    probabilities = safe_probability(logits)
    return logits.numpy(), probabilities.numpy()


def add_response_metrics(rows):
    frame = pd.DataFrame(rows)
    slice_group_key = "fixture_id" if "fixture_id" in frame.columns else "slice_key"
    for (_slice_id, block_size), group in frame.groupby([slice_group_key, "block_size"], sort=True):
        p0 = group["p0"].to_numpy(dtype=float)
        pg = group["pg"].to_numpy(dtype=float)
        q0 = group["q0"].to_numpy(dtype=float)
        qg = group["qg"].to_numpy(dtype=float)
        candidate = np.maximum(q0 - qg, 0.0)
        amplitude = float(np.max(np.abs(q0 - qg)))
        status = "valid" if float(np.max(candidate)) > EPSILON_NUM else "insufficient_positive_response"
        top_k = max(1, int(math.ceil(0.10 * len(group))))
        cutoff = np.sort(candidate)[::-1][top_k - 1]
        selected = (candidate >= cutoff) & (candidate > EPSILON_NUM) if status == "valid" else np.zeros(len(group), dtype=bool)
        indices = group.index.to_numpy()
        frame.loc[indices, "signed_probability_drop"] = p0 - pg
        frame.loc[indices, "absolute_probability_change"] = np.abs(p0 - pg)
        frame.loc[indices, "prediction_flip"] = (group["baseline_class"].to_numpy() != group["masked_class"].to_numpy()).astype(int)
        frame.loc[indices, "decision_confidence_drop"] = q0 - qg
        frame.loc[indices, "candidate_response"] = candidate
        frame.loc[indices, "position_variance"] = float(np.var(pg, ddof=0))
        frame.loc[indices, "p95_absolute_probability_change"] = float(np.quantile(np.abs(p0 - pg), 0.95))
        frame.loc[indices, "response_amplitude"] = amplitude
        frame.loc[indices, "candidate_status"] = status
        frame.loc[indices, "candidate_selected"] = selected
        frame.loc[indices, "candidate_cutoff"] = float(cutoff)
    return frame


def rasterize_block_scores(group, value_column, image_size=224):
    values = np.zeros((image_size, image_size), dtype=np.float64)
    counts = np.zeros((image_size, image_size), dtype=np.float64)
    block_size = int(group.block_size.iloc[0])
    for row in group.itertuples(index=False):
        score = float(getattr(row, value_column))
        x, y = int(row.x), int(row.y)
        values[y:y + block_size, x:x + block_size] += score
        counts[y:y + block_size, x:x + block_size] += 1.0
    if np.any(counts == 0):
        raise AssertionError("rasterized map does not cover the image")
    return values / counts


def project_area_average(image, grid=COMPARISON_GRID):
    height, width = image.shape
    gh, gw = grid
    result = np.zeros((gh, gw), dtype=np.float64)
    for iy in range(gh):
        y0, y1 = iy * height / gh, (iy + 1) * height / gh
        for ix in range(gw):
            x0, x1 = ix * width / gw, (ix + 1) * width / gw
            ya, yb = int(round(y0)), int(round(y1))
            xa, xb = int(round(x0)), int(round(x1))
            result[iy, ix] = float(np.mean(image[ya:yb, xa:xb]))
    return result


def rank_values(values):
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks


def spatial_metrics(map_a, map_b, candidate_a, candidate_b):
    a, b = map_a.ravel(), map_b.ravel()
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        spearman = None
        pearson = None
    else:
        spearman = float(spearmanr(a, b).statistic)
        pearson = float(np.corrcoef(a, b)[0, 1])
    ca, cb = candidate_a.astype(bool), candidate_b.astype(bool)
    intersection = np.logical_and(ca, cb).sum()
    union = np.logical_or(ca, cb).sum()
    iou = float(intersection / union) if union else None
    dice = float(2 * intersection / (ca.sum() + cb.sum())) if (ca.sum() + cb.sum()) else None
    l1 = float(np.mean(np.abs(a - b)))
    if ca.any() and cb.any():
        center_a = np.argwhere(ca).mean(axis=0)
        center_b = np.argwhere(cb).mean(axis=0)
        diagonal = float(np.linalg.norm(np.asarray(ca.shape, dtype=float) - 1.0))
        center_distance = float(np.linalg.norm(center_a - center_b) / diagonal) if diagonal > 0 else 0.0
    else:
        center_distance = None
    return {"spearman": spearman, "pearson": pearson, "top10_iou": iou,
            "dice": dice, "normalized_center_distance": center_distance,
            "normalized_l1": l1}


def patient_first_summary(frame):
    summaries = []
    for (patient_id, block_size), group in frame.groupby(["patient_id", "block_size"], sort=True):
        per_slice = group.groupby("slice_key", sort=True).agg(
            baseline_probability=("p0", "first"),
            median_abs_change=("absolute_probability_change", "median"),
            iqr_abs_change=("absolute_probability_change", lambda x: float(np.quantile(x, .75) - np.quantile(x, .25))),
            p90_abs_change=("absolute_probability_change", lambda x: float(np.quantile(x, .90))),
            p95_abs_change=("absolute_probability_change", lambda x: float(np.quantile(x, .95))),
            flip_rate=("prediction_flip", "mean"),
            position_variance=("position_variance", "first"),
            response_amplitude=("response_amplitude", "first"),
            candidate_status=("candidate_status", "first"),
        ).reset_index()
        valid = per_slice.candidate_status.eq("valid")
        baseline_probability = float(per_slice.baseline_probability.mean())
        summaries.append({
            "patient_id": patient_id,
            "block_size": int(block_size),
            "slice_count": int(len(per_slice)),
            "baseline_patient_probability": baseline_probability,
            "baseline_patient_class": int(baseline_probability >= 0.5),
            "median_absolute_probability_change": float(per_slice.median_abs_change.median()),
            "iqr_absolute_probability_change": float(np.quantile(per_slice.median_abs_change, .75) - np.quantile(per_slice.median_abs_change, .25)),
            "p90_absolute_probability_change": float(per_slice.p90_abs_change.median()),
            "p95_absolute_probability_change": float(per_slice.p95_abs_change.median()),
            "flip_rate": float(per_slice.flip_rate.mean()),
            "position_variance": float(per_slice.position_variance.mean()),
            "valid_response_slice_proportion": float(valid.mean()),
            "insufficient_response_slice_count": int((~valid).sum()),
        })
    return pd.DataFrame(summaries)


def patient_bootstrap(values, seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"valid_n": 0, "median": None, "ci95": None}
    rng = np.random.default_rng(seed)
    medians = np.empty(resamples, dtype=float)
    for i in range(resamples):
        medians[i] = np.median(rng.choice(values, size=len(values), replace=True))
    return {"valid_n": int(len(values)), "median": float(np.median(values)),
            "ci95": [float(np.quantile(medians, .025)), float(np.quantile(medians, .975))]}


def atomic_write_json(path, payload):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_parquet(frame, path):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".partial")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def slice_summary(frame):
    return frame.groupby(["patient_id", "slice_key", "block_size"], sort=True).agg(
        baseline_probability=("p0", "first"),
        baseline_class=("baseline_class", "first"),
        mean_signed_probability_drop=("signed_probability_drop", "mean"),
        mean_absolute_probability_change=("absolute_probability_change", "mean"),
        p95_absolute_probability_change=("p95_absolute_probability_change", "first"),
        prediction_flip_rate=("prediction_flip", "mean"),
        position_variance=("position_variance", "first"),
        response_amplitude=("response_amplitude", "first"),
        candidate_status=("candidate_status", "first"),
        candidate_block_count=("candidate_selected", "sum"),
    ).reset_index()


def candidate_summary(frame):
    records = []
    for (patient_id, slice_key, block_size), group in frame.groupby(
            ["patient_id", "slice_key", "block_size"], sort=True):
        status = str(group.candidate_status.iloc[0])
        if status == "insufficient_positive_response":
            area_fraction = None
            selected_count = 0
        else:
            candidate_map = rasterize_block_scores(
                group.assign(candidate_response=group.candidate_selected.astype(float)),
                "candidate_response",
            ) > 0
            area_fraction = float(candidate_map.mean())
            selected_count = int(group.candidate_selected.sum())
        records.append({
            "patient_id": patient_id,
            "slice_key": slice_key,
            "block_size": int(block_size),
            "candidate_status": status,
            "candidate_block_count": selected_count,
            "candidate_area_fraction": area_fraction,
            "max_candidate_response": float(group.candidate_response.max()),
        })
    return pd.DataFrame(records)


def cross_scale_slice_summary(frame):
    records = []
    for slice_key, slice_frame in frame.groupby("slice_key", sort=True):
        maps = {}
        for block_size, group in slice_frame.groupby("block_size", sort=True):
            status = str(group.candidate_status.iloc[0])
            if status == "insufficient_positive_response":
                continue
            response_map = rasterize_block_scores(group, "candidate_response")
            selected_map = rasterize_block_scores(
                group.assign(candidate_response=group.candidate_selected.astype(float)),
                "candidate_response",
            ) > 0
            maps[int(block_size)] = (
                project_area_average(response_map),
                project_area_average(selected_map.astype(float)) > 0,
            )
        for left, right in itertools.combinations(sorted(maps), 2):
            metrics = spatial_metrics(maps[left][0], maps[right][0], maps[left][1], maps[right][1])
            records.append({
                "patient_id": str(slice_frame.patient_id.iloc[0]),
                "slice_key": str(slice_key),
                "scale_a": left,
                "scale_b": right,
                **metrics,
            })
    return pd.DataFrame(records)


def cross_scale_patient_summary(frame):
    if frame.empty:
        return pd.DataFrame()
    metric_columns = [
        "spearman", "pearson", "top10_iou", "dice",
        "normalized_center_distance", "normalized_l1",
    ]
    records = []
    for (patient_id, scale_a, scale_b), group in frame.groupby(
            ["patient_id", "scale_a", "scale_b"], sort=True):
        record = {
            "patient_id": patient_id,
            "scale_a": int(scale_a),
            "scale_b": int(scale_b),
            "valid_slice_count": int(len(group)),
        }
        for metric in metric_columns:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            record[f"{metric}_slice_median"] = float(values.median()) if len(values) else None
            record[f"{metric}_slice_iqr"] = (
                float(values.quantile(.75) - values.quantile(.25)) if len(values) else None
            )
        records.append(record)
    return pd.DataFrame(records)


def validate_patient_chunks(patient_id, expected_slice_keys, raw_dir, slice_dir,
                            patient_dir, candidate_dir, cross_dir):
    """Accept a patient only when all five committed chunks agree with the split."""
    paths = [directory / f"patient_{patient_id}.parquet" for directory in
             (raw_dir, slice_dir, patient_dir, candidate_dir, cross_dir)]
    if not all(path.is_file() for path in paths):
        raise RuntimeError(f"Incomplete patient chunks: {patient_id}")
    raw, slices, patient, candidate, cross = (pd.read_parquet(path) for path in paths)
    expected_keys = set(expected_slice_keys)
    if len(expected_keys) != len(expected_slice_keys):
        raise RuntimeError(f"Duplicate validation slice keys: {patient_id}")
    expected_scales = {16, 32, 64}
    for name, frame in (("raw", raw), ("slice", slices), ("patient", patient),
                        ("candidate", candidate)):
        if frame.empty or "patient_id" not in frame or set(frame.patient_id) != {patient_id}:
            raise RuntimeError(f"Invalid {name} patient identity: {patient_id}")
    if set(raw.slice_key) != expected_keys or set(slices.slice_key) != expected_keys or set(candidate.slice_key) != expected_keys:
        raise RuntimeError(f"Patient slice set mismatch: {patient_id}")
    if set(raw.block_size) != expected_scales or set(slices.block_size) != expected_scales or set(candidate.block_size) != expected_scales or set(patient.block_size) != expected_scales:
        raise RuntimeError(f"Patient scale set mismatch: {patient_id}")
    counts = expected_grid_counts()
    raw_counts = raw.groupby(["slice_key", "block_size"], sort=False).size()
    expected_index = pd.MultiIndex.from_product([sorted(expected_keys), sorted(expected_scales)], names=["slice_key", "block_size"])
    if not raw_counts.index.is_unique or set(raw_counts.index) != set(expected_index) or any(raw_counts.loc[(key, scale)] != counts[scale] for key, scale in expected_index):
        raise RuntimeError(f"Patient raw grid count mismatch: {patient_id}")
    if raw.duplicated(["slice_key", "block_size", "x", "y"]).any():
        raise RuntimeError(f"Duplicate raw response row: {patient_id}")
    for scale in expected_scales:
        actual = pd.MultiIndex.from_frame(raw.loc[raw.block_size.eq(scale), ["x", "y"]]).unique()
        if set(actual) != set(build_grid(224, scale, scale // 2)):
            raise RuntimeError(f"Patient raw grid positions mismatch: {patient_id}, scale {scale}")
    if len(slices) != len(expected_index) or slices.duplicated(["slice_key", "block_size"]).any():
        raise RuntimeError(f"Invalid slice summary chunk: {patient_id}")
    if len(candidate) != len(expected_index) or candidate.duplicated(["slice_key", "block_size"]).any():
        raise RuntimeError(f"Invalid candidate summary chunk: {patient_id}")
    if len(patient) != 3 or patient.block_size.duplicated().any() or not patient.slice_count.eq(len(expected_keys)).all():
        raise RuntimeError(f"Invalid patient summary chunk: {patient_id}")
    valid = candidate.loc[candidate.candidate_status.eq("valid")].groupby("slice_key").block_size.apply(set).to_dict()
    expected_pairs = {(key, a, b) for key, scales in valid.items()
                      for a, b in itertools.combinations(sorted(scales), 2)}
    actual_pairs = set(zip(cross.get("slice_key", []), cross.get("scale_a", []), cross.get("scale_b", [])))
    if actual_pairs != expected_pairs or len(cross) != len(expected_pairs) or (not cross.empty and set(cross.patient_id) != {patient_id}):
        raise RuntimeError(f"Invalid cross-scale chunk: {patient_id}")
    if not np.isfinite(raw.select_dtypes(include=[np.number]).to_numpy()).all():
        raise RuntimeError(f"Non-finite raw patient chunk: {patient_id}")
    return len(expected_keys)


def print_progress(state, expected_patients, expected_slices, expected_masks, started_monotonic, force=False):
    now = time.monotonic()
    last = float(state.get("last_progress_monotonic", 0.0))
    if not force and now - last < 30:
        return
    state["last_progress_monotonic"] = now
    elapsed = now - started_monotonic
    completed = int(state.get("completed_masked_inferences", 0))
    in_flight = int(state.get("inflight_masked_inferences", 0))
    observed = completed + in_flight
    session_observed = observed - int(state.get("session_start_masked_inferences", 0))
    rate = session_observed / elapsed if elapsed > 0 else 0.0
    remaining = (expected_masks - observed) / rate if rate > 0 else None
    percentage = 100.0 * observed / expected_masks if expected_masks else 0.0
    eta = f"{remaining / 3600:.2f} h" if remaining is not None else "unknown"
    print(
        f"FORMAL OCCLUSION progress: patients={len(state.get('completed_patients', []))}/{expected_patients} "
        f"committed_slices={state.get('processed_slices', 0)}/{expected_slices} "
        f"inflight_slices={state.get('inflight_slices', 0)} "
        f"committed_masks={completed}/{expected_masks} inflight_masks={in_flight} ({percentage:.3f}%) "
        f"elapsed={elapsed / 3600:.2f} h rate={rate:.2f}/s eta={eta} "
        f"nan_inf={state.get('nan_inf_count', 0)} failed_slices={state.get('failed_slices', 0)}",
        flush=True,
    )


def run_formal_validation(stage_config, stage_config_path, output_dir):
    freeze, checkpoint_path, split_dir = verify_frozen_inputs(stage_config, stage_config_path)
    if stage_config["data"]["primary_split"] != "val":
        raise RuntimeError("Frozen primary split is not validation")
    if stage_config["data"]["test_set_status"] != "SEALED":
        raise RuntimeError("Formal test is not sealed")
    if not torch.backends.mps.is_available():
        raise RuntimeError("Formal validation requires an available MPS device")

    baseline_config = load_config("configs/formal_baseline_rule_b_v1.yaml")
    validation_path = baseline_config["data"]["val_csv"]
    if validation_path != stage_config["data"]["primary_manifest"]:
        raise RuntimeError("Stage 1 primary manifest mismatch")
    validation = read_manifest(validation_path).copy()
    validation["instance_sort"] = pd.to_numeric(validation["instance_number"], errors="coerce")
    validation = validation.sort_values(["patient_id", "series_uid", "instance_sort", "image_path"])
    patients = sorted(validation.patient_id.unique())
    expected_slices = len(validation)
    expected_masks = expected_slices * sum(expected_grid_counts().values())
    if len(patients) != 28 or expected_slices != 5637 or expected_masks != 5264958:
        raise RuntimeError("Frozen validation counts do not match protocol")
    if "test" in validation_path.lower():
        raise RuntimeError("Test path detected in formal validation manifest")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_by_patient"
    slice_dir = output_dir / "slice_summary_by_patient"
    patient_dir = output_dir / "patient_summary_by_patient"
    candidate_dir = output_dir / "candidate_summary_by_patient"
    cross_dir = output_dir / "cross_scale_by_patient"
    for directory in (raw_dir, slice_dir, patient_dir, candidate_dir, cross_dir):
        directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        state = json.loads(manifest_path.read_text(encoding="utf-8"))
        if state.get("status") == "COMPLETE":
            raise RuntimeError("Formal validation is already COMPLETE")
        if state.get("protocol_sha256") != freeze["protocol_sha256"] or state.get("config_sha256") != freeze["config_sha256"]:
            raise RuntimeError("Resume provenance mismatch")
        listed = state.get("completed_patients", [])
        if len(listed) != len(set(listed)) or not set(listed).issubset(set(patients)):
            raise RuntimeError("Invalid completed patient list in resume manifest")
        completed = set(listed)
        committed_slices = 0
        for patient_id in completed:
            patient_rows = validation[validation.patient_id.eq(patient_id)]
            keys = [f"{patient_id}|{record.sop_uid}" for _, record in patient_rows.iterrows()]
            committed_slices += validate_patient_chunks(patient_id, keys, raw_dir, slice_dir,
                                                        patient_dir, candidate_dir, cross_dir)
        # A crash during a five-file commit can leave orphan files. Preserve them
        # and recompute that patient from the frozen validation manifest.
        orphan_paths = [path for directory in (raw_dir, slice_dir, patient_dir, candidate_dir, cross_dir)
                        for path in directory.iterdir() if path.is_file() and
                        (path.name.endswith(".partial") or
                         (path.name.startswith("patient_") and path.name.endswith(".parquet") and
                          path.stem[len("patient_"):] not in completed))]
        if orphan_paths:
            recovery_dir = output_dir / "recovery_orphans" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            for path in orphan_paths:
                destination = recovery_dir / path.parent.name / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, destination)
        state["completed_patients"] = sorted(completed)
        state["processed_slices"] = committed_slices
        state["completed_masked_inferences"] = int(state["processed_slices"] * 934)
        state["inflight_slices"] = 0
        state["inflight_masked_inferences"] = 0
        state["status"] = "RUNNING"
        state["resumed_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(manifest_path, state)
    else:
        state = {
            "status": "RUNNING",
            "protocol_id": stage_config["protocol_id"],
            "protocol_sha256": freeze["protocol_sha256"],
            "config_sha256": freeze["config_sha256"],
            "checkpoint_sha256": freeze["baseline_checkpoint_sha256"],
            "checkpoint_epoch": 2,
            "git_commit": git_commit(),
            "completed_patients": [],
            "processed_slices": 0,
            "completed_masked_inferences": 0,
            "inflight_slices": 0,
            "inflight_masked_inferences": 0,
            "nan_inf_count": 0,
            "failed_slices": 0,
            "expected_patients": len(patients),
            "expected_slices": expected_slices,
            "expected_masked_inferences": expected_masks,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        completed = set()
        atomic_write_json(manifest_path, state)

    state["session_start_masked_inferences"] = state["completed_masked_inferences"]

    model_config = {**baseline_config, "model": {**baseline_config["model"], "pretrained": False}}
    model = build_model(model_config)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if int(checkpoint.get("epoch", -1)) != 2:
        raise RuntimeError("Frozen checkpoint epoch is not 2")
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    torch.manual_seed(BOOTSTRAP_SEED)
    device = torch.device("mps")
    model.to(device)
    stop_requested = {"value": False}

    def request_stop(signum, _frame):
        stop_requested["value"] = True
        print(f"Received signal {signum}; will checkpoint at the next safe boundary.", flush=True)

    old_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    started_monotonic = time.monotonic()
    try:
        for patient_id in patients:
            if patient_id in completed:
                continue
            patient_rows = validation[validation.patient_id.eq(patient_id)]
            all_rows = []
            for _, record in patient_rows.iterrows():
                if stop_requested["value"]:
                    break
                try:
                    stages = preprocess_dicom(project_path(record.image_path), baseline_config, return_stages=True)
                    base_logits, base_probs = infer_logits(model, [stages.tensor], device, batch_size=1)
                    if not np.isfinite(base_logits).all() or not np.isfinite(base_probs).all():
                        raise FloatingPointError("non-finite baseline output")
                    p0 = float(base_probs[0, 1])
                    baseline_class = int(p0 >= 0.5)
                    for block_size, stride in zip(stage_config["masking"]["block_sizes"], stage_config["masking"]["strides"]):
                        positions = build_grid(224, int(block_size), int(stride))
                        tensors = [mask_resized(stages.resized, x, y, int(block_size), float(stage_config["preprocessing"]["fill"]))
                                   for x, y in positions]
                        masked_logits, masked_probs = infer_logits(model, tensors, device, batch_size=32)
                        if not np.isfinite(masked_logits).all() or not np.isfinite(masked_probs).all():
                            raise FloatingPointError("non-finite masked output")
                        slice_key = f"{patient_id}|{record.sop_uid}"
                        for (x, y), logits, probs in zip(positions, masked_logits, masked_probs):
                            all_rows.append({
                                "split": "val", "patient_id": patient_id,
                                "study_uid": record.study_uid, "series_uid": record.series_uid,
                                "sop_uid": record.sop_uid, "slice_key": slice_key,
                                "image_path_hash": hashlib.sha256(record.image_path.encode()).hexdigest(),
                                "block_size": int(block_size), "stride": int(stride), "x": int(x), "y": int(y),
                                "baseline_logit_negative": float(base_logits[0, 0]),
                                "baseline_logit_positive": float(base_logits[0, 1]),
                                "masked_logit_negative": float(logits[0]), "masked_logit_positive": float(logits[1]),
                                "p0": p0, "pg": float(probs[1]),
                                "baseline_class": baseline_class, "masked_class": int(probs[1] >= 0.5),
                                "q0": float(base_probs[0, baseline_class]), "qg": float(probs[baseline_class]),
                            })
                    state["inflight_slices"] += 1
                    state["inflight_masked_inferences"] += sum(expected_grid_counts().values())
                    print_progress(state, len(patients), expected_slices, expected_masks, started_monotonic)
                except FloatingPointError:
                    state["nan_inf_count"] += 1
                    state["failed_slices"] += 1
                    atomic_write_json(manifest_path, {**state, "status": "FAILED"})
                    raise
                except Exception:
                    state["failed_slices"] += 1
                    atomic_write_json(manifest_path, {**state, "status": "FAILED"})
                    raise
            if stop_requested["value"]:
                state["status"] = "INTERRUPTED"
                atomic_write_json(manifest_path, state)
                print_progress(state, len(patients), expected_slices, expected_masks, started_monotonic, force=True)
                return state

            raw = add_response_metrics(all_rows)
            atomic_write_parquet(raw, raw_dir / f"patient_{patient_id}.parquet")
            atomic_write_parquet(slice_summary(raw), slice_dir / f"patient_{patient_id}.parquet")
            atomic_write_parquet(patient_first_summary(raw), patient_dir / f"patient_{patient_id}.parquet")
            atomic_write_parquet(candidate_summary(raw), candidate_dir / f"patient_{patient_id}.parquet")
            atomic_write_parquet(cross_scale_slice_summary(raw), cross_dir / f"patient_{patient_id}.parquet")
            keys = [f"{patient_id}|{record.sop_uid}" for _, record in patient_rows.iterrows()]
            committed_count = validate_patient_chunks(patient_id, keys, raw_dir, slice_dir,
                                                      patient_dir, candidate_dir, cross_dir)
            if committed_count != state["inflight_slices"]:
                raise RuntimeError(f"In-flight patient slice count mismatch: {patient_id}")
            state["processed_slices"] += committed_count
            state["completed_masked_inferences"] += committed_count * 934
            state["inflight_slices"] = 0
            state["inflight_masked_inferences"] = 0
            state["completed_patients"].append(patient_id)
            completed.add(patient_id)
            state["last_checkpoint_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(manifest_path, state)
            print_progress(state, len(patients), expected_slices, expected_masks, started_monotonic, force=True)

        slice_frames = [pd.read_parquet(path) for path in sorted(slice_dir.glob("patient_*.parquet"))]
        patient_frames = [pd.read_parquet(path) for path in sorted(patient_dir.glob("patient_*.parquet"))]
        candidate_frames = [pd.read_parquet(path) for path in sorted(candidate_dir.glob("patient_*.parquet"))]
        cross_frames = [pd.read_parquet(path) for path in sorted(cross_dir.glob("patient_*.parquet"))]
        slice_all = pd.concat(slice_frames, ignore_index=True)
        patient_all = pd.concat(patient_frames, ignore_index=True)
        candidate_all = pd.concat(candidate_frames, ignore_index=True)
        cross_all = pd.concat(cross_frames, ignore_index=True) if cross_frames else pd.DataFrame()
        atomic_write_parquet(slice_all, output_dir / "slice_summaries.parquet")
        atomic_write_parquet(patient_all, output_dir / "patient_summaries.parquet")
        atomic_write_parquet(candidate_all, output_dir / "candidate_region_summary.parquet")
        atomic_write_parquet(cross_all, output_dir / "cross_scale_stability.parquet")
        slice_all.to_csv(output_dir / "slice_summaries.csv", index=False)
        patient_all.to_csv(output_dir / "patient_summaries.csv", index=False)
        candidate_all.to_csv(output_dir / "candidate_region_summary.csv", index=False)
        cross_all.to_csv(output_dir / "cross_scale_stability.csv", index=False)
        cross_patient = cross_scale_patient_summary(cross_all)
        atomic_write_parquet(cross_patient, output_dir / "cross_scale_patient_summaries.parquet")
        cross_patient.to_csv(output_dir / "cross_scale_patient_summaries.csv", index=False)

        actual_patients = int(patient_all.patient_id.nunique())
        actual_slices = int(slice_all[["patient_id", "slice_key"]].drop_duplicates().shape[0])
        if actual_patients != 28 or actual_slices != 5637:
            raise RuntimeError(
                f"Final output count mismatch: patients={actual_patients}, slices={actual_slices}"
            )
        if int(state["completed_masked_inferences"]) != expected_masks:
            raise RuntimeError("Final masked inference count mismatch")
        if int(state["nan_inf_count"]) or int(state["failed_slices"]):
            raise RuntimeError("Formal validation has non-finite outputs or failed slices")

        cohort_rows = []
        metric_columns = ["median_absolute_probability_change", "iqr_absolute_probability_change",
                          "p90_absolute_probability_change", "p95_absolute_probability_change",
                          "flip_rate", "position_variance", "valid_response_slice_proportion"]
        for block_size, group in patient_all.groupby("block_size", sort=True):
            row = {"block_size": int(block_size), "patient_count": int(group.patient_id.nunique())}
            for metric in metric_columns:
                row[f"{metric}_patient_median"] = float(group[metric].median())
                row[f"{metric}_patient_iqr"] = float(group[metric].quantile(.75) - group[metric].quantile(.25))
                row[f"{metric}_bootstrap"] = patient_bootstrap(group[metric].to_numpy())
            cohort_rows.append(row)
        cohort = pd.DataFrame(cohort_rows)
        cohort.to_json(output_dir / "cohort_summary.json", orient="records", indent=2)
        cohort.to_csv(output_dir / "cohort_summary.csv", index=False)

        run_manifest = {
            **state,
            "status": "COMPLETE",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_seconds": float(time.monotonic() - started_monotonic),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "baseline_checkpoint_unchanged": sha256_file(checkpoint_path) == freeze["baseline_checkpoint_sha256"],
            "test_dataset_constructed": False, "test_pixels_read": False,
            "test_inference": False, "test_predictions": False, "test_metrics": False,
            "nan_inf_count": int(state["nan_inf_count"]),
            "failed_slices": int(state["failed_slices"]),
            "raw_patient_chunks": sorted(str(path.relative_to(PROJECT_ROOT)) for path in raw_dir.glob("patient_*.parquet")),
        }
        atomic_write_json(manifest_path, {**run_manifest, "status": "FINALIZING"})
        qa = {
            "status": "PASS",
            "expected_patients": 28, "processed_patients": actual_patients,
            "expected_slices": 5637, "processed_slices": actual_slices,
            "expected_masked_inferences": 5264958,
            "completed_masked_inferences": int(state["completed_masked_inferences"]),
            "mask_counts": expected_grid_counts(), "total_masks_per_slice": 934,
            "protocol_sha256": freeze["protocol_sha256"], "config_sha256": freeze["config_sha256"],
            "checkpoint_sha256": sha256_file(checkpoint_path), "checkpoint_epoch": 2,
            "nan_inf_count": int(state["nan_inf_count"]), "failed_slices": int(state["failed_slices"]),
            "test_access": False, "patient_first_aggregation": True,
            "projection": "14x14 deterministic area-average pooling",
        }
        atomic_write_json(output_dir / "qa_report.json", qa)
        atomic_write_json(output_dir / "provenance.json", {
            "protocol_id": stage_config["protocol_id"], "experiment_id": stage_config["experiment_id"],
            "protocol_sha256": freeze["protocol_sha256"], "config_sha256": freeze["config_sha256"],
            "checkpoint_sha256": sha256_file(checkpoint_path), "checkpoint_epoch": 2,
            "git_commit": git_commit(), "frozen_split_hashes": freeze["formal_split_hashes"],
            "seed": BOOTSTRAP_SEED, "masking": {"block_sizes": [16, 32, 64], "strides": [8, 16, 32], "fill": 0.5},
            "comparison_grid": "14x14", "projection": "deterministic area-average pooling",
            "test_set_status": "SEALED", "test_dataset_constructed": False,
            "test_pixels_read": False, "test_inference": False,
            "runtime": {"python": platform.python_version(), "torch": torch.__version__, "torchvision": torchvision.__version__},
        })
        result_artifacts = [
            output_dir / "slice_summaries.parquet",
            output_dir / "patient_summaries.parquet",
            output_dir / "candidate_region_summary.parquet",
            output_dir / "cross_scale_stability.parquet",
            output_dir / "cross_scale_patient_summaries.parquet",
            output_dir / "cohort_summary.json",
            output_dir / "qa_report.json",
            output_dir / "provenance.json",
            *sorted(raw_dir.glob("patient_*.parquet")),
        ]
        result_hashes = {
            str(path.relative_to(PROJECT_ROOT)): sha256_file(path)
            for path in result_artifacts
        }
        atomic_write_json(output_dir / "result_freeze.json", {
            "status": "FROZEN",
            "protocol_id": stage_config["protocol_id"],
            "experiment_id": stage_config["experiment_id"],
            "protocol_sha256": freeze["protocol_sha256"],
            "config_sha256": freeze["config_sha256"],
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "formal_split_hashes": freeze["formal_split_hashes"],
            "metadata_confounding_status": "PRESENT_AND_UNRESOLVED",
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifact_sha256": result_hashes,
        })
        atomic_write_json(manifest_path, run_manifest)
        print(json.dumps(qa, indent=2))
        return qa
    finally:
        signal.signal(signal.SIGINT, old_handlers[signal.SIGINT])
        signal.signal(signal.SIGTERM, old_handlers[signal.SIGTERM])


def select_train_fixture(manifest_path, slices_per_patient=2, patient_count=2):
    frame = read_manifest(manifest_path).copy()
    frame["instance_sort"] = pd.to_numeric(frame.get("instance_number", ""), errors="coerce")
    frame = frame.sort_values(["patient_id", "series_uid", "instance_sort", "image_path"])
    selected = frame.groupby("patient_id", sort=True, group_keys=False).head(slices_per_patient).head(patient_count * slices_per_patient)
    if selected.patient_id.nunique() != patient_count or len(selected) != patient_count * slices_per_patient:
        raise AssertionError("fixed train fixture selection failed")
    return selected.drop(columns=["instance_sort"]).reset_index(drop=True)


def run_smoke(stage_config, stage_config_path, output_dir):
    freeze, checkpoint_path, _ = verify_frozen_inputs(stage_config, stage_config_path)
    assert stage_config["masking"]["block_sizes"] == [16, 32, 64]
    assert stage_config["masking"]["strides"] == [8, 16, 32]
    assert float(stage_config["preprocessing"]["fill"]) == 0.5
    assert stage_config["spatial"]["comparison_grid"] == [14, 14]
    assert stage_config["spatial"]["projection"] == "deterministic_area_average_pooling"
    assert float(stage_config["response"]["candidate"]["epsilon_num"]) == EPSILON_NUM
    assert float(stage_config["response"]["candidate"]["top_fraction"]) == 0.10
    baseline_config = load_config("configs/formal_baseline_rule_b_v1.yaml")
    fixture = select_train_fixture(baseline_config["data"]["train_csv"])
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "train_fixture.csv"
    fixture.to_csv(fixture_path, index=False, lineterminator="\n")
    provenance = {
        "protocol_id": stage_config["protocol_id"],
        "experiment_id": stage_config["experiment_id"],
        "protocol_sha256": freeze["protocol_sha256"],
        "config_sha256": freeze["config_sha256"],
        "checkpoint_sha256": freeze["baseline_checkpoint_sha256"],
        "checkpoint_epoch": int(stage_config["baseline"]["best_epoch"]),
        "git_commit": git_commit(),
        "frozen_split_hashes": freeze["formal_split_hashes"],
        "seed": BOOTSTRAP_SEED,
        "masking": {"block_sizes": [16, 32, 64], "strides": [8, 16, 32], "fill": 0.5},
        "comparison_grid": "14x14",
        "projection": "deterministic area-average pooling",
        "test_set_status": "SEALED",
        "test_dataset_constructed": False,
        "test_pixels_read": False,
        "test_inference": False,
        "runtime": {"python": platform.python_version(), "torch": torch.__version__, "torchvision": torchvision.__version__},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    model_config = {**baseline_config, "model": {**baseline_config["model"], "pretrained": False}}
    model = build_model(model_config)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    assert checkpoint["epoch"] == 2
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    torch.manual_seed(BOOTSTRAP_SEED)
    device = torch.device("cpu")
    model.to(device)

    rows = []
    baseline_inference_consistent = True
    batch_single_consistent = True
    baseline_cache = {}
    with torch.inference_mode():
        for idx, record in fixture.iterrows():
            stages = preprocess_dicom(project_path(record.image_path), baseline_config, return_stages=True)
            baseline_logits, baseline_probs = infer_logits(model, [stages.tensor], device, batch_size=1)
            with torch.inference_mode():
                direct_logits = model(stages.tensor.unsqueeze(0).to(device)).detach().cpu().numpy()
            baseline_inference_consistent &= bool(np.allclose(baseline_logits, direct_logits, rtol=1e-5, atol=1e-6))
            baseline_cache[idx] = (stages.resized, baseline_logits[0], baseline_probs[0])
            p0 = float(baseline_probs[0, 1])
            baseline_class = int(p0 >= 0.5)
            for block_size, stride in zip(stage_config["masking"]["block_sizes"], stage_config["masking"]["strides"]):
                positions = build_grid(224, int(block_size), int(stride))
                tensors = [mask_resized(stages.resized, x, y, int(block_size), float(stage_config["preprocessing"]["fill"])) for x, y in positions]
                masked_logits, masked_probs = infer_logits(model, tensors, device, batch_size=32)
                one_logits, _ = infer_logits(model, [tensors[0]], device, batch_size=1)
                batch_single_consistent &= bool(np.allclose(masked_logits[0], one_logits[0], rtol=1e-5, atol=1e-6))
                for (x, y), z, probs in zip(positions, masked_logits, masked_probs):
                    q0 = float(probs[baseline_class] * 0 + baseline_probs[0, baseline_class])
                    qg = float(probs[baseline_class])
                    rows.append({
                        "fixture_id": f"f{idx}",
                        "slice_key": f"f{idx}",
                        "patient_id": record.patient_id,
                        "image_path_hash": hashlib.sha256(record.image_path.encode()).hexdigest(),
                        "block_size": int(block_size),
                        "stride": int(stride),
                        "x": int(x), "y": int(y),
                        "baseline_logit_negative": float(baseline_logits[0, 0]),
                        "baseline_logit_positive": float(baseline_logits[0, 1]),
                        "masked_logit_negative": float(z[0]),
                        "masked_logit_positive": float(z[1]),
                        "p0": p0, "pg": float(probs[1]),
                        "baseline_class": baseline_class,
                        "masked_class": int(probs[1] >= 0.5),
                        "q0": q0, "qg": qg,
                    })
    raw = add_response_metrics(rows)
    if not np.isfinite(raw.select_dtypes(include=[np.number]).to_numpy()).all():
        raise FloatingPointError("non-finite smoke response")
    raw.to_parquet(output_dir / "raw_responses.parquet", index=False)
    raw.to_csv(output_dir / "raw_responses.csv", index=False)
    summary = patient_first_summary(raw)
    summary.to_csv(output_dir / "patient_summary.csv", index=False)

    projection_rows = []
    for (fixture_id, block_size), group in raw.groupby(["fixture_id", "block_size"], sort=True):
        response_map = rasterize_block_scores(group, "candidate_response")
        projected = project_area_average(response_map)
        candidate_map = rasterize_block_scores(group.assign(candidate_response=group.candidate_selected.astype(float)), "candidate_response") > 0
        projected_candidate = project_area_average(candidate_map.astype(float)) > 0
        projection_rows.append({"fixture_id": fixture_id, "block_size": int(block_size), "map": projected.tolist(), "candidate_map": projected_candidate.tolist()})
    projection = pd.DataFrame(projection_rows)
    projection.to_json(output_dir / "projection_14x14.json", orient="records", indent=2)
    cross_scale = []
    for fixture_id, group in projection.groupby("fixture_id", sort=True):
        records = {int(r.block_size): r for r in group.itertuples(index=False)}
        scales = sorted(records)
        for left, right in itertools.combinations(scales, 2):
            a, b = records[left], records[right]
            cross_scale.append({"fixture_id": fixture_id, "scale_a": left, "scale_b": right,
                                **spatial_metrics(np.asarray(a.map), np.asarray(b.map), np.asarray(a.candidate_map), np.asarray(b.candidate_map))})
    pd.DataFrame(cross_scale).to_csv(output_dir / "cross_scale_metrics.csv", index=False)
    bootstrap = {"median_absolute_probability_change": patient_bootstrap(summary.median_absolute_probability_change)}
    (output_dir / "patient_bootstrap.json").write_text(json.dumps(bootstrap, indent=2), encoding="utf-8")

    report = {
        "status": "PASS",
        "mode": "smoke",
        "protocol_id": stage_config["protocol_id"],
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "checkpoint_epoch": int(checkpoint["epoch"]),
        "fixture_patients": int(fixture.patient_id.nunique()),
        "fixture_slices": int(len(fixture)),
        "mask_counts": expected_grid_counts(),
        "total_masks_per_slice": int(sum(expected_grid_counts().values())),
        "raw_parquet": str((output_dir / "raw_responses.parquet").relative_to(PROJECT_ROOT)),
        "projection": "14x14 deterministic area-average pooling",
        "candidate_rule_verified": True,
        "insufficient_response_rule_verified": True,
        "baseline_inference_consistent": baseline_inference_consistent,
        "batch_single_tolerance_verified": batch_single_consistent,
        "finite_outputs_verified": True,
        "test_dataset_constructed": False,
        "test_pixels_read": False,
        "test_inference": False,
        "test_predictions": False,
        "test_metrics": False,
        "baseline_checkpoint_unchanged": sha256_file(checkpoint_path) == freeze["baseline_checkpoint_sha256"],
        "summary_sha256": sha256_file(output_dir / "patient_summary.csv"),
    }
    (output_dir / "smoke_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--smoke", action="store_true", help="run only the fixed train fixture smoke")
    modes.add_argument("--formal-validation", action="store_true", help="run the frozen validation protocol")
    parser.add_argument("--config", default="configs/occlusion_instability_v1.yaml")
    args = parser.parse_args()
    stage_config, config_path = load_stage_config(args.config)
    if args.smoke:
        output_dir = PROJECT_ROOT / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/smoke"
        report = run_smoke(stage_config, config_path, output_dir)
    else:
        output_dir = PROJECT_ROOT / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation"
        report = run_formal_validation(stage_config, config_path, output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
