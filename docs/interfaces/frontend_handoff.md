# 前端开发交接：EpiLocate 研究原型

对接基线：B 分支 `feat/gradio-demo-p0`（`f153b9b`）已有 Gradio 单张 PNG/JPG Mock 测试页和 `/api/v1/jobs/inference` 任务接口。当前本地 `flow-fluidity/` 是独立展示页，`aid_site` 是远端主线项目介绍站；两者都没有真实 CT 分析页面。以下九页是**待开发页面清单**，并非已存在的功能。

先读取 `algorithm_api_contract.md` 和 `algorithm_api_contract.yaml`。所有示例都是 `SYNTHETIC_FIXTURE`。页面统一显示 `source`、模型/协议版本、QA 状态及“研究用途，非临床诊断”。`available|planned|unavailable` 由 `/api/v1/capabilities` 决定；规划中的按钮禁用并说明原因，不填造算法结果。

| 页面 | 用户动作与所需输入 | API 与返回数据 | 加载、失败与当前状态 |
| --- | --- | --- | --- |
| 1 影像上传 | 选择 DICOM 序列或 NIfTI；确认已去标识与授权 | `POST /cases` → `case_id,job_id`；`GET /cases/{id}` → 解析与质量检查 | 上传进度、解析 job 轮询；415/422 显示具体但脱敏的错误。**未实现**；B P0 仅 PNG/JPG Mock |
| 2 CT 切片浏览 | 选择 `case_id`，滚动/点选 `slice_id` | `GET /cases/{id}/slices` → 索引、空间信息；`GET /slices/{id}/preview` → PNG | 先显示骨架屏，再逐切片加载；解码失败只影响该切片。**未实现** |
| 3 分类结果 | 选择切片或患者级汇总、Baseline | `POST /predictions` → job；`GET /jobs/{id}/result` → `Prediction` | 显示 `unit=slice|patient`、正类概率与预测类别置信度；503 模型不可用。**真实推理未接入**；Mock 必须大字标明 |
| 4 遮挡分析 | 选切片、16/32/64 尺度 | `POST /jobs/occlusion`、job/result、`/occlusion-results/{id}/positions`、`/assets/{id}` | 显示 0–1 进度、已处理切片、ETA 可空；任务失败提供安全重试。`insufficient_positive_response` 是有效结果，隐藏候选区。**服务未实现** |
| 5 三尺度比较 | 在同一 `slice_id` 切换尺度和配对 | result 中 `scale_summaries`、`cross_scale`，三张 224 图和 14×14 比较指标 | 各图独立加载；缺失 pair 显示“不可计算”。不使用红绿合格阈值。**服务未实现** |
| 6 稳定粗定位 | 浏览逐级区域、最终区域 | result 中 `coarse_localization` | 只有 `status=COMPLETED` 才绘图；目前显示“方法未实现”，**无区域** |
| 7 LIME 精细定位 | 选择粗定位先验并查看边界/贡献 | result 中 `lime`；未来提交需 `input_coarse_result_id` | 仅在粗定位有效时启用；当前 `NOT_IMPLEMENTED`，**无解释图** |
| 8 医生修正 | 在单切片区域确认/增删/改边界，填写意见 | `POST /feedback` → 新 `annotation_version` 和事件 | 先保留模型原图层，再单独展示医生修正图层；冲突提示刷新。**未实现**，不能在现有 Series 复核服务写病灶反馈 |
| 9 模型与实验对比 | 查看历史 validation 或选择同一病例切片做 Baseline/Robust 配对 | `GET /experiments/{id}/validation-summary` 或 `POST /comparisons` | 历史结果显著标 `FROZEN_VALIDATION`，在线结果标 `LIVE_CASE`；Robust 未实现时对比按钮禁用 |

## 热力图与 CT 对齐的实现要求

1. `slice_id`、图像版本和 `asset_id` 一致时才允许叠加。固定窗预览与响应图放在同一定位容器，绘制矩形均以预览可见内容区域为准。
2. 后端给出的 `raw_to_algorithm_edge_affine` 只描述原始边界到 224×224 算法空间。浏览器 `object-fit: contain` 产生的左右/上下留白要扣除：`xdisplay=left+x224*displayWidth/224`、`ydisplay=top+y224*displayHeight/224`。
3. 16/32/64 是遮挡块大小，不是热力图尺寸；14×14 仅用于跨尺度比较，原始 CT 可能是 512×512 等尺寸。前端把 224 图插值放大仅是显示效果，不能回写科研统计。
4. `value_min/max` 决定颜色图例；不能对每张图悄悄使用不同归一化而又并排比较。候选区域标“模型遮挡响应假设”，不写“病灶”。无效响应时不画空白轮廓或伪区域。
5. 不跨轴位切片合成一张患者级二维热力图。像素间距或方向缺失时不显示毫米标尺；医生手绘坐标必须带 `coordinate_space` 和切片 ID 回传。

## 长任务和前端状态

任务提交需稳定 `Idempotency-Key`；断网后先用保存的 `job_id` 轮询，不能重复提交。`PENDING/RUNNING` 显示处理进度，`COMPLETED` 读取结果，`FAILED/CANCELLED` 显示统一错误码。ETA `null` 时显示“暂无法估计”。取消按钮只在后端声明可取消时展示。页面刷新后恢复 job 查询，不假设重启后的任务可以继续。

## B 同事分支的具体修改点

1. 保留现有 P0 Mock UI/API 与 `contract_version=0.1`，在真实 CT 页面使用新的 v1 模型。Mock 结果继续醒目标识，禁止接入正式历史统计卡片。
2. `contracts.py` 增加 `positive_probability`、`predicted_class_confidence`、`unit`、`source`、`capability state`、`candidate_status`、`HeatmapLayer`/空间元数据；弃用没有冻结定义的 `stability_score`。
3. `OcclusionStage.image_path`、`mask_path` 和 `overlay_path` 改成授权资产 ID。Gradio 当前下载 `result.json` 的机制仅用于本地调试；所有未来影像资产都走对象授权 API。
4. UI 的 Occlusion/Coarse/LIME tabs 目前只是“未接入”，可保留，但不得用 Mock 数值填充。新增切片浏览和长期任务进度组件时统一读取 API 状态。
5. 不在 `flow-fluidity` 宣传页里复制算法逻辑；将来的 React 页面若使用它，只消费相同 API 契约。

验收时用 `fixtures/` 的 synthetic 例子先检查字段、坐标和禁用状态；再在受控开发环境接真实服务。前端验收不要求解除 formal test seal。
