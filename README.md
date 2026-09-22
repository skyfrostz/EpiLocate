# EpiLocate - 疫影寻灶

医学影像 AI 项目的 Baseline 工作区。当前已完成 DICOM 整理、患者级划分、统一预处理、抽样 QC、Dataset/DataLoader、预训练 ResNet-18 初始化、tiny overfit、1-epoch smoke 和 10-epoch Baseline。

当前已执行 Baseline Plan 的 Step 1–12。Step 4 人工 QC 已由用户确认通过，补充元数据审计无阻断问题。项目根为本 README 所在的 `infectious-ct-ai`；所有脚本以自身位置定位数据，不依赖当前终端路径。

## 环境

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 安全整理 DICOM

先执行只读扫描：

```bash
python scripts/organize_dicoms.py
```

确认汇总正常后，再显式执行移动：

```bash
python scripts/organize_dicoms.py --execute
```

脚本只处理项目根目录直属的 `*.dcm` 文件，不修改 DICOM 内容，不覆盖已存在的目标文件。整理后的每张切片会写入本地 `data/data_manifest.csv`。

## 检查与显示

```bash
python scripts/inspect_dicoms.py
python scripts/test_dicom.py
```

数据标签暂定为：`MIDRC-RICORD-1A = 1`、`MIDRC-RICORD-1B = 0`、`UNKNOWN` 留空。后续数据集划分必须按患者进行，不能随机拆分切片。

## Baseline Step 1–4

在项目根目录激活环境后依次运行：

```bash
python scripts/summarize_series.py --config configs/baseline.yaml
python scripts/create_splits.py --config configs/baseline.yaml
python scripts/check_preprocessing.py --config configs/baseline.yaml
```

Step 1 会检查 manifest 的实际字段、全部 Header、标签、文件对应关系，并记录源文件 SHA-256。输出 `outputs/data/series_summary.csv`（全部序列及排除原因）、`selected_manifest.csv` 和 `audit_summary.json`。

当前原始数据包含 10 位患者、6,688 张 DICOM、37 个序列。1A 除常规轴位外，还含 Scout、冠状/矢状重建和骨算法序列，不能直接将这些混在同一 Baseline 中。配置显式采用对两个类别相同的规则：`ORIGINAL/PRIMARY/AXIAL`、轴位空间方向、`STANDARD` 重建核、1.25 mm 层厚。当前每位患者恰好有一个候选，共 10 个序列、2,346 张（1A 1,208 张；1B 1,138 张）。若任一患者出现零个或多个候选，脚本立即停止，须重新审查规则。原始 manifest 和全部影像保留，未删除任何被排除的序列。

Step 2 使用 seed 42，每类患者按 3/1/1 分配到 train/val/test。`data/splits/patient_split.csv` 是患者分配表，`all_slice_assignments.csv` 为全部原始切片记录患者归属；`train.csv`、`val.csv`、`test.csv` 仅包含选中序列。当前分别为 6/2/2 位患者、1,422/507/417 张切片，患者交集为 0。重复运行结果确定；如已有不同划分，脚本停止而不覆盖。

完整数据到位后的比例模式：

```bash
python scripts/create_splits.py --mode ratios --ratios 0.70 0.15 0.15
```

比例模式仍按患者标签分层，使用最大余数法分配整数人数；样本太少导致某类在某一 split 中无人时会报错。变更数据或划分前需先归档旧划分和完整性基线，避免静默替换。

Step 3 的唯一入口为 `src.preprocessing.preprocess_dicom(path, config)`：像素乘 RescaleSlope 加 RescaleIntercept → HU → 肺窗（C=-600/W=1500，范围 -1350 至 150）→ [0,1] → 双线性抗锯齿缩放 224×224 → 复制三通道 → ImageNet 标准化。缺失 slope/intercept 会明确警告并回退为 1/0，非法数值或非二维图像会报错。mean/std 直接读取本机 `ResNet18_Weights.DEFAULT.transforms()`，当前分别为 `[0.485,0.456,0.406]` 和 `[0.229,0.224,0.225]`；不调用其默认 resize/center-crop，也不下载或加载模型权重。

