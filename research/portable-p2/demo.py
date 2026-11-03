"""Run the public P2 scheduler with deterministic, generated responses."""
from types import SimpleNamespace
import json

from p2.p2_routing import ARMS, run


class GeneratedProvider:
    """Count generated scores only. No data, model or network is used."""

    target_class = 1
    engine = SimpleNamespace(source="GENERATED")

    def __init__(self, score_fn=None):
        self.score_fn = score_fn if score_fn is not None else self.generated_score
        self.counts = {"baseline": 0, "noop": 0, "masked": 0}
        self.meter = self

    @staticmethod
    def generated_score(scale, index):
        return ((scale * 17 + index * 29) % 97) / 100

    def baseline(self):
        self.counts["baseline"] += 1
        return 1.0

    def noop(self):
        self.counts["noop"] += 1
        return 1.0

    def evaluate(self, scale, indices):
        self.counts["masked"] += len(indices)
        return [self.score_fn(scale, i) for i in indices]

    def receipt(self):
        return dict(self.counts)


if __name__ == "__main__":
    for arm in ARMS:
        result = run(GeneratedProvider(), arm)
        print(json.dumps({"arm": arm, "source": result["source"], "status": result["status"],
                          "counts": result["provider"],
                          "positions_per_level": [len(level["queries"]) for level in result["levels"]]}))
