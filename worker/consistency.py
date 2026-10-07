"""Capture and compare synthetic CPU/CUDA Worker results without changing inference."""
from __future__ import annotations

import base64
import hashlib
import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .inference import InferenceOutput


@dataclass(frozen=True)
class NumericalTolerance:
    probability_abs: float = 1e-4
    derived_abs: float = 1e-4
    png_pixel_abs: int = 2


TOLERANCE = NumericalTolerance()


def capture_bundle(output: InferenceOutput, input_sha256: str, device: str) -> dict:
    """Keep numeric results and decoded-comparable PNG bytes from a synthetic run."""
    layers = {layer["asset_id"]: layer for summary in output.result.get("scale_summaries", [])
              for layer in (summary.get("response_layer"), summary.get("candidate_layer"),
                            summary.get("comparison_grid_layer")) if layer is not None}
    assets = {}
    for name, (data, media_type) in sorted(output.assets.items()):
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            geometry = {"width": image.width, "height": image.height, "mode": image.mode}
        assets[name] = {
            "layer_kind": layers[name]["layer_kind"], "coordinate_space": layers[name]["coordinate_space"],
            "media_type": media_type, "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data), "png_base64": base64.b64encode(data).decode("ascii"), **geometry,
        }
    return {"bundle_version": "1.0", "device": device, "input_sha256": input_sha256,
            "model_hash": output.result["model_version"], "result": output.result, "assets": assets}


def _decoded(asset: dict) -> np.ndarray:
    data = base64.b64decode(asset["png_base64"], validate=True)
    if hashlib.sha256(data).hexdigest() != asset["sha256"] or len(data) != asset["size_bytes"]:
        raise ValueError("Reference PNG integrity check failed")
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if (image.width, image.height, image.mode) != (asset["width"], asset["height"], asset["mode"]):
            raise ValueError("Reference PNG geometry check failed")
        return np.asarray(image).astype(np.int16)


def compare_bundles(reference: dict, candidate: dict, tolerance: NumericalTolerance = TOLERANCE) -> dict:
    failures: list[str] = []
    maxima = {"probability_abs": 0.0, "derived_abs": 0.0, "png_pixel_abs": 0}

    def exact(path: str, left, right) -> None:
        if left != right:
            failures.append(path)

    def numeric(path: str, left, right, category: str) -> None:
        if type(left) not in (float, int) or type(right) not in (float, int) or not math.isfinite(left) or not math.isfinite(right):
            failures.append(path)
            return
        delta = abs(float(left) - float(right))
        maxima[category] = max(maxima[category], delta)
        limit = tolerance.probability_abs if category == "probability_abs" else tolerance.derived_abs
        if delta > limit:
            failures.append(path)

    for key in ("bundle_version", "input_sha256", "model_hash"):
        exact(key, reference.get(key), candidate.get(key))
    left, right = reference["result"], candidate["result"]
    exact("result.keys", set(left), set(right))
    for key in ("contract_version", "source", "case_id", "slice_id", "kind", "model_id",
                "model_version", "preprocessing_version", "protocol_id"):
        exact("result." + key, left.get(key), right.get(key))
    lp, rp = left["prediction"], right["prediction"]
    exact("prediction.keys", set(lp), set(rp))
    for key in ("predicted_class", "class_label"):
        exact("prediction." + key, lp.get(key), rp.get(key))
    for key in ("positive_probability", "predicted_class_confidence"):
        numeric("prediction." + key, lp.get(key), rp.get(key), "probability_abs")
    # inference_time_ms is measured performance, not a numerical model output.
    for key in ("scale_summaries", "positions", "cross_scale"):
        exact(key + ".count", len(left.get(key, [])), len(right.get(key, [])))
    for index, (ls, rs) in enumerate(zip(left.get("scale_summaries", []), right.get("scale_summaries", []))):
        prefix = f"scale_summaries[{index}]"
        exact(prefix + ".keys", set(ls), set(rs))
        for key in ("block_size", "stride", "fill", "candidate_status"):
            exact(prefix + "." + key, ls.get(key), rs.get(key))
        for key in ("baseline_positive_probability", "median_absolute_probability_change", "flip_rate", "candidate_area_fraction"):
            lv, rv = ls.get(key), rs.get(key)
            if lv is None or rv is None:
                exact(prefix + "." + key, lv, rv)
            else:
                numeric(prefix + "." + key, lv, rv, "derived_abs")
        for key in ("response_layer", "candidate_layer", "comparison_grid_layer"):
            ll, rl = ls.get(key), rs.get(key)
            if ll is None or rl is None:
                exact(prefix + "." + key, ll, rl)
                continue
            exact(prefix + "." + key + ".keys", set(ll), set(rl))
            for field in ("asset_id", "layer_kind", "width", "height", "coordinate_space", "origin",
                          "x_axis", "y_axis", "display_interpolation_only"):
                exact(prefix + "." + key + "." + field, ll.get(field), rl.get(field))
            for field in ("value_min", "value_max"):
                numeric(prefix + "." + key + "." + field, ll.get(field), rl.get(field), "derived_abs")
    for index, (lp_, rp_) in enumerate(zip(left.get("positions", []), right.get("positions", []))):
        prefix = f"positions[{index}]"
        exact(prefix + ".keys", set(lp_), set(rp_))
        for key in ("block_size", "x", "y", "prediction_flip"):
            exact(prefix + "." + key, lp_.get(key), rp_.get(key))
        for key in ("baseline_positive_probability", "masked_positive_probability",
                    "decision_confidence_drop", "candidate_response"):
            numeric(prefix + "." + key, lp_.get(key), rp_.get(key), "derived_abs")
    for index, (lc, rc) in enumerate(zip(left.get("cross_scale", []), right.get("cross_scale", []))):
        prefix = f"cross_scale[{index}]"
        exact(prefix + ".keys", set(lc), set(rc))
        for key in set(lc) | set(rc):
            if key in {"scale_a", "scale_b"} or lc.get(key) is None or rc.get(key) is None:
                exact(prefix + "." + key, lc.get(key), rc.get(key))
            else:
                numeric(prefix + "." + key, lc.get(key), rc.get(key), "derived_abs")
    exact("assets.names", set(reference["assets"]), set(candidate["assets"]))
    for name in sorted(set(reference["assets"]) & set(candidate["assets"])):
        la, ra = reference["assets"][name], candidate["assets"][name]
        for key in ("layer_kind", "coordinate_space", "media_type", "width", "height", "mode"):
            exact(f"assets.{name}.{key}", la.get(key), ra.get(key))
        try:
            left_pixels, right_pixels = _decoded(la), _decoded(ra)
        except (ValueError, OSError) as exc:
            failures.append(f"assets.{name}.decode:{type(exc).__name__}")
            continue
        if left_pixels.shape != right_pixels.shape:
            failures.append(f"assets.{name}.shape")
            continue
        delta = int(np.max(np.abs(left_pixels - right_pixels)))
        maxima["png_pixel_abs"] = max(maxima["png_pixel_abs"], delta)
        limit = 0 if la["layer_kind"] == "CANDIDATE_TOP10" else tolerance.png_pixel_abs
        if delta > limit:
            failures.append(f"assets.{name}.pixels")
    return {"passed": not failures, "failures": failures, "maxima": maxima,
            "tolerance": {"probability_abs": tolerance.probability_abs,
                          "derived_abs": tolerance.derived_abs, "png_pixel_abs": tolerance.png_pixel_abs}}
