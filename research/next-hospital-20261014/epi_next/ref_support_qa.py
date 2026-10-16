"""Independent support oracle for declared nearest-floor patch exports.

No SPI/CPF/PSMI selector, model, patient files or GT construction. Producers must
declare sampling conventions; a different convention requires another oracle.
"""
import numpy as np


def patch_support(image_shape, grid_shape, cell):
    """Entire cell under legacy nearest floor(output_index * grid / image)."""
    h, w = image_shape
    gy, gx = grid_shape
    cy, cx = cell
    if any(type(v) is not int or v <= 0 for v in (h, w, gy, gx)) or gy > h or gx > w:
        raise ValueError("positive nonempty grid dimensions required")
    if not (0 <= cy < gy and 0 <= cx < gx):
        raise ValueError("cell outside grid")
    y = np.arange(h) * gy // h
    x = np.arange(w) * gx // w
    return (y[:, None] == cy) & (x[None, :] == cx)


def native_support(model_mask, native_shape):
    """Existing fixed prepared-image half-pixel nearest-cell inverse raster."""
    model_mask = np.asarray(model_mask)
    if model_mask.ndim != 2 or model_mask.dtype != np.bool_:
        raise ValueError("model support must be 2D bool")
    if any(type(v) is not int or v <= 0 for v in native_shape):
        raise ValueError("native shape required")
    y = np.floor((np.arange(native_shape[0]) + .5) * model_mask.shape[0] / native_shape[0]).astype(int)
    x = np.floor((np.arange(native_shape[1]) + .5) * model_mask.shape[1] / native_shape[1]).astype(int)
    return model_mask[np.ix_(y, x)]


def verify_full_base_support(image_shape, base_grid, retained_cells, saved_model, saved_native,
                             native_shape, *, sampling):
    """Verify union of entire retained base patches; never intersect vote pixels."""
    if sampling != "NEAREST_FLOOR_GRID;HALF_PIXEL_NATIVE_CELL":
        raise ValueError("explicit supported sampling convention required")
    cells = [tuple(cell) for cell in retained_cells]
    if len(set(cells)) != len(cells):
        raise ValueError("duplicate retained base cell; preserve stage provenance separately")
    expected = np.zeros(image_shape, dtype=bool)
    for cell in cells:
        expected |= patch_support(image_shape, base_grid, cell)
    model, native = np.asarray(saved_model), np.asarray(saved_native)
    if model.dtype != np.bool_ or native.dtype != np.bool_:
        raise ValueError("saved supports must be boolean")
    mapped = native_support(expected, native_shape)
    if not np.array_equal(model, expected) or not np.array_equal(native, mapped):
        raise ValueError("entire-base-patch or native support mismatch")
    return {"status": "PASS", "model_pixels": int(expected.sum()), "native_pixels": int(mapped.sum()),
            "verification": "SUPPORT_ONLY_NOT_OPTIMIZATION_OR_VOTE_FIDELITY"}
