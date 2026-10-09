# 版本化算法与空间映射契约

源码：`research/next-hospital-20261014/epi_next/hospital_contract.py`、`hospital_runtime.py`、`hospital_release.py`、接管的 `volume_io.py`。
不改变 EPI-NEXT-1、Backend v2、Result 2.0、Session Gateway、Worker、FrozenBaseline、历史 A/B/C、GT-v1 或冻结研究证据。

## 输入 `EPI-NEXT-HOSPITAL-INPUT-1`

| 字段 | 含义 |
| --- | --- |
| run_id / source_git_sha / source | 独立 EPI-NEXT run、完整受测提交、SYNTHETIC 或 LIVE_CASE |
| case_id / study_uid / series_uid | Case、Study、Series 精确关联，真实标识仅存获准本地目录 |
| task | definition_id、definition_sha256、固定 target_class 和 target_label；collection proxy 不作病灶/临床标签 |
| model_id / model_version / model_sha256 | 实际交付模型身份与 SHA；encoder+head 必须由上游发布整体模型绑定 |
| algorithm_id / algorithm_version | E1、E2、F0、F1 与精确注册版本；历史算法另走原 handler |
| algorithm_config / algorithm_config_sha256 | 参数及规范 JSON 字节 SHA，不允许同模型下换参数复用验收 |
| preprocessing_version / preprocessing_sha256 | 预处理身份，不从历史 FrozenBaseline 改推新 CT-FM 预处理 |
| input_manifest_sha256 / access_approval_sha256 | 正式上游数据交付关联；下游不得自填 proposal SHA 作为医院许可 |
| model_input_dtype / model_input_channels | float32/float64、通道数；输入和布尔支持域的最低字节预算 |
| spatial | native/model ZYX shape、原始 SOP 及文件 SHA、native→LPS affine、model→native affine、operations |
| resource_budget | device、最大模型调用数、输入 voxel/bytes、秒数、BETWEEN_FORWARDS |

真实入口目前显式 BLOCKED_BY_DATA_HANDOFF；正式 DATA 空间 ledger、版本化模型/预处理和真正运行适配器到达后，按总控精确文件清单实现消费。**该阻断不能靠填充假 metadata 绕过。**

## 输出 `EPI-NEXT-HOSPITAL-OUTPUT-1`

保存请求 SHA、原始执行状态及原因、SUCCESS / NO_RELIABLE_RESPONSE / PARTIAL_BUDGET / FAILED / BLOCKED / NOT RUN、全部 logits、原始 argmax 与未校准 softmax 数值、候选和响应、空间坐标、调用数、运行时间和产物相对路径/SHA。
完整请求、原始结果、统一结果与资产存入不可覆盖 run 目录；最终 `receipt.json` 给出所有文件 SHA（避免结果自身 SHA 循环依赖）。

| 算法 | 注册版本 | 证据/响应数值 |
| --- | --- | --- |
| E1 | EPI-NEXT-E1-fixed-target-margin-v1 | INPUT_OCCLUSION；signed_margin_delta、target_probability_delta |
| E2 | EPI-NEXT-E2-HSPI-independent-projected-Adam-v1 | OPTIMIZED_INPUT_MASK；similarity、sparsity、peak_gap；全 logits 一致性，不改成目标 margin |
| F0 | EPI-NEXT-F0-signed-CAM-v1 | CAM_CONTRIBUTION；signed_contribution |
| F1 | EPI-NEXT-F1-residual-input-refreshed-coarse-v2 | INPUT_OCCLUSION；signed_margin_delta、target_probability_delta；残余 baseline/粗图刷新 |
| 专家 GT | 独立上游参考，不进入模型结果 | EXPERT_REFERENCE；保留 GT 版本、覆盖与临床裁定状态 |

候选需真实计数的有效 logits、数值响应和可重新计算的 LPS corners/SOP 关联。无可靠响应不能造候选，几何无效即使有真实 logits 也禁止候选。保留 raw_result 用于追溯，不将部分诊断结果当可展示候选。

## 空间

数组为 ZYX，索引是零基像素中心；原始 DICOM 坐标为 LPS mm。半开整数 bounds 转成像素边缘 `lo-0.5` 至 `hi-0.5`。
依次重建 crop offset、resize half_pixel_align_corners_false、resample first_center_preserved，再与 native affine 相乘。保留八个有方向的 LPS corners，轴对齐 bbox 仅摘要；相邻切片只接触边缘不算候选 SOP。
`spatial_from_volume` 消费既有 reader ledger 并校验输出 affine、shape、source SOP/hash；不定义 GT、选择病例或发布新空间资产。

矩阵自洽状态为 MATHEMATICAL_ONLY。医院准入另外要求原始真实 CT 的左右、切片顺序、世界坐标、crop、resize、resampling 六项 SHA 固定检查证据。未执行操作也须核验实际流水线确实未使用，不允许空 N/A。
倾斜/不均匀间距、增强多帧、任意 warp/pad 和未声明插值均拒绝；当前不是通用医学配准或经过官方验证的 CT-FM 预处理。
volume loader 当前 `EPI-NEXT-CT-ACCESS-1` 仅是生成 DICOM 的候选读接口，**与 DATA 正式 EPI_NEXT_APPROVED_THREE_CASE_ALLOWLIST_V2 不是同一 schema**；不得另建批准文件转换来绕过正式 handoff。兼容消费需在 DATA 正式空间资产交付时按其规范适配。

## 任务与设备安全

固定共享设备锁 `~/.codex/epi-next-device-queue/{cpu,mps}.lock` 覆盖整个计算与保存，忙时 BLOCKED。锁仅约束使用 `device_lease` 的运行器；不能冒称所有其他 Codex/历史脚本已自动纳入。MPS 仅 ENCODER 当前调度资格，INTEGRATION CPU；远程 RTX3090 与付费计算暂停。
每个 forward 前适配器必须调用 `before_forward`，失败调用也计数；截止只能 BETWEEN_FORWARDS，进行中的 forward 可超过预算。最低输入字节检查不是峰 RSS 保证。
全球 run intent 在模型运行前不可覆盖创建，崩溃后保留；未知事务先对账，不因无 PID 就重跑。同 ID 换输出根也禁止重算。未运行/阻断请求不创建虚假成功收据。
注册函数必须处理资源检查、真实输入字节核验与输入防修改，返回 `(raw_result, dict[str,bytes])`；上游未正式交付时不构造假运行器。任何终止身份不明进程的操作均不在实现中。
