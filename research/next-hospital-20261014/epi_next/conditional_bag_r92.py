"""R92 conditional K=8 BAG function. No loaders, authority or legacy mutation."""
from __future__ import annotations
import time
import math
import torch
from torch import nn
from torch.nn import functional as F


class Limit(RuntimeError):
    pass


class Meter:
    """Local accounting in addition to an existing admitted parent's guard.

    Reservations are not actual returned calls. One batch is one encoder F;
    batch sample count is recorded separately. Starts before caller loading.
    """
    def __init__(self, forward, backward, updates, samples, seconds, check=lambda: None, clock=time.monotonic):
        caps = (forward, backward, updates, samples)
        if any(type(n) is not int or n < 0 for n in caps) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('FINITE_NONNEGATIVE_BUDGET_REQUIRED')
        self.caps = dict(zip(('forward', 'backward', 'updates', 'samples'), caps))
        self.reserved = dict.fromkeys(self.caps, 0)
        self.returned = dict.fromkeys(self.caps, 0)
        self.batches = []
        self.clock, self.started, self.seconds, self.check = clock, clock(), seconds, check

    def guard(self):
        self.check()
        if self.clock() - self.started >= self.seconds:
            raise Limit('TIMEOUT')

    def call(self, kind, fn, samples=0):
        self.guard()
        if kind not in ('forward', 'backward', 'updates') or type(samples) is not int or samples < 0 or (kind != 'forward' and samples):
            raise ValueError('COUNT_DOMAIN')
        increments = {kind: 1}
        if kind == 'forward': increments['samples'] = samples
        if any(self.reserved[k] + n > self.caps[k] for k, n in increments.items()):
            raise Limit('CALL_OR_SAMPLE_BUDGET')
        for k, n in increments.items(): self.reserved[k] += n
        result = fn()
        for k, n in increments.items(): self.returned[k] += n
        if kind == 'forward': self.batches.append(samples)
        self.guard()
        return result

    def report(self):
        return dict(reserved=self.reserved.copy(), returned=self.returned.copy(),
                    encoder_batch_samples=list(self.batches), elapsed_seconds=self.clock()-self.started)


def finite(t, shape=None):
    if not isinstance(t, torch.Tensor) or t.device.type != 'cpu' or not t.is_floating_point() or not torch.isfinite(t).all() or (shape is not None and tuple(t.shape) != tuple(shape)):
        raise ValueError('FINITE_CPU_TENSOR_REQUIRED')
    return t


def bag_losses(baseline, logits, k=8):
    if k != 8: raise ValueError('K8_ONLY')
    raw = (finite(logits, (1, 2)) - finite(baseline, (1, 2))).square().sum()
    return {'RAW_BAG_LS_R92_V1': raw, 'K2_COMPONENT_LS_R92_V1': raw * k*k}


