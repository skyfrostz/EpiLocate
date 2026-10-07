---
name: epilocate-project
description: Use for substantial EpiLocate repository tasks that need project context, canonical source selection, branch provenance, frozen research boundaries, agent dispatch, or engineering documentation updates.
---

# EpiLocate project workflow

1. Read the repository root `AGENTS.md`, `docs/project/PROJECT_CONTEXT.md`, and `docs/consolidation/SOURCE_MAP.md`. Read a more specific `AGENTS.md` for the area being changed.
2. Record repository root, branch, full `HEAD`, worktree, and relevant tracked, untracked, and ignored files. Verify any document's branch and commit before treating it as present in this checkout.
3. Discover available Skills, agents, scripts, tests, and contracts. Delegate bounded independent Frontend, Backend, Worker, Deployment, QA, Documentation, or Repository/Git work only to agents actually available. The main agent owns integration and final verification.
4. Choose the canonical source using the Source Map and current Git evidence. The Phase 5 implementation, parallel documentation, research Landing, and consolidation plan are distinct provenance lines. This handoff candidate has imported `apps/landing/`; Vue, Backend, Gateway, Worker, Showcase, and Review remain at their original root paths, and `services/` remains a future target.
5. Protect FrozenBaseline, checkpoint, preprocessing, research split/protocol evidence, Worker protocol, CPU reference, and numerical tolerance. Do not equate a functional GPU E2E pass with CPU/GPU numerical consistency, engineering MVP with production readiness, or heatmaps with clinical truth.
6. For significant engineering changes, update both iteration history and engineering journal in the delivery scope. If their branch has not been integrated, make that integration and synchronization an explicit delivery dependency; do not silently waive it. Cite full commit, test scope, environment, and open issues.
7. Run relevant tests and documentation checks, inspect staged paths for secrets and medical data, then report exact branch, commit, changed files, evidence, and remaining gaps. Do not auto-merge, auto-push, auto-deploy, or change frozen model assets.
