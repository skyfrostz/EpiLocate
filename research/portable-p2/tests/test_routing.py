import unittest

from demo import GeneratedProvider
from p2.p2_routing import ARMS, run


class GeneratedRoutingTests(unittest.TestCase):
    def test_same_budget_distinct_routes(self):
        traces = {}
        for arm, limit in ARMS.items():
            result = run(GeneratedProvider(), arm)
            self.assertEqual(result["status"], "FINE_RESPONSE_16")
            self.assertEqual(result["provider"], {"baseline": 1, "noop": 1, "masked": 100})
            coarse, middle, fine = result["levels"]
            self.assertEqual([len(x["queries"]) for x in (coarse, middle, fine)], [36, 32, 32])
            for level in (middle, fine):
                self.assertEqual(len(set(level["queries"])), len(level["queries"]))
                route = level["route_from_parent"]
                self.assertLessEqual(len(route["parents"]), limit)
                self.assertEqual(len(route["exploration"]), 8)
                self.assertTrue(set(route["exploitation"]).isdisjoint(route["exploration"]))
            traces[arm] = fine["queries"]
        self.assertNotEqual(traces["single_parent_v1"], traces["multi_parent_v1"])

    def test_zero_and_threshold_responses_stop(self):
        for score in (0, 1e-6):
            result = run(GeneratedProvider(lambda scale, i: score), "multi_parent_v1")
            self.assertEqual(result["status"], "NO_POSITIVE_RESPONSE_64")
            self.assertEqual(result["provider"]["masked"], 36)

    def test_fallback_records_unassessed_fine_grid(self):
        result = run(GeneratedProvider(lambda scale, i: 1.0 if scale == 64 else 0.0), "single_parent_v1")
        self.assertEqual(result["status"], "FALLBACK_64")
        self.assertEqual([x["scale"] for x in result["levels"]], [64, 32])

    def test_invalid_response(self):
        with self.assertRaisesRegex(ValueError, "INVALID_RESPONSE_VECTOR"):
            run(GeneratedProvider(lambda scale, i: float("nan")), "single_parent_v1")
