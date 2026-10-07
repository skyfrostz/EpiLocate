# EpiLocate 算法服务接口契约 v1 设计稿

本文件与同目录的 `algorithm_api_contract.yaml` 一起交给前后端开发。下文保留接口设计背景和冻结算法语义；**当前实际可用范围以 `p0_real_integration.md` 和 `p0_verification_record.md` 为准**。集成工作树已接入单切片 DICOM Baseline/Stage 1；多切片、NIfTI、Robust、粗定位、LIME 和医生反馈仍未实现。`aid_site` 的同名 `/api/v1` 是另一个服务，影像相关路由仍是占位。

## 1. 服务、来源和能力

算法服务由 B 的 FastAPI + Gradio P0 服务演进。浏览器只调用 API 或 Gradio，不读取 `src/`、checkpoint、Parquet 和本机路径。数据来源必须显式使用 `LIVE_CASE`（受控上传的真实在线推理）、`FROZEN_VALIDATION`（冻结 validation 统计）或 `SYNTHETIC_FIXTURE`（接口样例）；Mock 结果不得使用 `LIVE_CASE`。

`GET /api/v1/capabilities` 按模块返回 `available|planned|unavailable` 和证据。`available` 意味着**该部署下的服务实际可调用**。离线算法已完成但还没接入 Web 时，服务仍返回 `planned`，并在 `evidence` 注明“offline validated”。当前 B P0 的 `mock_prediction` 可标 `available`，真实 CT 分类、实时遮挡、NIfTI、Robust、粗定位、LIME、医生反馈均不可标 `available`。模型文件或 MPS 缺失可将真实推理标为 `unavailable`。

## 2. 端点与状态

| 方法与路径 | 用途 | 当前状态 |
| --- | --- | --- |
| `GET /api/v1/capabilities` | 能力查询 | 设计，B 服务尚无此端点；展示站点有不同的占位版 |
| `POST /api/v1/cases` | DICOM/NIfTI 上传、创建解析任务 | 设计 |
| `GET /api/v1/cases/{case_id}`、`/slices` | 病例状态、质量检查、切片索引及几何 | 设计 |
| `GET /api/v1/slices/{slice_id}/preview` | 授权 PNG 预览 | 设计 |
| `POST /api/v1/predictions` | Baseline 切片或患者汇总预测 | 设计 |
| `POST /api/v1/jobs/occlusion` | 单切片三尺度或指定尺度遮挡任务 | 设计 |
| `GET /api/v1/jobs/{job_id}`、`/result` | Job 状态和结果 | B P0 有同路径的 Mock 版；v1 结构为扩展设计 |
| `POST /api/v1/jobs/{job_id}/cancel` | 安全取消 | 设计 |
| `GET /api/v1/occlusion-results/{result_id}/positions` | 分页取得遮挡位置和概率 | 设计 |
| `GET /api/v1/assets/{asset_id}` | 授权获取响应图与预览 | 设计 |
| `GET /api/v1/experiments/{experiment_id}/validation-summary` | 冻结历史统计 | 设计，只读 |
| `POST /api/v1/comparisons` | Baseline/Robust 配对比较 | P1 预留 |
| `POST /api/v1/feedback` | 医生修正事件 | P2 预留 |

现有 B P0 `/api/v1/jobs/inference` 保留为 `contract_version=0.1` 的 Mock 兼容入口；新路径不改变旧响应。正式接入后可增加 v1 转换器，但不能静默把 Mock 响应升级为真实结果。

## 3. 影像、标识和空间坐标

上传使用 multipart `input_kind=dicom_series|nifti` 和 `files[]`；服务生成不含患者信息的 `case_id` 和 `slice_id`。输入路径、DICOM `PatientID`、Study/Series/SOP UID 和原始文件名不进入 API。上传前需验证来源授权及去标识，服务端也要重新检查并限制大小、序列数量、解压膨胀、格式与像素解码。当前 `src/preprocessing.py` 仅支持 DICOM 单切片；NIfTI 的仿射矩阵、轴向重排和物理空间映射需要单独实现与验收。

`ImageGeometry` 区分原始像素边界坐标、算法 224×224 像素边界坐标和显示容器坐标。原点均为图像左上角，x 向右、y 向下。对宽 W、高 H 的原图，原始边界点映射到算法空间为 `x224=224*xraw/W`、`y224=224*yraw/H`；因此 `raw_to_algorithm_edge_affine=[224/W,0,0, 0,224/H,0, 0,0,1]`。图像像素中心采样由现有抗锯齿双线性 resize 实现，不可用此边界仿射替代真正的预处理。

