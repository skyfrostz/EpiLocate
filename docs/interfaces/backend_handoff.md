# 后端开发交接：算法服务与存储边界

以 B 分支 `gradio_service/gradio_debug/` 的 FastAPI、Gradio、`InferenceAdapter`、`JobManager` 和 SQLite 存储为最小集成点。`epilocate_review_server/` 的人工 Series 复核数据库保持独立；`aid_site` 仅负责项目展示及将来受控的 API 入口。OpenAPI 目标契约为 `algorithm_api_contract.yaml`，字段语义见 `algorithm_api_contract.md`。

## 现有入口与接线顺序

- B 分支代码已包含 P0：`GET /api/health`、`GET /api/v1/contract`、`POST /api/v1/jobs/inference`、`GET /api/v1/jobs/{job_id}`、`GET /api/v1/jobs/{job_id}/result`，只支持单 PNG/JPG Mock。`APP_MODE=real` 会查找缺失的 `algorithm.inference_pipeline.run_case`；未接入时健康状态 degraded，提交返回 503。本次只运行了分支的契约、Mock 推理和 job 单元测试，未启动 HTTP/Gradio 服务。
- P0 真算法封装：新建独立 `algorithm` service/adapter，先实现受控 DICOM 单切片的 checkpoint 严格加载与缓存、预处理、分类；结果包含模型哈希、预处理版本、`slice` 单位和两种不同的概率。进程启动或第一次请求校验 checkpoint 哈希及 epoch，禁止下载额外模型权重或重训。
- P0 遮挡封装：复用冻结 runner 的网格、正类概率和 `candidate_response` 定义；将 CLI 依赖从核心计算中隔离，但不改冻结代码/产物。先对 synthetic DICOM/已授权开发图像验证，正式 validation 统计走独立只读读取器。
- P1/P2：Robust、逐级粗定位、LIME、医生反馈均等对应研究方法和治理流程通过后接入；当前统一返回 `NOT_IMPLEMENTED`/能力 `planned`。

## 数据模型与存储

| 对象 | 必要字段 | 约束 |
| --- | --- | --- |
| `case` | `case_id,source,input_kind,preprocessing_status,created_at,quality_checks` | ID 随机；不含 PatientID/UID/绝对路径；只允许经授权的去标识影像 |
| `slice` | `slice_id,case_id,index,raw_width,raw_height,geometry,preview_asset_id` | 唯一 `(case_id,index)`；DICOM tag 映射仅留受控内部元数据，API 严格白名单 |
| `prediction` | `prediction_id,case_id,slice_id,unit,model_id,model_version,preprocessing_version,positive_probability,predicted_class_confidence,source` | `unit=patient` 的汇总独立记录，不覆盖切片预测；模型原始输出不可变 |
| `job` | `job_id,request_hash,idempotency_key,job_type,case_id,status,progress,processed_slices,total_slices,elapsed/ETA,error` | 同一用户+键+请求/版本唯一；原子状态转换；队列容量控制 |
| `analysis_result` | `result_id,job_id,protocol_id,scale_summaries,cross_scale,layer IDs,provenance,qa_status` | 只读已冻结 validation 与在线病例分开保存；无效候选的区域/layer 为 null |
| `asset` | `asset_id,owner_case_id,kind,mime,coordinate_space,checksum,storage_key` | API 只给资产 ID；读取要验对象授权，存储键不出响应 |
| `feedback_event` | `event_id,annotation_id,annotation_version,prediction_id,operation_type,original/corrected_region,reviewer_id,timestamp` | 仅追加版本；模型原始结果、医生修正、临床真值三套来源分离；默认不用于训练 |

目前 B 的 `Storage` 使用 SQLite `jobs` 表和本地 `storage/uploads`、`storage/results`；可扩展，但需要真正的 schema migration、文件保留期限、原子结果写入和对象授权。不能把正式 `outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation/` 设置为可写服务目录。日志只记录匿名 case/job ID，不记录原文件名、病人信息、原始路径或 DICOM metadata。

## 模型、空间与结果适配

`src/preprocessing.preprocess_dicom` 可复用 DICOM HU 转换、窗宽窗位、224 resize 和 ImageNet normalization；其 `return_stages=True` 的 `metadata` 包含 PatientID 和 UID，API 序列化必须采用明确白名单，不可直接 `__dict__` 导出。NIfTI 读取、轴向选择、仿射矩阵和物理方向目前缺失，应作为独立模块测试后开放能力。

用 `src.model.build_model` 构建模型，但避免在线服务首次启动自动下载 ImageNet 权重：从冻结 checkpoint 严格加载已登记参数，缓存到进程，`eval()` + `torch.inference_mode()`。每个结果记录 checkpoint SHA-256、协议/config 哈希、算法代码版本。MPS 不可用时返回 `MPS_UNAVAILABLE` 或有明示的经确认 CPU fallback；不能静默改变运行条件又省略 provenance。

遮挡 API 返回 224 坐标下的每位置 `x,y,b,p0,pg,flip,q0-qg,max(q0-qg,0)`；详细 934 位置分页，摘要一次返回。栅格化用冻结 `rasterize_block_scores`，14×14 比较用冻结 `project_area_average`，不能从前端插值图反推统计。像素边界仿射见契约；DICOM 方向和间距缺失用 `null`，不猜测。

## Job 与错误

B P0 当前单线程执行，状态 `queued/running/success/failed`，重启时将未完成 job 标记 failed，`progress` 是固定 25/100，不等于真实切片进度。新 API 增加状态转换器与实际 `processed_slices/total_slices`。取消、恢复、重复请求要分别设计：取消只对可安全中断的在线 job；恢复要求与输入/模型/协议哈希匹配的持久 checkpoint，目前不支持；重复请求由持久的 `Idempotency-Key` 索引返回同一 job。Web 请求断开不影响后台任务，也不影响正式冻结目录。

统一错误结构和 HTTP 对应见 OpenAPI。`insufficient_positive_response` 是 `COMPLETED` 结果中的 `candidate_status`，不能归类为推理失败。内部异常写脱敏日志，对外不给 traceback、物理路径、DICOM tag 或环境变量。

## 服务与权限边界

B 服务目前适合 `127.0.0.1` 本机开发，不具备接收实际医疗数据的认证/授权体系。未来若从 `aid_site` 进入，展示站点的会话/CSRF 不能直接等同算法服务的对象授权；需要明确代理身份、同源策略、上传大小、脱敏审核和资源 ACL。医生反馈写入要求单独角色与审计，不能沿用 Series 复核的 `/api/reviews` 表。

## 最小集成验收

1. 在最新主线的独立工作树只集成 B 分支新增的 `gradio_service/`，保留主线 `epilocate_review_server/` 与 `aid_site/`。B 分支从 `0c2060f` 分出，不要用整个旧树覆盖现主线。
2. B P0 的既有 Mock 上传/job/result 行为保持可运行，并醒目标 `MOCK RESULT`；真算法不可用时返回 503，不降级成 Mock 假结果。
3. 用 synthetic fixture 检验 schema、候选响应公式、无效候选不产生区域、224/14 坐标与 job 幂等。真实算法接入再做受控 DICOM 验收；不使用 formal test。
4. 冻结 validation 的 161 项产物、checkpoint 和协议/config 字节哈希不变；新增在线文件只写独立根目录。后端交付启动说明、API 示例、迁移文件、测试记录和已知限制。
