# EPI-NEXT status through the R127 closeout

This public summary supersedes the dated R18/no-result statements in the 2026-10-14 snapshot. It exposes no private execution manifests or medical assets.

The frozen R18 development validation recorded AUROC 0.95, AP approximately 0.954 and accuracy 0.85 on the existing observed 20-group validation cohort. This is not an independent test or clinical generalization claim. CT-FM and Ridge remain frozen; no new tuning or holdout selection follows from these results.

The fixed first CT/infection-reference pair passed ZIP/gzip integrity checks. The qualification entry rejected the CT at `KNOWN_SPATIAL_UNITS_REQUIRED`. The raw unit code, CT shape, dtype and scaling were not persisted before rejection; CT numeric scanning did not run. This does not establish file corruption or a proven unit-decoder defect. Pair geometry and fixed K8 remain unqualified, with medical denominator null. There is no first-case real R18 CAM or Dice/IoU result.

The frozen signed-CAM, B0/B1 and research-overlay implementations exist. B0 is the first planned medical overlap route at fixed 5%, 10% and 20% K8 area after qualification and separately authorized CAM production. Unknown reference coverage is not normal background or a zero score. Real model calls, medical-array consumption, demonstration and recording require their applicable independent authorization; source publication is none of these.

R128 concentrates on metadata-before-medical-rejection diagnostics, source HU and reference-extent evidence, and a new single fixed-pair request. At this publication checkpoint those new changes are in preparation, not part of the imported source snapshot. See the [source import and test boundaries](../consolidation/EPI_NEXT_SOURCE_IMPORT_20261017.md).
