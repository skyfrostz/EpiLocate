"""P2 V1 candidate/comparator. New routing, not the frozen D5a policy."""
from __future__ import annotations
import hashlib
import math
from .stage_c_replay import GRIDS, CHILD_LOOKUP, EPSILON

SEED = 20261025
LEVEL_CAP = 32
EXPLORATION = 8
ARMS = {'single_parent_v1': 1, 'multi_parent_v1': 4}


def rank(scores):
    return sorted((i for i, value in scores.items() if value > EPSILON),
                  key=lambda i: (-scores[i], i))


def parents(scale, scores, count):
    selected = []
    for i in rank(scores):
        x, y = GRIDS[scale][i]
        if all(abs(x-GRIDS[scale][j][0]) >= scale or abs(y-GRIDS[scale][j][1]) >= scale for j in selected):
            selected.append(i)
        if len(selected) == count: break
    return selected


def plan(parent_scale, child_scale, scores, arm):
    chosen = parents(parent_scale, scores, ARMS[arm])
    pools = {p: CHILD_LOOKUP[(parent_scale, child_scale)][p] for p in chosen}
    union = set().union(*(set(v) for v in pools.values())) if pools else set()
    routed = []
    # Round-robin allocates exploitation positions across every retained parent.
    max_len = max((len(v) for v in pools.values()), default=0)
    for offset in range(max_len):
        for p in chosen:
            if offset < len(pools[p]) and pools[p][offset] not in routed:
                routed.append(pools[p][offset])
                if len(routed) == LEVEL_CAP-EXPLORATION: break
        if len(routed) == LEVEL_CAP-EXPLORATION: break
    outside = set(range(len(GRIDS[child_scale]))) - union
    # Seeded SHA ordering is stable across Python/runtime versions.
    order = sorted(outside, key=lambda i: (hashlib.sha256(f'{SEED}:{child_scale}:{i}'.encode()).digest(), i))
    explore = order[:EXPLORATION] if chosen else []
    return {'parents': chosen, 'exploitation': routed, 'exploration': explore,
            'unspent': LEVEL_CAP-len(routed)-len(explore),
            'parent_links': {str(i): [p for p in chosen if i in pools[p]] for i in routed}}


def run(provider, arm, *, technical_noop=True):
    if arm not in ARMS: raise ValueError('UNKNOWN_ARM')
    baseline = provider.baseline()
    if technical_noop: provider.noop()
    records = []
    queries = list(range(36))
    last_positive = None
    route = None
    status = 'NO_POSITIVE_RESPONSE_64'
    for scale, next_scale in ((64, 32), (32, 16), (16, None)):
        values = provider.evaluate(scale, queries)
        if len(values) != len(queries) or not all(math.isfinite(v) and v >= 0 for v in values):
            raise ValueError('INVALID_RESPONSE_VECTOR')
        scores = dict(zip(queries, values))
        positive = rank(scores)
        records.append({'scale': scale, 'queries': queries, 'responses': values,
                        'positive_indices': positive, 'route_from_parent': route,
                        'unqueried_status': 'NOT_EVALUATED'})
        if not positive:
            status = 'NO_POSITIVE_RESPONSE_64' if last_positive is None else f'FALLBACK_{last_positive}'
            break
        last_positive = scale
        if next_scale is None:
            status = 'FINE_RESPONSE_16'
            break
        route = plan(scale, next_scale, scores, arm)
        queries = route['exploitation'] + route['exploration']
        if not queries:
            status = 'GEOMETRY_NO_CHILDREN'
            break
    return {'schema': 'P2_ROUTING_V1', 'arm': arm, 'status': status,
            'baseline_score': baseline, 'target_class': provider.target_class,
            'seed': SEED, 'levels': records, 'max_masked_positions': 100,
            'response_semantics': 'max(q0-qg,0); raw signed delta in provider ledger',
            'source': provider.engine.source, 'provider': provider.meter.receipt(),
            'scheduler': {'loads_model': False, 'reads_gt': False},
            'whole_task': {'gt_evaluation': 'NOT_RUN', 'medical_improvement': 'NOT_EVALUATED'}}
