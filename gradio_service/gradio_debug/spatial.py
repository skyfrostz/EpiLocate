"""Display-only projection from raw CT through the API's spatial metadata."""
from __future__ import annotations

import io
import math

from PIL import Image


def aligned_overlay(preview_png: bytes, response_png: bytes, geometry: dict, layer: dict) -> Image.Image:
    raw = Image.open(io.BytesIO(preview_png)).convert("RGB")
    response = Image.open(io.BytesIO(response_png)).convert("L")
    raw_size = (geometry["raw_width"], geometry["raw_height"])
    algorithm_size = (geometry["algorithm_width"], geometry["algorithm_height"])
    if raw.size != raw_size or response.size != (layer["width"], layer["height"]):
        raise ValueError("图像尺寸与后端空间元数据不一致。")
    if response.size != algorithm_size or layer["coordinate_space"] != "ALGORITHM_224":
        raise ValueError("响应图不在当前算法输入坐标空间。")
    if geometry["coordinate_origin"] != "TOP_LEFT_PIXEL_EDGE" or layer["origin"] != "TOP_LEFT_PIXEL_EDGE":
        raise ValueError("不支持的坐标原点。")
    a, b, c, d, e, f, g, h, i = geometry["raw_to_algorithm_edge_affine"]
    if not all(math.isfinite(v) for v in (a, b, c, d, e, f, g, h, i)) or (g, h, i) != (0, 0, 1):
        raise ValueError("无效的后端空间变换。")
    det = a * e - b * d
    if abs(det) < 1e-12:
        raise ValueError("空间变换不可逆。")
    inverse = (e / det, -b / det, (b * f - e * c) / det,
               -d / det, a / det, (d * c - a * f) / det)
    # Output pixels are algorithm pixels. PIL samples the raw image through the
    # inverse edge affine; both layers then share one display raster and zoom.
    aligned = raw.transform(algorithm_size, Image.Transform.AFFINE, inverse,
                            resample=Image.Resampling.BILINEAR)
    alpha = response.point(lambda value: round(value * 0.56))
    color = Image.new("RGBA", algorithm_size, (255, 92, 23, 0))
    color.putalpha(alpha)
    return Image.alpha_composite(aligned.convert("RGBA"), color).convert("RGB")