Step 4 覆盖全部 10 位患者，按各序列 `ImagePositionPatient` 的 z 坐标排序，在 30%/50%/70% 位置取样，共 30 张。生成：

- `outputs/qc/preprocessing_grid.png`：每位患者的中间样本总览，左侧 1A、右侧 1B。
- `outputs/qc/<PatientID>.png`：该患者的三张切片，每行依次为原始灰度、HU 肺窗、224×224。
- `outputs/qc/preprocessing_metrics.csv`：逐样本 HU/window/归一化/张量范围、尺寸、警告和失败原因。
- `outputs/qc/qc_summary.json`：样本 QC 和本轮全部原始文件哈希复核。

QC 图的最终列显示 ImageNet 标准化前的 [0,1] 图像，实际模型输入张量已做 ImageNet 标准化。黑/白饱和比例 ≥99%、归一化标准差 <0.001、物理宽高比偏离正方形 >10% 等只作工程报警；这不是医学判定。当前 30 张读取错误和自动标记均为 0，6,688 个源文件哈希均一致。生成时自动报告状态为 `AWAITING_VISUAL_REVIEW`；之后用户已确认通过，记录于 `outputs/qc/human_review.md`。此抽样结果不等于全量像素或诊断质量验收。

验证预处理数学、fallback、拒绝 Scout/多帧和患者分层：

```bash
python -m unittest discover -s tests -v
```

## 补充元数据审计与 Step 5–7

```bash
python scripts/check_dicom_metadata.py --config configs/baseline.yaml
python scripts/test_dataloader.py --config configs/baseline.yaml
python scripts/test_model.py --config configs/baseline.yaml
```

元数据审计仅读取全部原始 DICOM Header，并更新 `outputs/data/series_summary.csv`。表中以 `series_uid`、`collection`、`patient_id`、`modality`、`series_description`、`slice_count`、`rows`、`columns`、`photometric_interpretation` 对应 DICOM 的 SeriesInstanceUID、Collection、PatientID、Modality、SeriesDescription、切片数、Rows、Columns、PhotometricInterpretation；还包含 InstanceNumber 缺失/重复/跳号和 `audit_flags`。旧的选中状态与筛选原因保留，不执行新的筛选、搬动或像素修改。

完整分布保存于 `outputs/data/metadata_audit.json`，逐切片字段为 `metadata_per_slice.csv`，读取异常为 `metadata_read_issues.csv`。当前检查结果：

- 6,688 张均为 MONOCHROME2；MONOCHROME1 为 0。
- RescaleSlope 全部为 1，RescaleIntercept 全部为 -1024；缺失、非有限或非法值均为 0。
- 37 个序列均无 InstanceNumber 重复、缺失、非法值或跳号。
- 标记 5 个 Scout 和 17 个非轴位重建序列；其中一个 Scout 存在尺寸变化。这些全部属于之前已未选入 Baseline 的序列，本轮没有新增过滤。
- 原始影像哈希全部一致，完整 manifest、selected manifest 与患者划分文件内容未改变。

`src/dataset.py` 中的 `RICORDDataset(csv_path, config)` 在初始化时验证 collection/label 一致性，所有图像只调用 `src.preprocessing.preprocess_dicom`。返回 float32 `[3,224,224]` 和标量 `torch.long` 标签（0=1B、1=1A）；读取失败、错误标签、NaN/Inf 都会报错而不跳过。

DataLoader smoke test 分别验证 train/val/test 的第一个样本和 batch_size=8 的一个 batch，并断言患者集合互斥。三组图像均为 `[8,3,224,224]`，标签 `[8]`，无 NaN/Inf。完整 min/max/mean/std 记录在 `outputs/baseline/dataloader_smoke.json`。这是样本和 batch 检查，不是全数据 epoch。

`src/model.py` 的 `build_model(config)` 使用 torchvision `resnet18(weights=ResNet18_Weights.DEFAULT)`，替换 `fc=nn.Linear(512,2)`。首用从 torchvision 官方地址下载约 44.7 MiB 权重至 torch 用户缓存，不放入原始影像目录。检查脚本核对全部 100 个骨干状态张量与官方权重一致、权重 SHA-256 前缀正确，然后以 CPU 零张量 `[1,3,224,224]` 做结构前向测试，输出 `[1,2]` 且 finite。结果保存为 `outputs/baseline/model_initialization.json`。

