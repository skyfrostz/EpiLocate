"""Scientific selection boundaries, uncertainty handling and label blindness."""
import unittest

from scripts.analyze_fair_series_rules import hard_decision, rank_candidates, rule_pool


def series(uid="s1", **changes):
    row = dict(
        series_uid=uid, hard_status="eligible", modalities=["CT"], image_types=["ORIGINAL", "PRIMARY", "AXIAL"],
        descriptions=["CHEST"], kernels=["B"], orientation_missing=0, non_axial_slices=0,
        unique_positions=100, position_missing=0, duplicate_positions=0, all_original_primary=True,
        variable_orientation=False, invalid_thickness=0, invalid_spacing=0, variable_resolution=False,
        multiframe=0, dimensions_invalid_or_variable=False, photometric=["MONOCHROME2"], invalid_rescale=0,
        coverage_mm=300., thickness_max=3., spacing_max=.7,
    )
    return {**row, **changes}


class FairRuleTests(unittest.TestCase):
    def test_vendor_b_is_not_bone_and_explicit_bone_is_excluded(self):
        self.assertEqual(hard_decision(series())[0], "eligible")
        self.assertIn("explicit_bone_only", hard_decision(series(kernels=["BONE"]))[1])
        self.assertIn("explicit_bone_only", hard_decision(series(descriptions=["0.625mm bone alg"]))[1])

    def test_reformatted_axial_still_excluded_and_secondary_is_review(self):
        self.assertIn("explicit_sagittal_coronal_reformatted", hard_decision(series(image_types=["DERIVED", "REFORMATTED"]))[1])
        self.assertEqual(hard_decision(series(all_original_primary=False))[0], "review")
        self.assertEqual(hard_decision(series(descriptions=["2.5mm IODINE(WATER)"]))[0], "review")

    def test_smart_prep_description_does_not_exclude_full_spatial_stack(self):
        self.assertEqual(hard_decision(series(descriptions=["PE Smart Prep Left Atrium"]))[0], "eligible")
        result = hard_decision(series(descriptions=["Smart Prep Series"], unique_positions=1, duplicate_positions=9))
        self.assertIn("non_diagnostic_monitoring", result[1])

    def test_coverage_not_slice_count_and_95_percent_boundary(self):
        thick = series("thick", coverage_mm=300, thickness_max=3, slice_count=100)
        thin = series("thin", coverage_mm=285, thickness_max=1, slice_count=286)
        cropped = series("cropped", coverage_mm=284, thickness_max=.5, slice_count=600)
        self.assertEqual(rank_candidates([thick, thin, cropped], "A")[0][0]["series_uid"], "thick")
        self.assertEqual(rank_candidates([thick, thin, cropped], "B")[0][0]["series_uid"], "thin")

    def test_label_and_uid_cannot_break_tie(self):
        a = series("999", collection="MIDRC-RICORD-1A", label=1)
        b = series("001", collection="MIDRC-RICORD-1B", label=0)
        for rule in ("A", "B", "C"):
            self.assertEqual(len(rank_candidates([a, b], rule)[0]), 2)
            self.assertEqual(len(rank_candidates([b, a], rule)[0]), 2)

    def test_C_inclusive_bounds_no_standard_or_125_requirement(self):
        candidates = [series("boundary", thickness_max=3, spacing_max=1),
                      series("thick", thickness_max=3.01), series("coarse", spacing_max=1.01)]
        self.assertEqual([r["series_uid"] for r in rule_pool(candidates, "C")], ["boundary"])
        self.assertEqual(len(rule_pool(candidates, "A")), 3)


if __name__ == "__main__":
    unittest.main()
