# Source provenance of the sanitized handoff snapshot

## Mainline integration, 2026-10-07

This integration starts from the existing public `main` commit `14c114ab26226561615315f7d3d25e42fcec64cc`. It imports the audited file tree of the independent Clinical Canvas snapshot `117ce7a61c6bd8ba6893ecb83445d8647c9965a1` (tree `6cc89f8295735610f45e0c686c3dfd88a86a6050`) by file content. The Clinical Canvas commit and internal Phase 5/research history do not become ancestors of `main`. The prior public `main` history remains reachable.

The source tree deliberately omits `MIDRC-RICORD-01.s5cmd` from its current files. That download-command file existed in the prior public `main` history, which this integration retains. Removing it from the tip does not remove the historical Git object; the final reachable-object audit must report that pre-existing exposure separately and must not label the whole history clean by inspecting only the tip.

## Historical independent handoff snapshot

The sections below describe the earlier independent sanitized handoff root and its original publication audit. They are historical evidence, not a certification of this later mainline integration. References to "this repository" or "this root" below mean that earlier standalone snapshot, not the consolidated `main` ancestry.

This repository is a **sanitized source snapshot with an independent Git root**. It is intended for public handoff, reproducible builds, and Git-based candidate releases. The complete internal Git history is preserved locally for internal evidence and is **not** contained in this branch. Internal SHAs below identify source evidence; they are not ancestors of this public root commit.

| Reference | SHA | Role |
| --- | --- | --- |
| Internal source | `f80d4cf406689cd031f993090783e281db93c4ef` | Preserved internal Phase 5 source and incident record. Not pushed through this branch. |
| Audited handoff candidate | `d498f0465f6b7d0e4d999562658356a734211bfa` | Internal candidate from which the initial payload was exported and compared file by file. |
| Audited handoff candidate tree | `973a488682394db2c90a5c9bb27f064b5ac59af3` | Internal Git tree at the candidate commit; this is not the final public tree. |
| Sanitized snapshot payload tree | `e1f1f810d006e6be4299e0b14e364514d1c5cf1b` | Git tree of the final staged payload **excluding this file**. A tree cannot contain its own hash without changing that hash. The published commit's full tree hash must be read with `git rev-parse HEAD^{tree}`. |

## Why a new root was required

The internal candidate's files were cleaned, but its ancestor history contains restricted investigation artifacts. A normal push of that ancestry would publish those Git objects even when absent from the candidate tip. The user authorized a new root from the audited candidate file tree. The original branches, commits, and local evidence remain unchanged; no history filtering, rebase, deletion, or force push was performed.

## File reconciliation and snapshot-only changes

Before snapshot-only edits, all 434 exported payload paths were compared byte for byte against the audited internal candidate, with no missing or extra paths. Final reconciliation against that candidate found **416 byte-identical files, 17 intentionally modified files, one excluded manifest, and this one added provenance file**. The modified files are listed below; no business logic, FrozenBaseline, model checkpoint, or numerical tolerance was changed in this sanitization step.

| Modified path | Reason |
| --- | --- |
| `.gitignore` | Exclude Word lock files and image download manifests. |
| `AGENTS.md`, `README.md` | Clarify snapshot history and remove the excluded manifest from listings. |
| `docs/backend/EpiLocate_API_Integration_Guide_V1.0.md` | Correct integrated document links. |
| `docs/consolidation/README.md`, `docs/consolidation/SOURCE_MAP.md` | Clarify internal SHA pointers versus the new public root. |
| `deploy/mvp/nginx-welcome.conf` | Allow the image service's observed final media domain in Welcome CSP. |
| Three `docs/handoff/*.docx` files | Fix table clipping, stale TOC numbers, and integrated source index; all pages reviewed. |
| `docs/handoff/HANDOFF_STATUS.md`, `docs/handoff/README.md`, `docs/handoff/RELEASE_SECURITY_AUDIT.md` | State actual snapshot gates, exclusions, and publication boundary. |
| `docs/phase5/remote_gpu_node_preparation.md` | Correct two relative links. |
| `docs/project/ENGINEERING_JOURNAL.md`, `docs/project/ITERATION_HISTORY.md`, `docs/project/PROJECT_CONTEXT.md` | Preserve historical evidence while distinguishing it from this root's ancestry and removing case-linked narrative. |

## Excluded asset categories

- Restricted medical images, object-level download manifests, and image sources of uncertain provenance.
- Restricted incident evidence and linkable identifiers.
- Research datasets and uncommitted research worktree outputs.
- Model weights, database/object-store contents, credentials, logs, caches, and virtual environments.
- Other local Office originals; only the three audited handoff Word copies are included.

The single tracked DICOM, `docs/interfaces/fixtures/p0_synthetic_ct.dcm`, was reproduced byte for byte from its generator and structurally reviewed as synthetic. No source-uncertain DICOM is allowed in this root.

## Secret and PHI checks

The audited candidate-tip file scan found no actual secret, private key, credential value, direct patient identifier, or source-uncertain medical image. A later targeted check found object-level image locators in a download manifest; that manifest was excluded from this public snapshot. The three Word copies passed XML, relationships, metadata, media, hidden-text, and native Word full-page review (8 + 7 + 16 pages).

Through application commit `649b0c665971cfefcc67509849947b2d3f7e49c7`, every reachable Git object was enumerated: one independent root, 529 objects, 429 unique blobs, three expanded Word ZIP files, one byte-verified synthetic DICOM, and 55 other image files. No blocking Secret / PHI finding remained. Three patient-field test strings were manually confirmed to be synthetic rejection tests. Because this provenance update creates a later commit, **the full reachable-object scan must be repeated against the final commit before push**. A working-tree-only scan does not satisfy the publication gate. Any positive finding stops publication.

This record states provenance and exclusion scope. It does not assert that the sanitized branch preserves complete project development history.
