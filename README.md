<div align="center">

<img src="./logo.png" alt="EpiLocate Logo" width="180" />

# EpiLocate · 疫影寻灶

**面向新发突发传染病的弱监督、可解释医学影像病灶定位研究与工程验证**  
**Weakly Supervised & Explainable Lesion Localization for Emerging Infectious-Disease Imaging**

[![Research Prototype](https://img.shields.io/badge/status-research%20prototype-6f42c1)](#项目状态--project-status)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-powered-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![DICOM](https://img.shields.io/badge/imaging-DICOM-2ea44f)](https://www.dicomstandard.org/)
[![GitHub Stars](https://img.shields.io/github/stars/skyfrostz/EpiLocate?style=flat)](https://github.com/skyfrostz/EpiLocate/stargazers)

[中文](#中文) · [English](#english) · [Roadmap](#路线图--roadmap) · [Reproducibility](#可复现性与安全边界--reproducibility--safety)

</div>

---

<a id="中文"></a>

# 中文

## 项目简介

**EpiLocate（疫影寻灶）** 是一个面向新发突发传染病医学影像的研究型项目，目标是在**缺乏大规模像素级病灶标注**的现实条件下，仅依赖图像级或病例级类别标签，研究能够稳定定位病灶、解释模型决策并支持医生反馈修正的方法。

项目以“**方法研究为主、工程验证为辅**”为定位：分类网络、DICOM 预处理、训练管线与 Web 原型均用于支撑核心研究，而不是替代核心研究问题。项目当前已经完成从 DICOM 整理、患者级数据划分、统一预处理、质量控制到 ResNet-18 基线训练的一套可复现 Baseline 工作流；后续核心研究围绕三阶段技术路线推进：

1. **分块掩码驱动的逐级稳定粗定位**：分析遮挡扰动导致的定位漂移，并训练对局部遮挡更鲁棒的分类器；
2. **粗定位先验约束下的 LIME 精细化定位**：在候选区域内进行局部解释与边界细化；
3. **临床诊断逻辑对齐与医生交互**：组织可理解的定位证据，并允许医生确认、补充、删除或修正病灶区域。

> 本仓库属于研究与竞赛原型，不是医疗器械，也不用于临床诊断或治疗决策。

独立的项目展示网站位于 [`aid_site/`](aid_site/README.md)，已部署于 [aid.xbstu.com](https://aid.xbstu.com)。它展示研究目标、技术路线与验证计划，并提供受登录保护的 `/api/v1` 占位契约；当前不接入真实影像或算法。既有人工审查工作台代码仍位于 `epilocate_review_server/`。

项目依托“**面向新发突发传染病影像的弱监督可解释病灶定位方法研究**”课题的问题框架开展，并以可运行的医学影像辅助诊断原型作为算法验证和演示载体。

---

## 为什么是 EpiLocate？

在新发传染病暴发早期，影像数据往往能够快速积累，但高质量像素级病灶勾画需要影像科医生逐层完成，成本高、周期长。与此同时，病例级诊断、检查结果和影像报告等“弱标签”通常更容易获得。

EpiLocate 关注的问题不是“如何在已经拥有大量精细标注时再做一个分割模型”，而是：

> **当只有弱标签时，能否让模型稳定地找到病灶、说明为什么找到这里，并让医生能够核验和纠正它？**

这也是项目从单纯分类进一步走向**稳定定位 → 精细定位 → 可解释交互**的原因。

---

## 核心技术路线

```text
DICOM / CT Imaging
        │
        ▼
统一数据审计与预处理
HU → 肺窗 → 归一化 → 224×224 → ImageNet Normalize
        │
        ▼
图像级 / 病例级分类器
ResNet-18 Baseline
        │
        ├─────────────── Baseline / 对照
        │                  Grad-CAM++ 等
        │
        ▼
Stage 1 · 分块掩码逐级稳定定位
遮挡敏感性分析 → 遮挡免疫鲁棒学习 → 稳定粗定位
        │
        ▼
Stage 2 · 粗定位引导 LIME 精细化
候选区域先验 → 局部扰动解释 → 边界精细化
        │
        ▼
Stage 3 · 临床逻辑对齐与医生交互
证据呈现 → 医生确认 / 圈改 / 增删 → 反馈记录
        │
        ▼
Web Research Prototype
分类 + 粗定位 + 精细定位 + 解释 + 交互
```

当前仓库已经完整落地的是**数据与 Baseline 层**；三阶段核心定位算法与 Web 交互层仍按路线图继续实现。

---

## 项目状态 · Project Status

| 模块 | 状态 | 当前说明 |
|---|---|---|
| DICOM 安全整理与 Manifest | ✅ 已完成 | 保留原始文件，不静默覆盖 |
| Series 审计与筛选 | ✅ 已完成 | 支持开发规则与正式冻结协议 |
| 患者级 Train/Val/Test 划分 | ✅ 已完成 | 按患者拆分，避免切片级数据泄漏 |
| CT 统一预处理 | ✅ 已完成 | HU、肺窗、缩放、ImageNet 标准化 |
| 抽样 QC 与元数据审计 | ✅ 已完成 | 预处理 QC、Header 审计、SHA-256 复核 |
| Dataset / DataLoader | ✅ 已完成 | 输入检查、标签检查、NaN/Inf 防护 |
| ResNet-18 Baseline | ✅ 已完成 | tiny overfit、smoke、10-epoch baseline |
| 全量 MIDRC-RICORD 下载审计 | ✅ 已完成 | 已完成 Header 级全量审计 |
| 正式 Cohort 冻结 | 🚧 进行中 | 仍需完成部分 Series 人工复核 |
| 分块掩码逐级定位 | 🧪 研究中 | 核心 Stage 1 |
| 遮挡免疫鲁棒训练 | 🧪 研究中 | 核心 Stage 1 |
| LIME 精细定位 | 🗓️ 计划中 | 核心 Stage 2 |
| 临床解释与医生交互 | 🗓️ 计划中 | 核心 Stage 3 |
| Web 演示系统 | 🗓️ 计划中 | 用于研究结果展示与交互验证 |

---

## 当前 Baseline 做了什么？

当前开发集围绕 MIDRC-RICORD-1A / 1B 构建了一套严格的开发用途 Baseline 管线。

### 1. 数据安全与 Series 选择

开发集原始数据包含：

- **10 位患者**
- **6,688 张 DICOM**
- **37 个 Series**

开发阶段按一致规则筛选常规轴位 CT：`ORIGINAL / PRIMARY / AXIAL`、`STANDARD` 重建核、1.25 mm 层厚。当前选中 10 个 Series、2,346 张切片。

针对后续正式实验，仓库还提供冻结协议 `formal-series-selection-rule-b-v1`：在满足 CT、轴位、诊断用途，并排除 Scout / Localizer、明确重建和 bone-only Series 等硬条件后，再按覆盖率、层厚、PixelSpacing 与覆盖范围排序。该规则不读取标签、collection、UID 顺序或模型输出，从而尽量避免选择偏差。

### 2. 患者级数据划分

当前开发模式固定 `seed=42`，每类患者按 `3 / 1 / 1` 分配到 train / validation / test：

| Split | 患者数 | 切片数 |
|---|---:|---:|
| Train | 6 | 1,422 |
| Validation | 2 | 507 |
| Test | 2 | 417 |

患者集合之间交集为 0。仓库显式禁止随机打散切片后再划分数据集，以避免同一患者不同切片出现在训练集和验证/测试集。

### 3. 统一 CT 预处理

唯一预处理入口：

```python
src.preprocessing.preprocess_dicom(path, config)
```

处理链：

```text
DICOM Pixel
  → RescaleSlope / RescaleIntercept
  → Hounsfield Unit (HU)
  → Lung Window (C=-600, W=1500)
  → Clip [-1350, 150]
  → Normalize to [0, 1]
  → Bilinear Antialiased Resize to 224×224
  → Replicate to 3 channels
  → ImageNet normalization
```

预处理会拒绝明显不符合预期的输入，例如非 CT、Localizer/Scout、非 `MONOCHROME2`、非法二维尺寸以及 NaN/Inf 数据。

### 4. 模型与训练

当前模型：

```text
ImageNet pretrained ResNet-18
└── fc: Linear(512 → 2)
```

默认训练配置：

| 参数 | 值 |
|---|---|
| Optimizer | AdamW |
| Learning rate | 1e-4 |
| Weight decay | 0.01 |
| Batch size | 8 |
| Epochs | 10 |
| Checkpoint selection | minimum validation loss |
| Test set usage | final evaluation only |

正式 Baseline 前必须依次通过 eligibility、tiny-overfit 和 smoke safety gates。

---

## Baseline 结果如何理解？

> **以下结果仅用于验证工程链路是否能够工作，不代表科研结论，也不能用于医学性能宣传。**

当前 10 位患者开发集上的 10-epoch Baseline，best epoch 为 4：

| Metric | Validation result |
|---|---:|
| Train loss | 0.029545 |
| Validation loss | 1.875501 |
| Slice-level Accuracy | 0.287968 |
| Slice-level ROC-AUC | 0.092482 |
| Sensitivity | 0 |
| Specificity | 0.648889 |

该结果反映出**严重的患者级过拟合与较差的跨患者泛化**。由于 validation 仅有 2 位患者，当前结果不能用于比较模型优劣，也不能外推到真实临床人群。下一步应优先扩大患者规模、冻结正式 cohort，并保持患者级划分后再开展正式评测。

Tiny overfit 与 smoke run 的意义不同：它们用于验证训练、checkpoint、reload、inference 以及数值稳定性，而不是用于证明模型具有实际诊断性能。

---

## 全量数据进展

仓库已将 IDC 全量数据与开发集分目录保存，避免互相覆盖。

当前全量目录包含 **53,076 个 DICOM**：

- MIDRC-RICORD-1A：31,856 张，110 位患者，120 个 Study，229 个 Series
- MIDRC-RICORD-1B：21,220 张，117 位患者，120 个 Study，120 个 Series

Header 级审计读取错误为 0，跨 Collection PatientID 冲突为 0。开发集中的 6,688 个 SOP UID 是完整 Collection 的预期子集，因此两个目录存在内容重合是设计行为，不应直接删除或合并。

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/skyfrostz/EpiLocate.git
cd EpiLocate
```

### 2. 创建并激活虚拟环境

Linux / macOS：

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

主要依赖包括 PyTorch、torchvision、pydicom、NumPy、pandas、scikit-learn、Pillow、Matplotlib 与 PyYAML。

### 4. 运行测试

```bash
python -m unittest discover -s tests -v
```

### 5. 数据整理与审计

先执行只读扫描：

```bash
python scripts/organize_dicoms.py
```

确认汇总后再显式执行移动：

```bash
python scripts/organize_dicoms.py --execute
```

继续运行：

```bash
python scripts/summarize_series.py --config configs/baseline.yaml
python scripts/create_splits.py --config configs/baseline.yaml
python scripts/check_preprocessing.py --config configs/baseline.yaml
python scripts/check_dicom_metadata.py --config configs/baseline.yaml
```

### 6. Baseline 安全门与训练

```bash
python scripts/create_baseline_eligibility.py --config configs/baseline.yaml
python scripts/run_tiny_overfit.py --config configs/baseline.yaml
python train.py --config configs/baseline.yaml --experiment smoke
python train.py --config configs/baseline.yaml --experiment baseline
```

如果前置安全门未通过，训练入口会主动停止，而不是绕过检查继续执行。

---

## 正式 Series 复核

正式实验使用：

```text
configs/formal_series_selection_rule_b_v1.json
```

生成和校验人工复核材料：

```bash
python scripts/prepare_series_manual_review.py
python scripts/validate_manual_series_decisions.py
```

当前仍存在少量技术平局或诊断类型不确定 Series，需要完成人工复核理由后，才能冻结正式 cohort 与 full split。

---

## 仓库结构

```text
EpiLocate/
├── configs/                 # Baseline 与正式 Series 选择配置
├── scripts/                 # 数据整理、审计、QC、安全门与实验工具
├── src/                     # Dataset、预处理、模型、训练核心逻辑
├── tests/                   # 预处理与数据安全相关测试
├── train.py                 # Smoke / Baseline 训练入口
├── infer.py                 # 推理入口（当前仍待扩展）
├── prepare_index.py         # 数据索引准备入口
├── requirements.txt         # Python 依赖
├── MIDRC-RICORD-01.s5cmd    # MIDRC-RICORD 数据下载相关清单
├── logo.png                 # 项目 Logo
└── README.md
```

本地数据、患者级清单、QC 图、模型权重、运行输出等敏感或大型文件均不应提交到远程仓库。

---

## 路线图 · Roadmap

### Phase 0 — Reproducible Baseline ✅

- [x] DICOM 安全整理与 Manifest
- [x] Header / Series 审计
- [x] 患者级划分
- [x] 统一 CT 预处理
- [x] 抽样 QC
- [x] Dataset / DataLoader
- [x] ResNet-18 初始化检查
- [x] Tiny overfit
- [x] 1-epoch smoke run
- [x] 10-epoch development baseline
- [x] IDC 全量数据 Header 审计

### Phase 1 — Stable Coarse Localization 🚧

- [ ] 冻结正式 cohort 与 full split
- [ ] 多尺度分块遮挡实验
- [ ] 定位失稳量化分析
- [ ] 遮挡免疫鲁棒分类器训练
- [ ] 逐级候选区域收缩
- [ ] 粗定位稳定性指标与消融实验

### Phase 2 — LIME-guided Fine Localization 🗓️

- [ ] 将稳定粗定位转化为局部先验
- [ ] 在候选区域内执行 LIME 局部扰动
- [ ] 病灶边界精细化
- [ ] Dice / IoU / Pointing Game 评测
- [ ] 与 CAM / Grad-CAM++ 对照

### Phase 3 — Clinical Explainability & Interaction 🗓️

- [ ] 组织定位证据与解释信息
- [ ] 医生确认 / 删除 / 补充 / 边界修正
- [ ] 临床诊断逻辑一致性评价
- [ ] 交互可用性记录

### Phase 4 — Web Research Prototype 🗓️

- [ ] DICOM / NIfTI / 常见图像上传
- [ ] 分类结果展示
- [ ] 遮挡过程可视化
- [ ] 稳定粗定位展示
- [ ] LIME 精细定位展示
- [ ] 医生反馈与结果留存
- [ ] Baseline / 降级演示模式

---

## 评价指标

后续正式研究将按不同层次分别评价，而不是只关注单一分类准确率。

| 维度 | 计划指标 |
|---|---|
| 分类性能 | AUC、Accuracy、Sensitivity、Specificity |
| 遮挡鲁棒性 | 遮挡前后预测一致性、置信度波动 |
| 粗定位稳定性 | 不同遮挡尺度下区域一致性、重复试验稳定性 |
| 精细定位 | Dice、IoU、Pointing Game |
| 解释一致性 | 医生对定位依据与临床逻辑一致性的评价 |
| 交互可用性 | 修正完成率、修正时间、主观可用性 |
| 工程性能 | 单例推理耗时、模块响应时间、模型与系统体积 |

医生手工勾画仅作为定位评价金标准，不参与弱监督训练。

---

## 可复现性与安全边界 · Reproducibility & Safety

### 数据泄漏防护

- 数据集必须按**患者级**而非切片级划分；
- train / validation / test 患者集合必须互斥；
- checkpoint 只根据 validation loss 选择；
- test 仅用于最终评估，不参与模型选择；
- Series 选择规则不得读取模型结果或利用标签进行“挑片”。

### 数据完整性

- 数据审计记录源文件 SHA-256；
- 整理脚本不修改 DICOM 像素内容；
- 不覆盖已存在目标文件；
- 被排除 Series 保留在原位并记录原因；
- 关键训练阶段通过明确 safety gates 控制。

### 隐私与医疗数据

请勿将以下内容提交到公开仓库：

- 原始医学影像；
- 含患者标识符的 CSV / Manifest；
- 患者级数据划分；
- 本地 QC 图；
- 医院脱敏前或未经授权的数据；
- 模型训练过程中可能携带敏感信息的输出。

真实医院数据必须在完成数据脱敏、授权与伦理审批后，按项目批准范围使用。

### 研究用途声明

EpiLocate 当前是**研究原型**：

- 不构成医疗建议；
- 不应直接用于临床诊断、筛查或治疗决策；
- 当前开发集指标不代表真实临床性能；
- 在正式研究结论发布前，应以更大规模患者级数据和独立验证为基础。

---

## 降级与对照方案

项目主线始终是：

```text
分块掩码逐级稳定定位
        → 粗定位引导的 LIME 精准定位
        → 临床诊断逻辑对齐与医生交互
```

ResNet / DenseNet + Grad-CAM++、肺区约束与三维平滑等成熟方案只作为**对照基线或进度受限时的工程降级路径**，不作为项目主要创新依据。

---

## 参考文献

1. **AFLoc: Annotation-Free Pathology Localization via Multi-level Semantic Alignment.** *Nature Biomedical Engineering*, 2026. DOI: `10.1038/s41551-025-01574-7`.
2. Yang Z, Zhao L, Wu S, et al. **Lung Lesion Localization of COVID-19 From Chest CT Image: A Novel Weakly Supervised Learning Method.** *IEEE Journal of Biomedical and Health Informatics*, 2021, 25(6): 1864–1872.
3. Selvaraju RR, Cogswell M, Das A, et al. **Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization.** ICCV, 2017.
4. Zhou B, Khosla A, Lapedriza A, et al. **Learning Deep Features for Discriminative Localization.** CVPR, 2016.

---

## 贡献

项目仍处于快速研究迭代阶段。欢迎围绕以下方向提交 Issue 或 Pull Request：

- 医学影像数据工程与 DICOM 质量控制；
- 弱监督病灶定位；
- 遮挡鲁棒学习；
- LIME / CAM 类可解释方法；
- 医学影像评测与患者级实验设计；
- 临床可解释交互；
- Web 研究原型与可视化。

提交贡献时请**不要包含任何受保护医疗数据或患者可识别信息**。

---

<a id="english"></a>

# English

## Overview

**EpiLocate** is a research-oriented medical imaging project for emerging and outbreak infectious diseases. It focuses on **weakly supervised, explainable lesion localization** under a realistic constraint: imaging data may become available quickly, while large-scale pixel-level expert annotations are expensive and slow to obtain.

Instead of treating classification as the final goal, EpiLocate studies a three-stage path:

1. **Progressively stable coarse localization with block masking** — characterize localization drift under occlusion and train a classifier that is more robust to missing local evidence;
2. **LIME-based fine localization guided by the coarse prior** — constrain local perturbation to candidate regions and refine lesion boundaries;
3. **Clinical-logic alignment and physician interaction** — present interpretable evidence and allow experts to confirm, add, remove, or edit predicted lesion regions.

The repository currently provides a reproducible **data + baseline foundation**: DICOM organization, Series auditing, patient-level splitting, unified CT preprocessing, QC, Dataset/DataLoader checks, pretrained ResNet-18 initialization, tiny-overfit validation, smoke training, and a 10-epoch development baseline.

> EpiLocate is a research prototype. It is not a medical device and must not be used for clinical diagnosis or treatment decisions.

---

## Research Motivation

During the early stage of an emerging infectious-disease outbreak, imaging studies can accumulate much faster than expert pixel-level annotations. A chest CT study may contain hundreds of slices, making dense manual lesion annotation difficult to scale quickly.

At the same time, weak labels such as case-level diagnoses or image-level categories are often easier to obtain. EpiLocate therefore asks:

> **Can a model localize lesions reliably from weak labels, explain why a region matters, and expose its output to expert verification and correction?**

The project treats the web application, classification backbone, and preprocessing stack as the engineering carrier of the research rather than as substitutes for the research question itself.

---

## Research Pipeline

```text
DICOM / CT imaging
        │
        ▼
Data audit & standardized preprocessing
HU → lung window → normalization → 224×224 → ImageNet normalization
        │
        ▼
Image-level / case-level classifier
ResNet-18 baseline
        │
        ▼
Stage 1 · Progressive block-mask localization
Occlusion analysis → occlusion-robust learning → stable coarse region
        │
        ▼
Stage 2 · Coarse-prior-guided LIME refinement
Local perturbation → contribution analysis → boundary refinement
        │
        ▼
Stage 3 · Clinical explanation & interaction
Evidence presentation → expert editing → feedback recording
        │
        ▼
Interactive research prototype
```

---

## What Is Implemented Today?

The current codebase contains a complete development baseline workflow for MIDRC-RICORD-1A / 1B.

### Data engineering

- Safe DICOM organization without modifying pixel content;
- Manifest generation and SHA-256 integrity checks;
- Series-level auditing and explicit exclusion reasons;
- Patient-level train / validation / test splitting;
- Frozen formal Series-selection protocol for the full cohort;
- Header-level auditing for the downloaded full MIDRC-RICORD collections.

### Preprocessing

All model inputs use a single preprocessing entry point:

```python
src.preprocessing.preprocess_dicom(path, config)
```

Pipeline:

```text
DICOM pixels
  → RescaleSlope / RescaleIntercept
  → Hounsfield Units
  → lung window (C=-600, W=1500)
  → clip to [-1350, 150]
  → normalize to [0,1]
  → antialiased bilinear resize to 224×224
  → replicate to three channels
  → ImageNet normalization
```

### Model baseline

```text
ImageNet-pretrained ResNet-18
└── Linear(512, 2)
```

Default development setup:

| Setting | Value |
|---|---|
| Loss | CrossEntropyLoss |
| Optimizer | AdamW |
| Learning rate | 1e-4 |
| Weight decay | 0.01 |
| Batch size | 8 |
| Epochs | 10 |
| Checkpoint criterion | minimum validation loss |
| Test role | final evaluation only |

Training is intentionally gated by eligibility checks, a tiny-overfit test, and a one-epoch smoke run.

---

## Development Dataset Snapshot

The current small development subset contains:

- 10 patients;
- 6,688 DICOM files;
- 37 Series;
- 10 selected Series / 2,346 eligible slices after the development selection rule.

Current patient-level split:

| Split | Patients | Slices |
|---|---:|---:|
| Train | 6 | 1,422 |
| Validation | 2 | 507 |
| Test | 2 | 417 |

There is no patient overlap across splits.

The full downloaded directory currently contains **53,076 DICOM files** across MIDRC-RICORD-1A and MIDRC-RICORD-1B. The formal cohort is **not yet frozen**, because a small number of technically tied or diagnostically ambiguous Series still require documented manual review.

---

## Development Baseline Results

> **These numbers are engineering/development results only. They are not scientific or clinical performance claims.**

For the current 10-patient development baseline, the best checkpoint occurred at epoch 4:

| Metric | Validation |
|---|---:|
| Train loss | 0.029545 |
| Validation loss | 1.875501 |
| Slice-level Accuracy | 0.287968 |
| Slice-level ROC-AUC | 0.092482 |
| Sensitivity | 0 |
| Specificity | 0.648889 |

The result indicates severe patient-level overfitting and poor cross-patient generalization. With only two validation patients, the metrics are highly unstable and must not be used to rank models or infer real-world medical performance.

The correct next step is to expand the patient-level cohort, freeze the formal Series-selection decisions, and repeat evaluation under a larger and properly separated dataset.

---

## Quick Start

```bash
git clone https://github.com/skyfrostz/EpiLocate.git
cd EpiLocate
python -m venv .venv
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

Run the baseline preparation pipeline:

```bash
python scripts/summarize_series.py --config configs/baseline.yaml
python scripts/create_splits.py --config configs/baseline.yaml
python scripts/check_preprocessing.py --config configs/baseline.yaml
python scripts/check_dicom_metadata.py --config configs/baseline.yaml
```

Run training safety gates and experiments:

```bash
python scripts/create_baseline_eligibility.py --config configs/baseline.yaml
python scripts/run_tiny_overfit.py --config configs/baseline.yaml
python train.py --config configs/baseline.yaml --experiment smoke
python train.py --config configs/baseline.yaml --experiment baseline
```

---

## Formal Series Review

The frozen formal selection protocol is stored at:

```text
configs/formal_series_selection_rule_b_v1.json
```

Generate and validate manual review materials with:

```bash
python scripts/prepare_series_manual_review.py
python scripts/validate_manual_series_decisions.py
```

The rule is designed to avoid model- or label-driven Series selection.

---

## Repository Layout

```text
EpiLocate/
├── configs/                 # Baseline and formal Series-selection configs
├── scripts/                 # Data preparation, audits, QC and safety gates
├── src/                     # Dataset, preprocessing, model and training logic
├── tests/                   # Data/preprocessing safety tests
├── train.py                 # Smoke and baseline training entry point
├── infer.py                 # Inference entry point (to be expanded)
├── prepare_index.py         # Dataset index preparation
├── requirements.txt         # Python dependencies
├── MIDRC-RICORD-01.s5cmd    # MIDRC-RICORD download manifest
├── logo.png
└── README.md
```

---

## Roadmap

### Reproducible baseline ✅
- [x] DICOM organization and manifest
- [x] Series audit
- [x] Patient-level data split
- [x] Shared CT preprocessing
- [x] QC and metadata audit
- [x] Dataset / DataLoader validation
- [x] ResNet-18 baseline initialization
- [x] Tiny-overfit test
- [x] One-epoch smoke training
- [x] 10-epoch development baseline
- [x] Full-download Header audit

### Stage 1 — Stable coarse localization 🚧
- [ ] Freeze formal cohort and full split
- [ ] Multi-scale block-mask perturbation experiments
- [ ] Quantify localization instability
- [ ] Occlusion-robust classifier training
- [ ] Progressive candidate-region refinement
- [ ] Stability metrics and ablations

### Stage 2 — LIME-guided fine localization 🗓️
- [ ] Use stable coarse localization as a prior
- [ ] Restrict LIME perturbations to candidate regions
- [ ] Refine lesion boundaries
- [ ] Dice / IoU / Pointing Game evaluation
- [ ] Compare with CAM / Grad-CAM++ baselines

### Stage 3 — Clinical explanation and interaction 🗓️
- [ ] Present model evidence in a clinically interpretable form
- [ ] Support expert confirmation and editing
- [ ] Record feedback
- [ ] Evaluate explanation consistency and usability

### Stage 4 — Web research prototype 🗓️
- [ ] Imaging upload and preprocessing
- [ ] Classification visualization
- [ ] Block-mask process visualization
- [ ] Coarse localization visualization
- [ ] LIME refinement visualization
- [ ] Physician feedback workflow
- [ ] Baseline / fallback demonstration mode

---

## Evaluation Plan

| Dimension | Planned metrics |
|---|---|
| Classification | AUC, Accuracy, Sensitivity, Specificity |
| Occlusion robustness | prediction consistency, confidence variation |
| Coarse localization stability | region overlap and drift across masking scales |
| Fine localization | Dice, IoU, Pointing Game |
| Explanation consistency | expert assessment against clinical reasoning |
| Interaction usability | completion rate, correction time, subjective usability |
| Engineering | inference time, module response time, model/system footprint |

Expert pixel-level annotations are intended as evaluation references only, not as supervision for the weakly supervised training objective.

---

## Reproducibility & Safety

EpiLocate intentionally enforces several safeguards:

- split data by **patient**, never by randomly shuffled slices;
- ensure patient sets are mutually exclusive across train / validation / test;
- select checkpoints from validation loss only;
- keep test data out of model selection;
- preserve excluded Series and explicit exclusion reasons;
- hash source files for integrity checks;
- fail loudly on invalid DICOM metadata or non-finite tensors;
- gate training through prerequisite validation steps.

### Medical data privacy

Do **not** commit raw medical images, patient identifiers, private manifests, local QC outputs, hospital datasets, or unauthorized derivatives to a public repository.

Any hospital data must be de-identified and used only after the appropriate authorization and ethics process has been completed.

### Research-use disclaimer

This repository is not intended for clinical deployment. Results from small development cohorts must not be interpreted as diagnostic performance, and any future clinical claim requires appropriately designed external validation.

---

## Baseline / Fallback Methods

The primary research route is:

```text
progressive block-mask localization
        → coarse-prior-guided LIME refinement
        → clinical-logic-aligned explanation and interaction
```

Mature methods such as ResNet / DenseNet with Grad-CAM++, lung-region constraints, or 3D smoothing may be retained as **comparison baselines or fallback engineering paths**, but they are not treated as the core methodological contribution.

---

## References

1. **AFLoc: Annotation-Free Pathology Localization via Multi-level Semantic Alignment.** *Nature Biomedical Engineering*, 2026. DOI: `10.1038/s41551-025-01574-7`.
2. Yang Z, Zhao L, Wu S, et al. **Lung Lesion Localization of COVID-19 From Chest CT Image: A Novel Weakly Supervised Learning Method.** *IEEE Journal of Biomedical and Health Informatics*, 2021, 25(6): 1864–1872.
3. Selvaraju RR, Cogswell M, Das A, et al. **Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization.** ICCV, 2017.
4. Zhou B, Khosla A, Lapedriza A, et al. **Learning Deep Features for Discriminative Localization.** CVPR, 2016.

---

## Contributing

Issues and pull requests are welcome, especially for:

- DICOM engineering and medical-imaging QC;
- weakly supervised lesion localization;
- occlusion-robust learning;
- explainable AI and LIME/CAM methods;
- patient-level evaluation design;
- clinician-facing explainability and interaction;
- research-oriented web visualization.

Please never include protected health information or identifiable patient data in public contributions.

---

<div align="center">

**EpiLocate · 疫影寻灶**  
*From weak labels to stable, explainable lesion localization.*

</div>
