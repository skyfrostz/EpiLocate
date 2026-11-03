"""Independent analytic coordinates; no production imports or image access."""
import math


def native_to_model(y, x, rows, columns):
    return ((y + .5) * 224 / rows - .5,
            (x + .5) * 224 / columns - .5)


def model_to_native(y, x, rows, columns):
    return ((y + .5) * rows / 224 - .5,
            (x + .5) * columns / 224 - .5)


def expected(geometry):
    """Prepare landmarks from saved metadata, not a new geometry QA verdict."""
    if (geometry['crop'], geometry['pad'], geometry['resize_convention']) != (
            'NONE', 'NONE', 'half_pixel_align_corners_false'):
        raise ValueError('UNSUPPORTED_SAVED_TRANSFORM')
    if geometry['model_shape_yx'] != [224, 224]:
        raise ValueError('MODEL_SIZE_MISMATCH')
    rows, columns = geometry['native_shape_rc']
    z = geometry['native_slice_index_zero_based']
    affine = geometry['native_affine_lps']
    if rows <= 0 or columns <= 0 or not all(
            math.isfinite(v) for row in affine for v in row):
        raise ValueError('INVALID_SAVED_METADATA')
    points = [(0, 0), (0, 223), (223, 0), (223, 223),
              (111.5, 111.5), (70.25, 119.75)]
    result = []
    for my, mx in points:
        y, x = model_to_native(my, mx, rows, columns)
        lps = [sum(a*b for a, b in zip(row, [z, y, x, 1]))
               for row in affine[:3]]
        result.append({'model_yx': [my, mx], 'native_yx': [y, x],
                       'native_zyx': [z, y, x], 'lps_mm': lps,
                       'viewer_image_edge_xy': [x + .5, y + .5]})
    return {'status': 'EXPECTED_COORDINATES_ONLY_NOT_VIEWER_PASS',
            'landmarks': result,
            'native_edges_yx': [[-.5, -.5], [rows-.5, columns-.5]],
            'model_edges_yx': [[-.5, -.5], [223.5, 223.5]],
            'viewer_screen_transform': 'NOT_RECORDED_INT_REQUIRED',
            'overlay_scope': 'ACTUAL_HISTORICAL_OCCLUSION_SCALE_64_ONLY',
            'full_series_and_3d': 'NOT_EVALUATED'}