前端先从预览实际绘制矩形获得 `left,top,displayWidth,displayHeight`，再把算法坐标映射为 `xdisplay=left+x224*displayWidth/224`、`ydisplay=top+y224*displayHeight/224`。若图片用 `object-fit: contain`，必须扣除留白；切勿按整个容器缩放。响应图与 CT 预览必须共用同一变换、同一裁切和同一切片 ID。视觉插值可用双线性并在 UI 标记“仅显示插值”；科研统计仍使用原始 224×224 响应图及冻结的 14×14 面积平均比较网格。`pixel_spacing_mm`、方向和位置缺失时为 `null`，不填造数值；仅有正确的几何和 NIfTI 仿射后才显示毫米测量。

## 4. 分类与遮挡语义

`Prediction.unit=slice` 时必须有 `slice_id`；`unit=patient` 时 `slice_id=null` 且 `aggregation=mean_slice_probability`。`positive_probability` 始终是正类概率；`predicted_class_confidence` 是模型所预测类别的概率，二者在负类时不同。固定阈值 `0.5`。`model_version` 为 checkpoint 内容哈希或经登记的不可变版本，不是 UI 发布版本。响应必须包含推理状态、耗时、预处理版本及来源。

冻结的 Stage 1 定义：

```text
y0 = 1[p0 >= 0.5]
q0 = probability of y0 before masking
qg = probability of the SAME y0 after masking
decision_confidence_drop = q0 - qg
candidate_response = max(q0 - qg, 0)
```

`p0/pg` 永远表示正类概率；`decision_confidence_drop` 可为负；`candidate_response` 在 `[0,1]`。16/32/64 像素遮挡，步长分别为 8/16/32，填充值为预归一化灰度 0.5；每切片 729/169/36 个位置。每尺度把连续响应图放在 `response_layer`、Top-10% 二值候选区放在 `candidate_layer`、14×14 科研比较网格放在 `comparison_grid_layer`。候选响应有效性沿用冻结 `epsilon_num=1e-6`：`max(candidate_response) <= epsilon` 时 `candidate_status=insufficient_positive_response`，`candidate_area_fraction=null`，`candidate_layer=null`。这属于成功计算得到的有效状态，HTTP 不报 500，也不生成虚假区域。Top-10% 只用于有效正响应，保留并列值。

三组跨尺度字段为 Spearman、Top-10% IoU、Dice、归一化中心距离、归一化 L1、Pearson。相关性或候选区域为空时相关字段为 `null`，不可写 0。没有稳定性合格阈值。候选图必须标为“模型遮挡响应假设”，不能标为“真实病灶”。不把不同轴位切片叠成一张患者级二维图。

## 5. 长任务、重试与错误

统一状态为 `PENDING → RUNNING → COMPLETED|FAILED|CANCELLED`。`progress` 为 `[0,1]`，`processed_slices/total_slices` 为准确计数；尚不能估计 ETA 时用 `null`。浏览器轮询 job，完成后再取 result。超长遮挡任务应持久化 job 和幂等索引；同一用户、`Idempotency-Key`、标准化请求摘要与模型/协议版本相同时返回原 job；键相同而请求不同返回 `409 IDEMPOTENCY_CONFLICT`。断网重试不得新建重复任务。

取消只在执行器声明 `cancellable=true` 且可安全中断的阶段生效；已完成返回 `409`。B P0 当前不能取消，重启会把 queued/running 标记为 failed；没有恢复。恢复只能在将来拥有已验证的切片级 checkpoint、输入哈希和版本一致性后增加新操作，不能承诺现有 job 可恢复。在线 job 的存储根必须独立于 `outputs/experiments/.../validation/`，网页断开不能写或删除冻结产物。

统一错误对象含 `code,message,retryable,request_id,details`。HTTP 415 `UNSUPPORTED_FORMAT`，422 `IMAGE_PARSE_FAILED|PREPROCESSING_FAILED|INVALID_REQUEST`，503 `MODEL_UNAVAILABLE|MPS_UNAVAILABLE|NOT_CONNECTED`，500 `INFERENCE_FAILED`，404 `RESULT_NOT_FOUND`，409 `IDEMPOTENCY_CONFLICT`，501 `NOT_IMPLEMENTED`，认证失败 401/403。`JOB_CANCELLED` 可体现在 job/result 状态中。对外错误不返回本机路径、DICOM tag、堆栈或患者信息。

