# Sanitized Handoff Release Security Audit

**Scope:** public, independent Git root on `handoff/pre-b-transfer-20260929`. Its files came from an audited internal candidate, but no internal commit is an ancestor. See [SOURCE_PROVENANCE](SOURCE_PROVENANCE.md). This report records risk categories and checks without publishing restricted identifiers or values.

| Scope | Decision and evidence |
| --- | --- |
| Internal Git history | Preserved locally for internal evidence. Excluded entirely from the public root; no history rewrite, filter-repo, rebase, or force push. |
| Restricted incident artifacts | Excluded from the audited candidate payload and from this new Git root. The public incident write-up is limited to a case-neutral decoder mechanism and operational lessons. |
| Object-level image download manifest | Removed from this public snapshot after finding direct object locators in the audited candidate tree. Its original is preserved in the internal candidate. README listings were corrected. |
| `docs/interfaces/fixtures/p0_synthetic_ct.dcm` | Allowed. Reproduced byte for byte with its generator; DICOM structure showed no patient tags, private tags, Study/Series UID, or burned-in text. This is the only tracked DICOM. |
| Three `docs/handoff/*.docx` copies | **PASS local.** Author/core metadata, relationships, hidden text, embedded diagrams, and case-linkable patterns audited. Native Word print-quality PDF review covered every page (8 + 7 + 16); tables and Chinese text were readable after layout corrections. |
| Text, source, and image payload | Candidate-tip inspection found no private-key blocks, actual credentials, direct identifiers, or source-uncertain medical imagery. Credential-related variable names and synthetic test strings were manually distinguished from real values. |
| Reachable sanitized Git objects | **PENDING:** after root commit creation, enumerate every reachable object, inspect all blobs (including expanded Word ZIP members), confirm one root and only the intended branch ref, then record PASS before ordinary push. |
| Existing remote documentation history | A separate documentation branch previously published a Word source copy with author metadata. This sanitized root does not remove or alter that independent remote history; remediation of that branch is a separate follow-up. |

The root-object scan is the publication decision point. Any PHI, secret, private key, actual credential, or source-uncertain medical image found there requires stopping before push.
