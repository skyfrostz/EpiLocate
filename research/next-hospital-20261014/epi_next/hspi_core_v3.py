"""Paper-based HSPI shared core. New implementation; old E2 is untouched.

X is the declared image domain; f (the supplied module) includes its declared
preprocessing. CT normalization/fill policies must be bound in adapter_policy.
No patient/checkpoint loading, execution authorization or clinical claims here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

SCHEMA = 'HSPI_TRACE_V3'


class BudgetStopped(RuntimeError):
    """Expected external meter/guard stop, preserving partial observations."""


@dataclass(frozen=True)
class HSPIConfig:
    mode: str = 'E2-REF'
    image_size: tuple[int, int] = (224, 224)
    grids: tuple[int, ...] = tuple(range(7, 17))
    stages: int = 15
    steps: int = 10000
    zeta: float = .5
    lr: float = .01
    lam: float = 1.
    alpha: float = .005
    beta: float = .08
    reference_grid: int = 7
    epsilon: int = 8
    adam_betas: tuple[float, float] = (.9, .999)
    adam_eps: float = 1e-8
    align_corners: bool = False
    adapter_policy: str = 'f_includes_preprocessing; X_declared_image_domain; zero_multiply'
    masking_policy: str = 'multiply_all'
    tie_policy: str = 'earliest_feasible_epoch_then_first_flat_argmax'

    def validate(self):
        if self.mode not in ('E2-REF', 'E2-CT'):
            raise ValueError('unknown method mode')
        if self.masking_policy not in ('multiply_all', 'preserve_exterior'):
            raise ValueError('unknown masking policy')
        if self.mode == 'E2-REF' and self.masking_policy != 'multiply_all':
            raise ValueError('CT support policy requires E2-CT')
        if (not self.grids or len(set(self.grids)) != len(self.grids)
                or any(type(g) is not int or g < 2 for g in self.grids)):
            raise ValueError('distinct grids >=2 required')
        if (len(self.image_size) != 2 or any(type(x) is not int or x < 1 for x in self.image_size)
                or any(g > min(self.image_size) for g in self.grids)):
            raise ValueError('grid cannot exceed image dimensions')
        if type(self.stages) is not int or type(self.steps) is not int or self.stages < 1 or self.steps < 1:
            raise ValueError('positive integer stages/steps required')
        if self.reference_grid not in self.grids:
            raise ValueError('reference grid absent')
        if type(self.epsilon) is not int or not 0 <= self.epsilon <= len(self.grids)-1:
            raise ValueError('epsilon exceeds other-scale count')
        vals = (self.zeta, self.lr, self.lam, self.alpha, self.beta, self.adam_eps, *self.adam_betas)
        if not all(math.isfinite(v) for v in vals) or not 0 <= self.zeta <= 1:
            raise ValueError('invalid numeric parameter')
        if self.lr <= 0 or self.lam < 0 or self.alpha <= 0 or not 0 < self.beta <= 1 or self.adam_eps <= 0:
            raise ValueError('invalid loss/optimizer parameter')
        if not all(0 <= b < 1 for b in self.adam_betas):
            raise ValueError('invalid Adam betas')
        if self.tie_policy != 'earliest_feasible_epoch_then_first_flat_argmax' or not self.adapter_policy:
            raise ValueError('unsupported tie policy or undeclared f boundary')
        return self

    def sha256(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def worst_cost(self):
        branches = len(self.grids)*self.stages
        return {'baseline_forward': branches, 'mask_forward': branches*self.steps,
                'forward': branches*(self.steps+1), 'backward': branches*self.steps,
                'extra_autograd': 0, 'optimizer_steps': branches*self.steps}


@dataclass
class Budget:
    """Cooperative budget for this invocation; external process guard still needed."""
    max_forward: int | None = None
    max_backward: int | None = None
    seconds: float | None = None
    clock: Callable = time.monotonic

    def __post_init__(self):
        for x in (self.max_forward, self.max_backward):
            if x is not None and (type(x) is not int or x < 0):
                raise ValueError('nonnegative integer call cap required')
        if self.seconds is not None and (not math.isfinite(self.seconds) or self.seconds < 0):
            raise ValueError('invalid deadline')
        self.started = self.clock()
        self.forward = self.backward = self.optimizer_steps = 0
        self.reason = None

    def permits(self, forwards=0, backwards=0):
        if self.seconds is not None and self.clock()-self.started >= self.seconds:
            self.reason = 'TIMEOUT'
        elif self.max_forward is not None and self.forward+forwards > self.max_forward:
            self.reason = 'FORWARD_BUDGET'
        elif self.max_backward is not None and self.backward+backwards > self.max_backward:
            self.reason = 'BACKWARD_BUDGET'
        return self.reason is None

    def counts(self):
        return {'forward': self.forward, 'backward': self.backward,
                'extra_autograd': 0, 'optimizer_steps': self.optimizer_steps,
                'elapsed_seconds': self.clock()-self.started, 'stop_reason': self.reason}

    def forward_call(self, function):
        self.forward += 1
        return function()

    def backward_call(self, function):
        self.backward += 1
        return function()

    def did_optimizer_step(self):
        self.optimizer_steps += 1


@contextmanager
def frozen_classifier(model):
    modes = [(m, m.training) for m in model.modules()]
    flags = [(p, p.requires_grad) for p in model.parameters()]
    try:
        model.eval()
        for p, _ in flags:
            p.requires_grad_(False)
        yield
    finally:
        for p, flag in flags:
            p.requires_grad_(flag)
        # train() recurses; assign each saved flag, preserving mixed module modes.
        for m, flag in modes:
            m.training = flag


def upsample(mask, size, mode, align_corners=False):
    args = {'size': size, 'mode': mode}
    if mode == 'bilinear':
        args.update(align_corners=align_corners, antialias=False)
    return F.interpolate(mask, **args)


def spi_inputs(x0, omega, mask, config, valid=None):
    residual = upsample(omega, config.image_size, 'nearest')*x0
    soft = upsample(omega*mask, config.image_size, 'bilinear', config.align_corners)
    if config.masking_policy == 'preserve_exterior':
        hard = upsample(omega, config.image_size, 'nearest')
        residual = torch.where(valid[None, None], hard, torch.ones_like(hard))*x0
        soft = torch.where(valid[None, None], soft, torch.ones_like(soft))
    return residual, soft*residual


def losses(baseline, logits, mask, config):
    ls = (baseline-logits).square().sum()
    lm = mask.abs().mean()
    return ls, lm, ls+config.lam*lm


def peak_gap(mask):
    values = torch.topk(mask.detach().flatten(), 2).values
    return float(values[0]-values[1])


def cpf_select(rows, alpha, beta):
    """Oracle/offline selector. No positive-gap gate; strict constraints."""
    feasible = [r for r in rows if r['ls'] < alpha and r['lm'] < beta]
    return max(feasible, key=lambda r: (r['gap'], -r['epoch'])) if feasible else None


def cell_patch(grid, cell, size, device='cpu'):
    one = torch.zeros((1, 1, grid, grid), device=device)
    one.flatten()[cell] = 1
    return upsample(one, size, 'nearest')[0, 0].bool()


def psmi(stages, config, complete=True):
    """Any-stage intersection per other scale; retain the WHOLE reference patch."""
    config.validate()
    refs = [s for s in stages if s['grid'] == config.reference_grid and s.get('patch') is not None]
    votes = []
    kept = []
    for q in refs:
        supporters = {}
        for grid in config.grids:
            if grid == config.reference_grid:
                continue
            supporters[str(grid)] = [s['stage'] for s in stages if s['grid'] == grid
                                     and s.get('patch') is not None
                                     and bool(torch.any(q['patch'] & s['patch']))]
        count = sum(bool(v) for v in supporters.values())
        retained = len(config.grids) == 1 or count >= config.epsilon
        votes.append({'reference_stage': q['stage'], 'supporting_stages': supporters,
                      'votes': count, 'epsilon': config.epsilon, 'retained': retained})
        if retained:
            kept.append(q['patch'].clone())
    status = ('NOT_APPLICABLE' if len(config.grids) == 1 else
              'SUPPORTED' if kept else 'NO_MULTISCALE_SUPPORT')
    summed = torch.zeros(config.image_size, dtype=torch.int64)
    for patch in kept:
        summed += patch.cpu().to(torch.int64)
    return {'status': status, 'complete': complete, 'votes': votes, 'patches': kept,
            'sum_map': summed}


def rng_snapshot():
    return {'torch': torch.get_rng_state().clone(), 'numpy': copy.deepcopy(np.random.get_state()),
            'python': random.getstate()}


def rng_restore(state):
    torch.set_rng_state(state['torch'])
    np.random.set_state(state['numpy'])
    random.setstate(state['python'])


def tensor_hash(t):
    a = t.detach().contiguous().cpu()
    return hashlib.sha256(str((tuple(a.shape), str(a.dtype))).encode()+a.numpy().tobytes()).hexdigest()


def source_sha():
    from pathlib import Path
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _binding(x0, omega, config, identity):
    if not identity:
        raise ValueError('explicit model/input/preprocessing identity required')
    return {'config_sha256': config.sha256(), 'source_sha256': source_sha(), 'identity': identity,
            'x_sha256': tensor_hash(x0), 'omega_sha256': tensor_hash(omega),
            'device': str(x0.device), 'dtype': str(x0.dtype)}


def _logits(model, x):
    y = model(x)
    if not torch.is_tensor(y) or y.ndim != 2 or y.shape[0] != 1 or y.shape[1] < 2:
        raise ValueError('classifier must return single-case full logits [1,C>=2]')
    if not bool(torch.isfinite(y).all()):
        raise FloatingPointError('nonfinite logits')
    return y


def optimize_stage(model: nn.Module, x0, omega, config, *, grid, stage, identity,
                   budget=None, resume=None, trace_sink=None, checkpoint_sink=None,
                   record_history=True, include_masks=False, valid=None,
                   checkpoint_every=100, checkpoint_steps=()):
    """Exactly config.steps pre-update observations + projected Adam updates.

    A checkpoint is after the update; its best candidate refers to an earlier
    pre-update observation. A resumed stage uses its saved residual baseline.
    Each iteration reserves both forward/backward before starting. A call itself
    may overrun a cooperative deadline; counts reflect entered calls on errors.
    """
    config.validate()
    if x0.device.type != 'cpu':
        raise ValueError('v3 exact RNG resume supports CPU only; MPS/CUDA not implemented')
    if type(checkpoint_every) is not int or checkpoint_every < 1:
        raise ValueError('positive checkpoint interval required')
    if any(type(n) is not int or not 1 <= n <= config.steps for n in checkpoint_steps):
        raise ValueError('invalid checkpoint milestone')
    if grid not in config.grids or not 1 <= stage <= config.stages:
        raise ValueError('invalid branch')
    if tuple(x0.shape[-2:]) != config.image_size or x0.ndim != 4 or x0.shape[0] != 1:
        raise ValueError('single BCHW image with configured size required')
    if x0.requires_grad or not x0.is_floating_point() or not bool(torch.isfinite(x0).all()):
        raise ValueError('fixed finite floating input required')
    if tuple(omega.shape) != (1, 1, grid, grid) or not bool(((omega == 0)|(omega == 1)).all()):
        raise ValueError('binary full coarse Omega required')
    if config.masking_policy == 'preserve_exterior':
        if (valid is None or valid.dtype != torch.bool or tuple(valid.shape) != config.image_size
                or valid.device != x0.device or not bool(valid.any())):
            raise ValueError('CT support policy requires bound valid support')
    elif valid is not None:
        raise ValueError('REF full image policy does not consume support')
    budget = budget if budget is not None else Budget()
    binding = _binding(x0, omega, config, identity)
    binding['valid_sha256'] = None if valid is None else tensor_hash(valid)
    mask = nn.Parameter(torch.full_like(omega, config.zeta))
    optimizer = torch.optim.Adam([mask], lr=config.lr, betas=config.adam_betas, eps=config.adam_eps)
    history, best, feasible_count, completed, baseline = [], None, 0, 0, None
    pending, replay_pending = None, None
    if resume is not None:
        if (resume.get('schema') != SCHEMA or resume.get('binding') != binding or not resume.get('resume_safe', True)
                or resume.get('grid') != grid or resume.get('stage') != stage
                or resume.get('record_history') != record_history or resume.get('include_masks') != include_masks):
            raise ValueError('resume identity/config/source/trace-policy mismatch')
        mask.data.copy_(resume['mask'].to(mask))
        optimizer.load_state_dict(copy.deepcopy(resume['optimizer']))
        history, best = copy.deepcopy(resume['history']), copy.deepcopy(resume['best'])
        feasible_count, completed = resume['feasible_count'], resume['completed_steps']
        baseline = resume['baseline'].to(x0) if resume['baseline'] is not None else None
        replay_pending = copy.deepcopy(resume.get('pending_observation'))
        pending = replay_pending
        rng_restore(resume['rng'])
    def checkpoint():
        return {'schema': SCHEMA, 'binding': binding, 'grid': grid, 'stage': stage,
                'mask': mask.detach().clone(), 'optimizer': copy.deepcopy(optimizer.state_dict()),
                'baseline': None if baseline is None else baseline.detach().clone(),
                'rng': rng_snapshot(), 'history': copy.deepcopy(history), 'best': copy.deepcopy(best),
                'feasible_count': feasible_count, 'completed_steps': completed,
                'record_history': record_history, 'include_masks': include_masks, 'resume_safe': True,
                'pending_observation': copy.deepcopy(pending)}
    error = None
    residual, _ = spi_inputs(x0, omega, mask, config, valid)
    step_entered = False
    observed_replays = 0
    with frozen_classifier(model), torch.enable_grad():
        try:
            if baseline is None and budget.permits(forwards=1):
                with torch.no_grad():
                    baseline = budget.forward_call(lambda: _logits(model, residual)).detach()
            if baseline is not None:
                for epoch in range(completed+1, config.steps+1):
                    if not budget.permits(forwards=1, backwards=1):
                        break
                    step_entered = False
                    _, masked = spi_inputs(x0, omega, mask, config, valid)
                    logits = budget.forward_call(lambda: _logits(model, masked))
                    ls, lm, loss = losses(baseline, logits, mask, config)
                    if not bool(torch.isfinite(loss)):
                        raise FloatingPointError('nonfinite objective')
                    gap = peak_gap(mask)
                    row = {'grid': grid, 'stage': stage, 'epoch': epoch, 'ls': float(ls.detach()),
                           'lm': float(lm.detach()), 'loss': float(loss.detach()), 'gap': gap,
                           'logits': logits.detach().cpu().tolist(),
                           'feasible': bool(ls.detach() < config.alpha and lm.detach() < config.beta)}
                    if include_masks:
                        row['mask'] = mask.detach().cpu().tolist()
                    pending = row
                    if replay_pending is not None:
                        if row != replay_pending:
                            raise ValueError('pending observation replay diverged')
                        observed_replays += 1
                    elif row['feasible']:
                        feasible_count += 1
                        if best is None or gap > best['gap']:
                            best = {**row, 'mask': mask.detach().clone()}
                    if trace_sink is not None:
                        trace_sink(copy.deepcopy(row))
                    if record_history and replay_pending is None:
                        history.append(row)
                    replay_pending = None
                    # Forward may cross a deadline. Preserve its observation,
                    # do not submit new backward work after the stop condition.
                    if not budget.permits(backwards=1):
                        break
                    optimizer.zero_grad(set_to_none=True)
                    budget.backward_call(loss.backward)
                    if mask.grad is None or not bool(torch.isfinite(mask.grad).all()):
                        raise FloatingPointError('missing/nonfinite mask gradient')
                    step_entered = True
                    optimizer.step()
                    with torch.no_grad():
                        mask.clamp_(0, 1)
                    completed = epoch
                    pending = None
                    budget.did_optimizer_step()
                    if checkpoint_sink is not None and (epoch % checkpoint_every == 0
                            or epoch in checkpoint_steps or epoch == config.steps):
                        checkpoint_sink(checkpoint())
        except BudgetStopped as exc:
            budget.reason = str(exc)
        except Exception as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
    cp = checkpoint()
    if error and pending is not None:
        # A pending pre-update observation can be replayed, costing one forward.
        # Mid-optimizer failures may leave Adam/mask inconsistent: fail closed.
        cp['resume_safe'] = not step_entered
    done = completed == config.steps and error is None
    status = ('FAILED' if error else 'PARTIAL_BUDGET' if not done else
              'SELECTED' if best is not None else 'NO_FEASIBLE_MASK')
    cell = int(best['mask'].flatten().argmax()) if best is not None else None
    patch = None if cell is None else cell_patch(grid, cell, config.image_size, x0.device)
    after = omega.clone()
    if cell is not None:
        after.flatten()[cell] = 0
    return {'grid': grid, 'stage': stage, 'status': status, 'error': error,
            'planned_steps': config.steps, 'completed_steps': completed,
            'observed_iterations': completed + (1 if pending is not None else 0),
            'optimizer_updates': completed,
            'observed_forward_replays_this_invocation': observed_replays,
            'baseline_logits': None if baseline is None else baseline.cpu().tolist(),
            'residual_class': None if baseline is None else int(baseline.argmax()),
            'history': history, 'feasible_count': feasible_count, 'best': best,
            'best_is_full_plan': done, 'cell': cell, 'patch': patch,
            'repeated_exclusion': cell is not None and not bool(omega.flatten()[cell]),
            'omega_before': omega.clone(), 'omega_after': after, 'checkpoint': cp}


def run_hspi(model, x0, config, *, identity, budget=None, resume=None,
             trace_sink=None, checkpoint_sink=None, record_history=True, include_masks=False, valid=None,
             checkpoint_every=100, checkpoint_steps=()):
    """Serial scale/stage engine; resume cursor contains completed and active state.

    Empty CPF stops that scale branch; remaining scales still run. Partial/failed
    stops the invocation without treating unrun stages/scales as negative votes.
    Public full-profile planning never executes here without an explicit caller.
    """
    config.validate()
    budget = budget if budget is not None else Budget()
    root_binding = _binding(x0, torch.ones(1), config, identity)
    root_binding['valid_sha256'] = None if valid is None else tensor_hash(valid)
    results, skipped, cursor, active = [], [], (0, 1), None
    if resume is not None:
        if resume.get('binding') != root_binding or resume.get('schema') != SCHEMA:
            raise ValueError('run resume binding mismatch')
        results, skipped = copy.deepcopy(resume['stages']), copy.deepcopy(resume['skipped'])
        cursor, active = tuple(resume['cursor']), resume['active']
    stop = None
    def run_checkpoint(si, sj, current):
        return {'schema': SCHEMA, 'binding': root_binding, 'stages': copy.deepcopy(results),
                'skipped': copy.deepcopy(skipped), 'cursor': (si, sj), 'active': current}
    final_cp = run_checkpoint(*cursor, active)
    for si in range(cursor[0], len(config.grids)):
        grid = config.grids[si]
        omega = torch.ones((1, 1, grid, grid), dtype=x0.dtype, device=x0.device)
        previous = [r for r in results if r['grid'] == grid]
        if previous:
            omega = previous[-1]['omega_after'].clone()
        first = cursor[1] if si == cursor[0] else 1
        for stage in range(first, config.stages+1):
            def emit_cp(cp):
                if checkpoint_sink is not None:
                    checkpoint_sink(run_checkpoint(si, stage, cp))
            result = optimize_stage(model, x0, omega, config, grid=grid, stage=stage,
                                    identity=identity, budget=budget, resume=active,
                                    trace_sink=trace_sink, checkpoint_sink=emit_cp,
                                    record_history=record_history, include_masks=include_masks, valid=valid,
                                    checkpoint_every=checkpoint_every, checkpoint_steps=checkpoint_steps)
            active = None
            if result['status'] in ('PARTIAL_BUDGET', 'FAILED'):
                stop = result['status']
                final_cp = run_checkpoint(si, stage, result['checkpoint'])
                partial = result
                break
            results.append(result)
            omega = result['omega_after']
            if result['status'] == 'NO_FEASIBLE_MASK':
                skipped.extend({'grid': grid, 'stage': j, 'reason': 'PRIOR_NO_FEASIBLE_MASK'}
                               for j in range(stage+1, config.stages+1))
                final_cp = run_checkpoint(si+1, 1, None)
                if checkpoint_sink:
                    checkpoint_sink(final_cp)
                break
            final_cp = run_checkpoint(si, stage+1, None) if stage < config.stages else run_checkpoint(si+1, 1, None)
            if checkpoint_sink:
                checkpoint_sink(final_cp)
        if stop:
            break
    evidence = results + ([partial] if stop else [])
    full_plan = stop is None and not skipped and len(results) == len(config.grids)*config.stages
    support = psmi(evidence, config, complete=full_plan)
    if stop:
        status = stop
    else:
        status = 'COMPLETED' if support['patches'] else 'NO_RELIABLE_RESPONSE'
    return {'schema': SCHEMA, 'mode': config.mode, 'config_sha256': config.sha256(),
            'source_sha256': source_sha(), 'status': status, 'stages': evidence,
            'planned_branches': len(config.grids)*config.stages,
            'full_plan_completed': full_plan, 'termination_policy_completed': stop is None,
            'completed_branches': len(results), 'skipped_branches': skipped,
            'psmi': support, 'cost': budget.counts(), 'checkpoint': final_cp}


def adopt_wave1_checkpoint(checkpoint, prefix, x0, valid, config, *, identity,
                           provenance, expected_baseline):
    """Zero-forward conversion of a verified W1 stage1 optimization prefix.

    Caller must verify the external lock/result/file bytes first. This converter
    requires their explicit hashes, validates same-step telemetry and Adam step,
    and reselects CPF over the full observed prefix under the NEW tie/no-gap-gate
    policy. It never labels W1 as REF or uses a checkpoint to grant execution.
    """
    config.validate()
    if (config.mode != 'E2-CT' or config.masking_policy != 'preserve_exterior'
            or config.grids != (7,) or config.stages != 1 or config.zeta != .5
            or config.lr != .01 or config.align_corners or config.adam_betas != (.9, .999)
            or config.adam_eps != 1e-8 or config.alpha != .005 or config.beta != .08):
        raise ValueError('W1 continuation requires exact W1 optimization policy')
    required = {'checkpoint_sha256', 'source_sha256', 'input_sha256',
                'model_sha256', 'preprocessing_sha256', 'execution_lock_sha256'}
    if set(provenance) != required or any(not isinstance(h, str) or len(h) != 64
                                         or any(c not in '0123456789abcdef' for c in h)
                                         for h in provenance.values()):
        raise ValueError('verified external W1 hashes required')
    old = checkpoint['config']
    n = checkpoint['step']
    if (old['grid'] != [7, 7] or old['weight'] != config.lam or old['learning_rate'] != config.lr
            or not 1 <= n <= old['steps'] <= 1000 or config.steps < n or len(prefix) != n):
        raise ValueError('W1 checkpoint plan/prefix mismatch')
    baseline = checkpoint['baseline_logits']
    if not torch.equal(baseline.cpu(), torch.as_tensor(expected_baseline).reshape_as(baseline).cpu()):
        raise ValueError('external baseline mismatch')
    mask = checkpoint['mask']
    states = checkpoint['optimizer']['state']
    groups = checkpoint['optimizer']['param_groups']
    if (tuple(mask.shape) != (1, 1, 7, 7) or len(states) != 1 or len(groups) != 1
            or len(groups[0]['params']) != 1 or int(next(iter(states.values()))['step']) != n
            or groups[0]['lr'] != config.lr or groups[0]['betas'] != config.adam_betas
            or groups[0]['eps'] != config.adam_eps or groups[0]['weight_decay'] != 0
            or groups[0]['amsgrad']):
        raise ValueError('incompatible/incomplete Adam state')
    history, best, count = [], None, 0
    for index, row in enumerate(prefix):
        if row['epoch'] != index or row['step'] != index+1:
            raise ValueError('W1 zero-based epoch/one-based observation mismatch')
        m = torch.tensor(row['mask_before'], dtype=mask.dtype).reshape_as(mask)
        logits = torch.tensor(row['logits'], dtype=baseline.dtype).reshape_as(baseline)
        ls, lm, loss = losses(baseline, logits, m, config)
        gap = peak_gap(m)
        if (float(ls) != row['similarity'] or float(lm) != row['sparsity']
                or gap != row['peak_gap']):
            raise ValueError('W1 same-step numeric binding mismatch')
        r = {'grid': 7, 'stage': 1, 'epoch': index+1, 'raw_epoch_zero_based': index,
             'ls': float(ls), 'lm': float(lm), 'loss': float(loss), 'gap': gap,
             'logits': logits.tolist(), 'feasible': float(ls) < config.alpha and float(lm) < config.beta}
        history.append(r)
        if r['feasible']:
            count += 1
            if best is None or gap > best['gap']:
                best = {**r, 'mask': m.clone()}
    last = torch.tensor(prefix[-1]['mask_after_projection'], dtype=mask.dtype).reshape_as(mask)
    if not torch.equal(last, mask.cpu()):
        raise ValueError('W1 checkpoint is not matching post-update mask')
    omega = torch.ones_like(mask, device=x0.device)
    binding = _binding(x0, omega, config, identity)
    binding['valid_sha256'] = tensor_hash(valid)
    numpy_rng = checkpoint['numpy_rng']
    rng = {'torch': checkpoint['torch_rng'].clone(), 'python': checkpoint['python_rng'],
           'numpy': (numpy_rng['name'], numpy_rng['keys'].numpy().astype(np.uint32),
                     numpy_rng['position'], numpy_rng['has_gauss'], numpy_rng['cached_gauss'])}
    return {'schema': SCHEMA, 'binding': binding, 'grid': 7, 'stage': 1,
            'mask': mask.clone(), 'optimizer': copy.deepcopy(checkpoint['optimizer']),
            'baseline': baseline.clone(), 'rng': rng, 'history': history, 'best': best,
            'feasible_count': count, 'completed_steps': n, 'record_history': True,
            'include_masks': False, 'resume_safe': True, 'legacy_provenance': dict(provenance),
            'selection_policy': 'new_CPF_no_positive_gap_gate; original_W1_optimization_prefix'}
