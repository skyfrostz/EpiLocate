"""Geometry shared by the 64, 32 and 16 pixel P2 grids."""
from __future__ import annotations

IMAGE_SIZE = 224
SCALES = (64, 32, 16)
GRID_COUNTS = {64: 36, 32: 169, 16: 729}
MARGINS = {(64, 32): 16, (32, 16): 8}
EPSILON = 1e-6


def grid(scale: int) -> tuple[tuple[int, int], ...]:
    stride = scale // 2
    starts = range(0, IMAGE_SIZE - scale + 1, stride)
    return tuple((x, y) for y in starts for x in starts)


GRIDS = {scale: grid(scale) for scale in SCALES}


def _overlap_positive(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _expanded_box(index: int, parent_scale: int, margin: int) -> tuple[int, int, int, int]:
    x, y = GRIDS[parent_scale][index]
    return (max(0, x - margin), max(0, y - margin),
            min(IMAGE_SIZE, x + parent_scale + margin),
            min(IMAGE_SIZE, y + parent_scale + margin))


def _child_box(index: int, child_scale: int) -> tuple[int, int, int, int]:
    x, y = GRIDS[child_scale][index]
    return x, y, x + child_scale, y + child_scale


def _make_child_lookup(parent_scale: int, child_scale: int) -> tuple[tuple[int, ...], ...]:
    margin = MARGINS[(parent_scale, child_scale)]
    return tuple(tuple(j for j in range(GRID_COUNTS[child_scale])
                       if _overlap_positive(_expanded_box(i, parent_scale, margin),
                                            _child_box(j, child_scale)))
                 for i in range(GRID_COUNTS[parent_scale]))


CHILD_LOOKUP = {pair: _make_child_lookup(*pair) for pair in MARGINS}