Step 7 当时只验证了结构；后续训练结果和严格的开发用途限制记录如下。

## Step 7.5–12：Baseline 训练

本节所有结果均为 **SMOKE / DEVELOPMENT ONLY**。当前只有 10 位患者，任何 Accuracy/AUC 都不能作为正式科研结果。

```bash
python scripts/create_baseline_eligibility.py --config configs/baseline.yaml
python scripts/run_tiny_overfit.py --config configs/baseline.yaml
python train.py --config configs/baseline.yaml --experiment smoke
python train.py --config configs/baseline.yaml --experiment baseline
```

`outputs/data/baseline_eligibility.csv` 为全部 6,688 张切片保留原始 manifest 字段，并增加 `baseline_eligible`、`eligibility_reason` 和固定 `split`。它不会改写患者划分。当前 eligible 为 10 位患者、10 个序列、2,346 张切片；1A/1B 分别为 1,208/1,138 张。排除的 27 个序列均保留原位，包括 5 个 Scout、17 个非轴位重建和 5 个不符合当前 STANDARD/1.25 mm 统一选序规则的轴位骨算法序列。患者泄漏为 0。

Tiny overfit 固定抽取 32 张平衡 train 切片，预先门槛为 accuracy >=95%、train-set eval loss <=0.20、loss 降幅 >=50%。本次第 7 epoch 达到 100% accuracy，loss 从 1.160915 降到 0.034136。曲线与日志位于 `outputs/experiments/EXP000_tiny_overfit/`。

1-epoch smoke 的 loss/logits/probabilities 均为 finite，两种标签存在，checkpoint 保存、重新加载和 reload 后 inference 均通过。产物位于 `outputs/experiments/EXP001_smoke/`。

10-epoch Baseline 使用 ImageNet pretrained ResNet-18、`Linear(512,2)`、CrossEntropyLoss、AdamW、LR=1e-4、seed=42。checkpoint 预先规定只按最低 validation loss 保存，test 不参与选择。best epoch 为 4：train loss 0.029545、validation loss 1.875501；slice-level validation Accuracy=0.287968、ROC-AUC=0.092482、Sensitivity=0、Specificity=0.648889。产物位于 `outputs/experiments/EXP002_resnet18_baseline/`。

该结果显示严重患者级过拟合和很差的跨患者泛化，不是一个可用于医学结论的性能结果。Validation 只有 2 位患者，患者级指标尤其不稳定。继续扩充患者数据并保持患者级划分之前，不应围绕本轮分数做模型优劣判断。

## 数据安全

原始 DICOM、生成的患者清单、虚拟环境、模型权重和运行输出已从 Git 中排除。不要将医学影像或含患者级标识符的数据提交到远程仓库。

患者划分 CSV 和 QC 图也只在本地保存，由 `.gitignore` 排除。

## IDC 全量下载

全量数据单独保存于 `data/full_raw/`，不会覆盖开发集 `data/raw/`。当前 IDC v22 index 使用的官方 collection_id 是 `midrc_ricord_1a` 和 `midrc_ricord_1b`（对应显示名称 MIDRC-RICORD-1A/1B）。下载日志位于 `logs/download_ricord_1a.log` 和 `logs/download_ricord_1b.log`，Header 审计报告位于 `outputs/data/full_download_report.json`。

本次全量目录包含 53,076 个 DICOM：1A 为 31,856 个、110 位患者、120 个 Study、229 个 Series；1B 为 21,220 个、117 位患者、120 个 Study、120 个 Series。全部使用 `stop_before_pixels=True` 完成 Header 检查，读取错误为 0，跨 Collection PatientID 冲突为 0。旧开发集的 6,688 个 SOP UID 是完整 Collection 的预期子集，因 `data/raw` 与 `data/full_raw` 分开保留而存在内容重合，不应删除或合并。