class ConditionalBag(nn.Module):
    """Encoder maps declared scalar inputs to actual GAP, retaining input grads.

    Cache rows are current residual features, not deleted vectors. On advance,
    snapshot updated rows; fixed original target is retained across stages.
    Caller owns exact preprocessing/checkpoint/cache/member identity validation.
    """
    def __init__(self, encoder, cached_gap, mean, scale, weight, bias, members, meter,
                 *, target_policy='ORIGINAL_ARGMAX_FIXED', declared_class=None):
        super().__init__()
        if len(members) != 8 or len(set(members)) != 8 or any(not isinstance(m, str) or not m for m in members):
            raise ValueError('EIGHT_UNIQUE_FIXED_MEMBERS_REQUIRED')
        finite(cached_gap)
        if cached_gap.ndim != 2 or cached_gap.shape[0] != 8: raise ValueError('K8_GAP_REQUIRED')
        d = cached_gap.shape[1]
        for key, tensor, shape in (('gap', cached_gap, (8,d)), ('mean',mean,(d,)),
                ('scale',scale,(d,)), ('weight',weight,(2,d)), ('bias',bias,(2,))):
            self.register_buffer(key, finite(tensor, shape).detach().clone().double())
        if not bool((self.scale > 0).all()): raise ValueError('POSITIVE_SCALE_REQUIRED')
        self.encoder, self.members, self.meter = encoder, tuple(members), meter
        self.aggregations = 0
        self.stage = 0
        self.eval().requires_grad_(False)
        original = self.aggregate(self.gap).detach()
        self.register_buffer('original_logits', original)
        self.register_buffer('current_logits', original.clone())
        predicted = int(original.argmax(1))
        if target_policy not in ('ORIGINAL_ARGMAX_FIXED','DECLARED_FIXED'):
            raise ValueError('FIXED_TARGET_POLICY_REQUIRED')
        resolved = predicted if target_policy == 'ORIGINAL_ARGMAX_FIXED' else declared_class
        if type(resolved) is not int or resolved not in (0,1) or (declared_class is not None and declared_class != resolved):
            raise ValueError('DECLARED_RESOLVED_TARGET_MISMATCH')
        self.target = resolved
        self.target_policy = target_policy

    def train(self, mode=True):
        super().train(False)
        return self

    def aggregate(self, gap):
        self.aggregations += 1
        return F.linear((gap.double().mean(0,keepdim=True)-self.mean)/self.scale,self.weight,self.bias)

    def features(self, images):
        finite(images)
        if images.ndim != 4 or images.shape[1] != 1 or images.dtype != torch.float32:
            raise ValueError('SCALAR_N1HW_FP32_REQUIRED')
        self.encoder.eval().requires_grad_(False)
        features = self.meter.call('forward', lambda: self.encoder(images), samples=len(images))
        return finite(features, (len(images),self.gap.shape[1])).double()

    def replacement_features(self, replacements):
        if not isinstance(replacements, dict) or not replacements or any(k not in self.members for k in replacements):
            raise ValueError('ONLY_FIXED_BAG_MEMBERS_NO_SUBSTITUTION')
        keys = [m for m in self.members if m in replacements]
        for m in keys: finite(replacements[m])
        if any(replacements[m].ndim != 4 or replacements[m].shape[0] != 1 for m in keys):
            raise ValueError('ONE_INPUT_PER_CHANGED_MEMBER')
        images = torch.cat([replacements[m] for m in keys])
        encoded = self.features(images)
        lookup = dict(zip(keys, encoded.unbind(0)))
        return torch.stack([lookup[m] if m in lookup else self.gap[i] for i,m in enumerate(self.members)])

    def forward(self, replacements):
        return self.aggregate(self.replacement_features(replacements))

    def advance(self, replacements):
        """Explicit new residual baseline; encoding charged once, no stale base."""
        updated = self.replacement_features(replacements)
        logits = self.aggregate(updated)
        with torch.no_grad():
            self.gap.copy_(updated)
            self.current_logits.copy_(logits)
        self.stage += 1
        return dict(stage=self.stage, target=self.target, baseline_logits=logits.detach().tolist(),
                    baseline_kind='CURRENT_RESIDUAL_BAG', members=list(self.members))

    def member(self, member):
        if member not in self.members: raise ValueError('NON_MEMBER')
        parent = self
        class Member(nn.Module):
            def forward(self, image): return parent({member:image})
        return Member()

    def metadata(self):
        return dict(schema='R92_CONDITIONAL_BAG_V1', K=8, prediction_scope='BAG',
            class_labels=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE'],
            target_policy=self.target_policy, fixed_target=self.target, stage=self.stage,
            original_logits=self.original_logits.tolist(), current_baseline_logits=self.current_logits.tolist(),
            bag_aggregations=self.aggregations, source_label=None,
            losses=['RAW_BAG_LS_R92_V1','K2_COMPONENT_LS_R92_V1'], cpf='NOT_CALIBRATED_NOT_APPLIED',
            meter=self.meter.report())
