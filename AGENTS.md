# EpiLocate Agent Operating Rules

These rules apply from the repository root. Read any more specific `AGENTS.md` in the directory being changed; preserve its valid constraints.

## Start here

For nontrivial work, read [Project Context](docs/project/PROJECT_CONTEXT.md) and [Source Map](docs/consolidation/SOURCE_MAP.md), then the relevant API, frontend, Worker, deployment, research, or engineering history documents. First record the repository root, worktree, branch, full `HEAD`, and tracked, untracked, and ignored state relevant to the task. In this handoff branch, `apps/landing/` contains Welcome source; `services/` remains a planning directory.

## Capability first and dispatch

Check available Skills, configured agents, existing scripts, tests, and documents before implementing a substantial task. Use an existing project Skill when available. Delegate bounded, independent work only to agents actually available in the current environment. A role in this table is a task scope, not a claim that a specialist agent is installed.

| Task | Delegate scope when an agent is available |
| --- | --- |
| Vue AI Web or UI | Frontend/UI |
| Backend, API, database | Backend/API |
| Worker, CUDA, frozen runtime integration | Worker/Runtime |
| Deployment and operations | Deployment |
| Tests and regression | QA |
| History and documentation | Documentation |
| Git, worktrees, source provenance | Repository/Git |

The main agent plans, assigns, resolves conflicts, integrates, validates, and reports. If no suitable agent is available, the main agent does that work. Parallel agents must use distinct ownership boundaries and must not edit each other's worktrees.

## Plan before modifying

For cross-module, architectural, deployment, database, FrozenBaseline, Git integration, or production configuration work: audit the exact branch and code, state a plan and evidence limits, verify that the task scope authorizes the change, implement, test, commit, and report. An existing clear user authorization satisfies the scope check; do not request it again. Do not guess across missing evidence. Check branch ancestry, unique commits, dirty and ignored files, test reports, and runtime dependencies before migration or integration.

## Canonical source and application boundaries

Use [Project Context](docs/project/PROJECT_CONTEXT.md) and the fixed [Source Map](docs/consolidation/SOURCE_MAP.md) to select source. A similarly named older worktree is not automatically canonical. This repository is a sanitized, independent Git root whose payload was derived from an audited internal candidate; it does not contain the internal Phase 5 commit ancestry or full development history. See [Source Provenance](docs/handoff/SOURCE_PROVENANCE.md). `apps/landing/` contains imported Landing source, while Vue, Backend, Gateway, Worker, Showcase, and Review remain at their original root paths. The old Review Server, `aid_site` Showcase, and AI System session are separate applications; do not combine their accounts or authentication by inference.

## Frozen and evidence boundaries

Do not change FrozenBaseline, checkpoint, frozen preprocessing, mathematics, protocol, CPU/GPU tolerance, or Stage 1 frozen evidence without an explicitly scoped task. Preserve `MOCK`, `LIVE_CASE`, and frozen research validation labels. Distinguish code **implemented**, tests **passed**, branch **integrated**, environment **deployed**, result **validated**, **production ready**, and **clinical valid**. A GPU functional E2E pass does not pass the open CPU/GPU numerical gate. Engineering acceptance does not establish clinical validity. Cite branch, full commit, test scope, environment, and report for claims; do not infer operator, date, or debugging sequence from commit messages.

Treat conversation, memory, and old summaries as leads. Resolve facts against current code, Git refs and ancestry, executed tests, stored reports, then documentation. Report contradictions instead of silently favoring a chat claim.

## Documentation and security

For material code, test, configuration, deployment, or acceptance changes, update both `docs/project/ITERATION_HISTORY.md` and `docs/project/ENGINEERING_JOURNAL.md` in the delivery scope, following `docs/project/DOCUMENTATION_GUIDE.md`. Both are integrated in this handoff checkout. Pure documentation changes may stand alone. Run `scripts/check_project_documentation.py` with an explicit base or range, plus `git diff --check`.

Never commit credentials, tokens, private keys, `.env`, signed object URLs, raw patient imaging, PHI, private object contents, or model weights. Review staged files before any push or publication. Sending a specific medical image to an external destination requires explicit per-file, per-destination authorization.

## Git safety

Work in the assigned branch and worktree. Do not reset or clean another agent's state, overwrite an active worktree, force push, force remove a worktree, or delete a unique historical branch without an audit and explicit scope. Do not merge, push, deploy, or move source trees merely because a document describes a future target.
