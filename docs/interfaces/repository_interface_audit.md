# EpiLocate 仓库与接口现状审查

审查时间：2026-09-26。此审查以本地工作区、`origin/main` 的 `14c114a` 和 B 同事分支 `origin/feat/gradio-demo-p0` 的 `f153b9b` 为依据。远端引用已读取，未切换、合并或改写任何分支。

## 仓库状态与协作边界

- 当前本地 `main=65d1861`，落后 `origin/main=14c114a` 一个提交。工作区已有多处未提交修改，以及冻结协议、正式实验、`flow-fluidity/` 和本次资料包等未跟踪文件。任何常规 `pull`、`merge`、清理或覆盖均不适合在此工作区直接执行。
- B 分支 `f153b9b` 的共同祖先是 `0c2060f`。它只新增 `gradio_service/`，创建时间早于当前主线的复核服务。直接拿 `main..B` 的删除清单当成 B 有意删除复核服务会误判；集成时应以新增的 17 个 `gradio_service/` 文件为范围，从最新主线创建独立集成工作树，保留 `epilocate_review_server/`、`aid_site/` 和本地未提交工作。
- `flow-fluidity/src/main.tsx` 是未跟踪的展示型 React 页面，只有图片切换和禁用的“在线面板建设中”按钮；没有病例、算法或后端调用。不能把它列作已实现的临床/研究前端。

## 已检查的运行面

| 位置 | 当前实际能力 | 对算法接口的关系 |
| --- | --- | --- |
| `src/preprocessing.py`、`src/model.py`、`src/dataset.py` | DICOM CT 单切片预处理、ResNet-18 构建、manifest 驱动数据集 | 算法核心可复用；`return_stages=True` 含 PatientID、Study/Series UID，服务层必须过滤 |
| `scripts/train_formal_baseline.py`、`scripts/occlusion_runner.py` | 正式 Baseline 训练与冻结验证遮挡计算；后者提供网格、指标、候选响应图栅格化、14×14 投影及汇总函数 | 是离线实验入口，不能直接作为 Web 请求处理器；冻结定义不得改变 |
| `infer.py` | 仅有模块说明，无推理实现 | 不能标记为真实单例推理 API |
| `outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation/` | 28 患者、5,637 切片、5,264,958 masked inferences；161 项产物，独立 QA PASS，`result_freeze.json` FROZEN | 已完成验证统计，可通过只读结果服务展示；不是任意上传病例的在线计算能力 |
| `epilocate_review_server/` | FastAPI/Jinja2/SQLite 人工 Series 复核与授权媒体；`/api/reviews/...` 是人工选片决定 | 与未来医生病灶反馈的语义、表结构和权限均不同；不能复用为算法标注写入端点 |
| B 分支 `gradio_service/` | FastAPI + Gradio，单 PNG/JPG 上传、Mock 分类、SQLite job、JSON 结果；`/api/v1/contract` | 最适合扩展的算法演示服务。Real 模式依赖尚不存在的 `algorithm.inference_pipeline.run_case`，未接真实 checkpoint |
| `origin/main:aid_site/` | 独立的项目展示 FastAPI 站点；`/api/v1/capabilities` 可用，`/images`、`/analysis-tasks`、`/results`、`/doctor-feedback` 返回 `NOT_CONNECTED` | 展示站点保持占位；将来需网关/代理和认证方案，不能把当前占位认作算法服务 |

当前没有发现 NIfTI 解析或将单 DICOM、NIfTI 序列统一成在线 `case_id`/`slice_id` 的模块。没有实时切片预览/空间变换服务、真实模型缓存服务、医生病灶修正存储、Robust/LIME/逐级稳定粗定位实现。

## 真实能力分级

**A 已实现并有正式验证：** 冻结 ResNet-18 checkpoint；统一 DICOM CT 单切片预处理；Stage 1 遮挡响应、候选响应有效性、切片/患者/跨尺度验证汇总；冻结 QA 与 provenance。这里的“可用”指离线算法和既有验证结果，不指 Web 可调用。

**B 算法基础可复用，仍需服务封装：** 对受控单切片进行 Baseline 推理；在同一冻结预处理/模型上做遮挡计算；按需生成单切片候选响应图与三尺度对照；从冻结 validation 汇总读取历史结果。需补充匿名病例 ID、格式和脱敏检查、模型生命周期、只读结果访问、进度、身份和资产 URL。

**C 预留契约：** NIfTI 解析与三维几何、Robust 推理/配对比较、逐级稳定粗定位、LIME 精细化、临床解释、医生病灶反馈和长期任务恢复。`planned` 只表示研究路线；任何具体结果、稳定性评分或病灶边界都不得由占位字段伪造。

## 推荐结构与原因

保留三种不同用途的服务：`epilocate_review_server` 负责已有人工 Series 复核，`aid_site` 负责项目展示和未来受控入口，B 的 `gradio_service` 负责本地算法调试与轻量 REST。新增薄的算法 Service/Adapter 层，复用 `src/` 和冻结遮挡函数；B 的 FastAPI 调用 adapter，Gradio 调同一个 API/Service。不要让 React、Gradio 或展示站点读取 checkpoint，也不要把 CLI runner 复制进前端。

对外契约按 `algorithm_api_contract.yaml` 的算法服务 `/api/v1` 设计。B 已有的 `/api/v1/jobs/inference` 保持 P0 Mock 向后兼容；真实 DICOM/影像流程使用新的 `/cases`、`/predictions`、`/jobs/occlusion` 等资源。`aid_site` 的同名 `/api/v1` 在另一服务/主机，当前不代理真实影像；接入时再确定网关路径与身份委托。

## 需要正面处理的兼容差异

1. B 的 `PredictionResult.probability` 是“预测类别概率”，未来响应必须另有 `positive_probability` 与 `predicted_class_confidence`，并声明 `unit=slice|patient`。
2. B 的 `OcclusionResult.stability_score` 没有冻结定义；不可把它作为正式 Stage 1 结果。候选区域要返回 `valid` 或 `insufficient_positive_response`，无效时 region/overlay 为 `null`。
3. B 的 `OcclusionStage.image_path`、`LocalizationResult.mask_path/overlay_path` 应改为受权 `asset_id`/URL，不向前端暴露主机路径。
4. B 的 job 状态 `queued/running/success/failed` 尚无取消、幂等、切片进度或恢复；API v1 适配层需要清晰映射 `PENDING/RUNNING/COMPLETED/FAILED/CANCELLED`。
5. B 的上传仅支持 PNG/JPG Mock；DICOM/NIfTI、去标识与空间坐标检查属于新实现。绝不能把普通图片 Mock 概率当 CT 正式结果。
6. B 服务缺少可公开部署的认证/授权边界，暂限本机调试。展示站点已有登录/CSRF，但业务路由当前 503；接线前要设计对象授权、文件生命周期和同源访问。
