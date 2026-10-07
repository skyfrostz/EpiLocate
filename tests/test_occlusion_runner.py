import numpy as np
import pandas as pd
import pytest

from scripts.occlusion_runner import (
    EPSILON_NUM,
    add_response_metrics,
    build_grid,
    expected_grid_counts,
    patient_bootstrap,
    project_area_average,
    spatial_metrics,
    validate_patient_chunks,
)


def test_primary_grid_counts_and_bounds():
    assert expected_grid_counts() == {16: 729, 32: 169, 64: 36}
    assert sum(expected_grid_counts().values()) == 934
    for block, stride in ((16, 8), (32, 16), (64, 32)):
        positions = build_grid(224, block, stride)
        assert all(0 <= x <= 224 - block and 0 <= y <= 224 - block for x, y in positions)
        assert len({(x, y) for x, y in positions}) == len(positions)


def test_candidate_response_uses_baseline_decision_class_and_top10():
    rows = []
    for x in range(10):
        rows.append({
            "fixture_id": "f0", "slice_key": "s0", "block_size": 16, "x": x, "y": 0,
            "p0": 0.2, "pg": 0.2 - x * 0.01,
            "q0": 0.8, "qg": 0.8 - x * 0.01,
            "baseline_class": 0, "masked_class": 0,
        })
    result = add_response_metrics(rows)
    assert np.allclose(result.decision_confidence_drop, result.q0 - result.qg)
    assert np.allclose(result.candidate_response, np.maximum(result.q0 - result.qg, 0))
    assert result.candidate_status.iloc[0] == "valid"
    assert result.candidate_selected.sum() >= 1
    assert (result.candidate_response[result.candidate_selected] > EPSILON_NUM).all()


def test_raw_probability_metrics_use_positive_probability_not_decision_confidence():
    rows = []
    pg = np.array([0.10, 0.25, 0.40, 0.55])
    qg = np.array([0.95, 0.90, 0.85, 0.80])
    for idx in range(len(pg)):
        rows.append({
            "fixture_id": "f0", "slice_key": "s0", "block_size": 16,
            "x": idx, "y": 0, "p0": 0.60, "pg": pg[idx],
            "q0": 0.90, "qg": qg[idx], "baseline_class": 1,
            "masked_class": int(pg[idx] >= 0.5),
        })
    result = add_response_metrics(rows)
    assert np.allclose(result.signed_probability_drop, 0.60 - pg)
    assert np.allclose(result.absolute_probability_change, np.abs(0.60 - pg))
    assert np.allclose(result.position_variance, np.var(pg, ddof=0))
    assert np.allclose(
        result.p95_absolute_probability_change,
        np.quantile(np.abs(0.60 - pg), 0.95),
    )
    assert np.allclose(result.decision_confidence_drop, 0.90 - qg)
    assert np.allclose(result.candidate_response, np.maximum(0.90 - qg, 0.0))


def test_insufficient_positive_response_does_not_select_zero_blocks():
    rows = [{
        "fixture_id": "f0", "slice_key": "s0", "block_size": 16, "x": i, "y": 0,
        "p0": 0.2, "pg": 0.2, "q0": 0.8, "qg": 0.8,
        "baseline_class": 0, "masked_class": 0,
    } for i in range(10)]
    result = add_response_metrics(rows)
    assert (result.candidate_status == "insufficient_positive_response").all()
    assert not result.candidate_selected.any()


def test_projection_is_deterministic_area_average():
    image = np.arange(224 * 224, dtype=float).reshape(224, 224)
    first = project_area_average(image)
    second = project_area_average(image.copy())
    assert first.shape == (14, 14)
    assert np.array_equal(first, second)
    assert first[0, 0] == image[:16, :16].mean()
    assert first[-1, -1] == image[-16:, -16:].mean()


def test_spatial_metrics_include_normalized_center_distance():
    left = np.zeros((14, 14), dtype=float)
    right = np.zeros((14, 14), dtype=float)
    left[0, 0] = 1.0
    right[-1, -1] = 1.0
    metrics = spatial_metrics(left, right, left > 0, right > 0)
    assert np.isclose(metrics["normalized_center_distance"], 1.0)


def test_patient_bootstrap_is_deterministic():
    values = np.array([0.1, 0.2, 0.3, 0.4])
    assert patient_bootstrap(values) == patient_bootstrap(values)


def test_committed_patient_requires_complete_consistent_chunks(tmp_path):
    names = ["raw", "slice", "patient", "candidate", "cross"]
    directories = [tmp_path / name for name in names]
    for directory in directories:
        directory.mkdir()
    raw = pd.DataFrame([
        {"patient_id": "p1", "slice_key": "p1|s1", "block_size": scale,
         "x": x, "y": y, "pg": 0.5}
        for scale in (16, 32, 64)
        for x, y in build_grid(224, scale, scale // 2)
    ])
    slice_rows = pd.DataFrame({"patient_id": ["p1"] * 3, "slice_key": ["p1|s1"] * 3,
                               "block_size": [16, 32, 64]})
    patient_rows = pd.DataFrame({"patient_id": ["p1"] * 3, "block_size": [16, 32, 64],
                                 "slice_count": [1] * 3})
    candidate_rows = slice_rows.assign(candidate_status="valid")
    cross_rows = pd.DataFrame({"patient_id": ["p1"] * 3, "slice_key": ["p1|s1"] * 3,
                               "scale_a": [16, 16, 32], "scale_b": [32, 64, 64]})
    for directory, frame in zip(directories, [raw, slice_rows, patient_rows, candidate_rows, cross_rows]):
        frame.to_parquet(directory / "patient_p1.parquet", index=False)
    assert validate_patient_chunks("p1", ["p1|s1"], *directories) == 1

    raw.loc[1, ["x", "y"]] = raw.loc[0, ["x", "y"]]
    raw.to_parquet(directories[0] / "patient_p1.parquet", index=False)
    with pytest.raises(RuntimeError, match="Duplicate raw response row"):
        validate_patient_chunks("p1", ["p1|s1"], *directories)

    (directories[4] / "patient_p1.parquet").unlink()
    with pytest.raises(RuntimeError, match="Incomplete patient chunks"):
        validate_patient_chunks("p1", ["p1|s1"], *directories)
