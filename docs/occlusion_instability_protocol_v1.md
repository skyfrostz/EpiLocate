# Stage 1 — Occlusion Instability Protocol v1

STATUS: FROZEN

Protocol ID: `stage1-occlusion-instability-v1`
Baseline experiment: `FORMAL-BL-R18-V1`

## 1. Purpose and scientific boundary

This protocol measures occlusion response and prediction instability of the frozen
ResNet-18 reference classifier. It is a response/instability analysis, not lesion
localization accuracy. Candidate regions are response hypotheses and are not lesions,
ground truth, or diagnostic evidence. This protocol does not retrain the baseline,
train an occlusion-robust model, use LIME, or use Grad-CAM.

## 2. Frozen inputs and sealing

The reference checkpoint is `outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth`,
best epoch 2, selected by minimum validation loss, with SHA-256
`548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
The frozen Rule-B split is `outputs/data/formal_split_rule_b_v1/`.

The primary analysis uses only the frozen validation manifest (28 patients, 5,637
slices, 14 positive and 14 negative patients). Train data is limited to fixed smoke
fixtures and QA. The formal test split remains sealed: no test Dataset, DICOM pixels,
inference, predictions, metrics, or visualizations may be created or read.

Metadata confounding status is `PRESENT_AND_UNRESOLVED`.

## 3. Checkpoint and preprocessing

The checkpoint must pass SHA-256 verification, strict state-dict loading, and epoch 2
verification before inference. The model runs in `eval()` and
`torch.inference_mode()`, without an optimizer or backward pass.

Preprocessing is identical to the frozen baseline: DICOM slope/intercept to HU, window
C=-600/W=1500, [0,1] scaling, antialiased bilinear resize to 224x224, single-channel
replication to RGB, and ImageNet ResNet-18 mean/std normalization.

Masking occurs after resize and before ImageNet normalization. The filled grayscale
image is then replicated to RGB and normalized exactly as the baseline input.

## 4. Primary block masking

Block sizes are fixed at `16/32/64` pixels and strides at `8/16/32` pixels
(`stride = block_size / 2`). For block size `b`, starts are:

```text
S_b = {0, stride, 2*stride, ...} union {224-b}
```

The final start is always `224-b`. Blocks never cross the image boundary, are never
cropped, padded, or wrapped, and coordinates are generated in row-major order.

The number of positions per slice is fixed:

```text
16 px: 729
32 px: 169
64 px: 36
total: 934
```

The primary fill is the fixed [0,1] grayscale value `0.5`. Black fill, blur,
inpainting, and per-slice-mean fill are not part of the primary experiment.

## 5. Raw response definitions

For each slice, retain baseline and masked logits and probabilities:

```text
p0 = baseline positive probability
pg = masked positive probability
y0 = 1[p0 >= 0.5]
yg = 1[pg >= 0.5]
```

The fixed threshold is 0.5. Required raw metrics are:

```text
signed_probability_drop = p0 - pg
absolute_probability_change = abs(p0 - pg)
prediction_flip = 1[y0 != yg]
position_variance = Var_g(pg), ddof=0
p95_absolute_probability_change
```

Raw positive probabilities and signed/absolute changes remain available even when the
candidate response uses the original decision class.

## 6. Candidate response and validity

Candidate response is class-conditional to the baseline decision:

```text
y0 = baseline predicted class
q0 = baseline probability of class y0
qg = masked probability of the same class y0
decision_confidence_drop = q0 - qg
candidate_response = max(q0 - qg, 0)
```

Candidate response means: confidence decrease in the frozen baseline's original
prediction after the region is masked. It must not be called a lesion.

The fixed numerical validity rule is:

```text
epsilon_num = 1e-6
response_amplitude = max_g(abs(q0 - qg))
```

If `max_g(candidate_response) <= epsilon_num`, set:

```text
candidate_status = insufficient_positive_response
```

Do not select zero-response blocks to force a Top-10% region, and do not generate a
candidate region in this case. This epsilon is a numerical validity threshold, not a
medical threshold. Scalar response metrics remain reportable.

## 7. Slice-level and patient-level analysis

Slice-level results construct the response maps and provide QA. Patient is the primary
statistical unit. For each patient, calculate slice-first summaries without allowing
patients with more slices to receive greater cohort weight:

- slice count;
- baseline patient probability `mean_s(p0)` and thresholded class;
- median absolute probability change;
- IQR, P90, and P95 absolute change;
- prediction flip rate;
- position variance;
- valid-response slice proportion;
- scale consistency;
- insufficient-response count.

The primary aggregation is slice-first. Probability-first masked aggregation
(`mean_s(pg)`) is secondary and is not interpreted as common anatomy across slices.

No naive patient-level 2D heatmap is generated. Axial slices are not fused into a
single 2D spatial map.

## 8. Candidate regions and spatial maps

For each scale independently, rasterize block scores into the original 224x224 frame by
area assignment and arithmetic averaging of overlapping blocks. The primary candidate
representation is Top-10% of positive `candidate_response` blocks, retaining ties and
recording actual covered area. If the validity rule fails, no candidate region is
generated.

Two-of-three scale consensus is a secondary descriptive representation only. Candidate
regions are not lesion labels or ground truth.

## 9. Fixed cross-scale projection

Every scale uses the same fixed comparison grid and projection:

```text
comparison_grid = 14x14
projection = deterministic area-average pooling
```

The projection maps each rasterized 224x224 response map to the 14x14 grid using the
same area-average rule for every block scale. No scale-specific projection is allowed.

Cross-scale metrics are continuous descriptive measures:

- primary: Spearman rank correlation;
- secondary: Top-10% IoU, Dice, normalized center distance, normalized L1 map
  difference, and Pearson correlation.

No pass/fail threshold is assigned to these metrics.

## 10. Cohort uncertainty and provenance

Report patient median and IQR. Patient-level percentile bootstrap uses 1,000 resamples
with replacement and seed `20260925`. Valid denominators and insufficient-response
counts are reported; insufficient response is not treated as zero instability.

Raw grid responses are written to Parquet without masked images. Batched inference,
`model.eval()`, and `torch.inference_mode()` are required. Rasterized maps are generated
on demand.

Record protocol/config hashes, checkpoint hash, frozen split hashes, Git commit,
runtime versions, seed, grid parameters, fill, epsilon, projection algorithm, output
schema, and timestamps.

## 11. Future robust-model comparison

Any future occlusion-robust classifier must use the same preprocessing, validation
manifest, mask grid, fill, threshold, response definitions, patient aggregation,
projection, metrics, and bootstrap procedure. Comparison is paired at slice and patient
levels. The frozen baseline checkpoint is never changed.

## 12. Safety gates

Automated QA must verify checkpoint hash and epoch, strict loading, deterministic grid
counts (729/169/36/934), fixed block area and boundaries, preprocessing equivalence,
baseline probability equivalence, batch/single inference equivalence, finite outputs,
candidate validity and Top-10% behavior, deterministic 14x14 projection, deterministic
patient bootstrap, repeated-run summary hash, unchanged checkpoint hash, no optimizer,
no backward, no LIME/Grad-CAM, and no test access.

Formal validation and formal test execution are separate future actions. This freeze
does not authorize either one.
