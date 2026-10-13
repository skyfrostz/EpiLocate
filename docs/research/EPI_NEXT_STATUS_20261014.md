# EPI-NEXT research and engineering status (2026-10-14)

This public summary reflects locally reconciled evidence through 2026-10-13. It is an aggregate status update; it does not include the private execution ledger, approval records, source data, model weights, or internal worktrees. The engineering changes described below remain in private development branches and are not integrated into this public source tree.

## Research results

| Work | Latest evidence | Conclusion and boundary |
| --- | --- | --- |
| CT-FM classification | Training AUROC 1.00. On the fixed 20-group validation cohort: AUROC 0.45, average precision 0.550452, accuracy 0.45; TN 6, FP 4, FN 7, TP 3. | This is a substantial observed generalization gap. Overfitting is plausible, but the evidence does not identify it as the sole cause. The small, already-observed cohort does not establish independent-test performance or clinical generalization. |
| R18 multiple-instance classification | The cache attempt read its approved input and loaded the fixed weights, then failed in preprocessing before the first backbone forward. Actual model forwards, backward passes, updates, and cache entries were zero; classification metrics were not produced. | No R18 classification result exists. A synthetic regression reproduced a possible post-resize upper-bound rounding overshoot; the failed real input did not preserve the predicate-level values, so that mechanism is not confirmed as the real cause. No algorithm improvement can be claimed. |
| Localization | The previously reported P1 result remains 1/3 CPF-feasible and 0/10 hits among the annotated reference objects. The later E2-R engineering correction did not perform a new scientific readout; its earlier actual counters remain unknown. | The P1 count is limited to the annotated reference set and does not establish full lesion recall. No new localization improvement was measured. |

The R18 synthetic regression retained the existing shape, dtype, device, finite-value, and range checks. It did not alter model mathematics or the scientific protocol. A synthetic reproduction is diagnostic evidence only; it does not replace a real-input diagnosis.

## Engineering and display status

- The E2-R command path was corrected to derive the invocation from the verified dispatch binding. Generated positive and negative cases exercised the production parser and exact binding comparison without opening a scientific slot or calling the model.
- The 64-only readiness check was changed to depend on the current image and viewport, decode and render state, visible canvas, and the expected overlay draw. The prior real check's hidden hint did not preserve enough evidence to identify why it was hidden; its cause remains unknown. Synthetic browser regression does not count as a new real three-result verification.
- The 64-only candidate has not passed final spatial review, hospital-use approval, or final rehearsal. The prior development acceptance and later failed readiness check do not satisfy those gates.

These checks show bounded engineering progress. They do not establish algorithm improvement, clinical validity, hospital display approval, or production readiness. No new real scientific readout was produced by the engineering closeout summarized here.

## Data and interpretation limits

The classification cohort uses 60 fixed source groups, with 40 training and 20 validation groups, and weak group labels. The number of stack members is not a patient count. Source identity checks were nonconformant for six groups and not evaluated for the other 54. Patient independence and overlap with encoder pretraining remain unknown. The observed validation cohort is exploratory and must not be relabeled as an independent test set.

The documented local control reconciliation found the state internally consistent with no pending writer transaction. Administrative document-binding revisions do not constitute scientific execution. Historical failures and unknown actual counters remain unchanged.