## 6. 主要请求和响应示例

下列数值和 ID 全部为 **SYNTHETIC_FIXTURE**，只检验字段形状，绝非真实患者或正式验证结果。

```http
POST /api/v1/predictions
Idempotency-Key: synthetic-prediction-001
Content-Type: application/json

{"case_id":"SYNTHETIC-CASE-001","slice_id":"SYNTHETIC-SLICE-001","unit":"slice","model_id":"baseline_resnet18"}
```

```json
{"job_id":"SYNTHETIC-JOB-001","case_id":"SYNTHETIC-CASE-001","status":"PENDING","status_url":"/api/v1/jobs/SYNTHETIC-JOB-001"}
```

```http
POST /api/v1/jobs/occlusion
Idempotency-Key: synthetic-occlusion-001
Content-Type: application/json

{"case_id":"SYNTHETIC-CASE-001","slice_id":"SYNTHETIC-SLICE-001","model_id":"baseline_resnet18","scales":[16,32,64],"protocol_id":"stage1-occlusion-instability-v1"}
```

完整分类、热力图、跨尺度、未来模块及 provenance 示例见 `fixtures/synthetic_analysis_result.json`。位置分页的单条样例：

```json
{"result_id":"SYNTHETIC-RESULT-001","scale":16,"positions":[{"x":0,"y":0,"block_size":16,"baseline_positive_probability":0.7,"masked_positive_probability":0.55,"prediction_flip":false,"decision_confidence_drop":0.15,"candidate_response":0.15}],"next_cursor":null}
```

候选无效的单尺度样例：

```json
{"block_size":16,"stride":8,"fill":0.5,"baseline_positive_probability":0.7,"median_absolute_probability_change":0.0,"flip_rate":0.0,"candidate_status":"insufficient_positive_response","candidate_area_fraction":null,"response_layer":null,"candidate_layer":null,"comparison_grid_layer":null}
```

历史结果读取示例：`GET /api/v1/experiments/FORMAL-BL-R18-V1/validation-summary`，响应 `source=FROZEN_VALIDATION`、`qa_status=PASS`、`protocol_id=stage1-occlusion-instability-v1`，只返回已冻结聚合指标，不返回测试数据或患者身份。当前该路由仍是设计。

Robust 对照请求示例：

```json
{"case_id":"SYNTHETIC-CASE-001","slice_id":"SYNTHETIC-SLICE-001","model_ids":["baseline_resnet18","robust_resnet18"],"protocol_id":"stage1-occlusion-instability-v1"}
```

在 Robust 未实现前返回 `501 NOT_IMPLEMENTED`，不生成比较数字。`coarse_localization` 和 `lime` 在统一结果里均为 `status=NOT_IMPLEMENTED`、空 `regions`、`final_region=null`、`layer=null`。LIME 未来还需要 `input_coarse_result_id`、有版本的局部解释贡献/边界以及耗时；在方法冻结前不定义搜索或筛选规则。

医生反馈请求示例：

```json
{"case_id":"SYNTHETIC-CASE-001","slice_id":"SYNTHETIC-SLICE-001","prediction_id":"SYNTHETIC-PRED-001","annotation_id":"SYNTHETIC-ANN-001","annotation_version":1,"original_region":null,"corrected_region":null,"operation_type":"CONFIRM","reviewer_id":"SYNTHETIC-REVIEWER-001","feedback_text":"synthetic fixture","timestamp":"2026-09-26T00:00:00Z"}
```

P2 落库时，模型原始结果、医生修正事件和独立获取的临床金标准必须是三套不同来源和版本。追加反馈事件，不更新原始预测行；默认 `training_use=false`。反馈 text 需审查 PHI，审核者 ID 仅内部匿名 ID，跨病例对象授权必须由后端执行。

## 7. 版本与对照的一致性条件

每个结果带 `contract_version`、`protocol_id`、`model_id`、`model_version`、`preprocessing_version`、`source`、`qa_status` 和 provenance。Baseline/Robust 比较的 join key 是 `case_id + slice_id + preprocessing_version + protocol_id + mask-grid version`；同一病例/切片和完全相同的遮挡设置才允许配对。历史 `FROZEN_VALIDATION` 与上传 `LIVE_CASE` 分开展示，不合并为一个样本统计表。历史 validation 有元数据混杂且 test seal 未解除，所有图注需保留研究边界。
