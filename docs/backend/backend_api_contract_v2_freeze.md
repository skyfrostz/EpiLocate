# EpiLocate Backend API Contract v2.0 Freeze

状态：**正式冻结版 v2.0，待最终确认后进入实现**。Backend 基于 FastAPI，公共前缀固定 `/api/v2`；P0 `/api/v1` 和 Gradio 研究入口不在本轮迁移中改写。此文将上游 Backend API Contract v2.0 的无前缀路径放入明确的版本命名空间，并固定 Result 读取、鉴权、幂等和 Job 状态机。Worker 报文见 [worker_protocol_v1_freeze.md](worker_protocol_v1_freeze.md)，持久字段与保留策略见 [database_schema_freeze_v1.md](database_schema_freeze_v1.md)。

## 路由及权限总览

| Router | 方法和路径 | 请求与成功响应 | 权限 |
| --- | --- | --- | --- |
| Case | `POST /cases` | JSON：`patient_id` 可空；`201` 返回新 `case_id/patient_id/status=CREATED` | 登录用户；Case 归本人 |
| Case | `GET /cases` | `cursor`、`limit<=100`；`200` 返回本人 Case 列表与 `next_cursor` | 登录用户；服务端强制 owner 过滤 |
| Case | `GET /cases/{case_id}` | `200` 返回匿名 Case、Study/Series/Slice 树、状态、输入可用期 | Case 所有者 |
| Case | `POST /cases/{case_id}/upload` | multipart：`input_kind=dicom_series`、一个 `file`；`201` 返回匿名 Study/Series/Slice ID、`status=READY` | Case 所有者 |
| Prediction | `POST /predictions` | JSON：`case_id,slice_id,model_id`；`202` 返回 `prediction_id=job_id`、`job_id,status=CREATED` | Case 所有者 |
| Prediction | `GET /predictions/{prediction_id}` | `200` 返回 Job 状态；完成后带分类字段与 `result_id` | Case 所有者 |
| Job | `POST /jobs/occlusion` | JSON：`case_id,slice_id,model_id,protocol_id,scales`；`202` 返回 `job_id,status=CREATED` | Case 所有者 |
| Job | `GET /jobs/{job_id}` | `200` 返回状态、可证实的进度、错误、`result_id` | Case 所有者 |
| Result | `GET /results/{result_id}` | `200` 返回完整预测/遮挡 JSON 与资产描述；不含私有路径 | Case 所有者，Job 已完成 |
| Result | `GET /results/{result_id}/positions` | `scale,cursor,limit<=1000`；`200` 返回遮挡位置分页 | Case 所有者，遮挡结果 |
| Result | `GET /results/{result_id}/assets/{asset_id}` | `200` 流式返回图层；`Cache-Control: private,no-store` | Case 所有者且资产属于该 Result |
| Worker | `POST /workers/register` | 预配节点注册/能力更新 | Worker Bearer |
| Worker | `POST /workers/heartbeat` | 心跳、续租 | Worker Bearer + Attempt 归属 |
| Worker | `POST /workers/jobs/claim` | 原子领取，`200` 或 `204`；请求含 `worker_id,available_capacity,supported_model_versions` | Worker Bearer |
| Worker | `POST /workers/results` | 成功/失败结果回传 | Worker Bearer + 有效租约 |

上表是 v2 第一阶段路由全集。`POST /jobs/{id}/cancel`、患者级预测、NIfTI、Robust 对比、LIME、医生反馈、实验写入与冻结 validation 展示均不在 v2 第一阶段路由中；不能返回假结果或宣称 capability 可用。P0 的同名/近似 `/api/v1` 路由维持原有版本契约。

## Case API

`POST /cases` 可带同一所有者的已有 `patient_id`，或传 `null` 由服务端生成新匿名 Patient。不能按匿名 Patient ID 查询其他用户。Case、Patient 的公共 ID 都由服务端生成；`Idempotency-Key`（8–128 字符）必填。重复同键同标准化请求返回原 `201` 响应；同键异请求返回 `409 IDEMPOTENCY_CONFLICT`。

`POST /cases/{case_id}/upload` 第一阶段只接收单个已去标识 CT DICOM，最大 20 MiB，并限制解码像素数量。Cloud 只做大小、格式、去标识和必要非像素头字段检查以建立一层 Study/Series/Slice 元数据；**实际像素读取、预处理和推理仍由 Worker 执行并再次验证**。源 DICOM 以随机私有对象键临时存放，记录 SHA-256 与到期时间；不写入数据库像素、不把原始文件名或 DICOM UID 返回前端。上传成功只表示输入可排队，`READY` 不保证后续模型推理成功。Cloud 不在上传时自动创建分类/遮挡 Job；前端须显式调用对应路由。这是为匹配 v2 分离的 Case/Prediction API 所作的决定。

上传同样要求 `Idempotency-Key`。同键同文件摘要重放原 `201` 结果；同键不同内容 409。一次 Case 只能有一个当前有效的 P0 单 Slice 输入；已有输入时不同键上传返回 `409 CASE_ALREADY_HAS_INPUT`，后续多 Series 需要新契约。输入过期后既有元数据可按保留策略查询，但新 Job 返回 `410 INPUT_EXPIRED`，用户须创建新 Case 并重新上传。所有 Case 列表、详情、上传与子对象关系通过 `owner_user_id` 校验；无权访问统一 `404 CASE_NOT_FOUND`，不泄露是否存在。

Case 进入 `DELETING` 后立即停止对用户列出/读取并禁止创建新 Job；后台按数据库冻结文档的墓碑流程完成对象和元数据清理。v2 第一阶段不增加公开删除路由；经批准的保留策略到期或用户主动删除的接口须另定认证与审计契约。

Case 响应的最小字段固定如下；列表按 `(created_at DESC, case_id DESC)` 稳定排序，`cursor` 为不透明游标，不允许客户端用任意 owner ID 过滤：

```json
{
  "case_id": "case_7b10...", "patient_id": "pat_1e52...",
  "status": "READY", "created_at": "2026-09-26T00:00:00Z",
  "input_expires_at": "2026-10-03T00:00:00Z",
  "studies": [{"study_id": "study_...", "series": [{"series_id": "series_...",
    "slices": [{"slice_id": "slice_a921...", "ordinal": 0,
      "width_px": 112, "height_px": 80}]}]}]
}
```

`POST /cases` 的响应只含 `case_id,patient_id,status=CREATED,created_at`；`GET /cases` 响应为 `{"items":[Case 摘要],"next_cursor":null|string}`；上传响应含 `case_id,study_id,series_id,slice_id,status=READY,input_expires_at`。上传不能把 DICOM Header 的身份字段混进这些结构。

## Prediction 与 Job API

`POST /predictions` 和 `POST /jobs/occlusion` 要求 `Idempotency-Key`，冻结 `model_id + checkpoint_sha256 + preprocessing_version + protocol_id + 请求参数 + 输入 SHA-256` 的标准化摘要。相同用户同键同摘要返回原 Job；同键不同摘要 409。`model_id` 解析为 Cloud 已登记的 ACTIVE `ModelVersion`；请求不能指定任意 checkpoint 文件或本地路径。切片必须属于该 Case，输入未过期，用户必须是 Case 所有者。

分类第一阶段 `unit=slice`，无患者级汇总。遮挡仅接受冻结协议 `stage1-occlusion-instability-v1` 及不重复的 16/32/64 像素尺度；`candidate_response`、q0/qg 与空间坐标继续服从现有冻结算法契约。结果 `source=LIVE_CASE`；旧 Mock `source=MOCK` 不经这些 v2 路由。

`GET /predictions/{prediction_id}` 中 `prediction_id` 是该分类 Job 的公共 ID，不再额外创造一个未完成的 Prediction 实体；`CREATED/QUEUED/RUNNING` 时 `prediction=null`，`COMPLETED` 时返回分类摘要及 `result_id`，`FAILED` 时返回脱敏错误。`GET /jobs/{job_id}` 对所有 Job 统一返回：

```json
{
  "job_id": "job_8c2a...",
  "kind": "OCCLUSION",
  "case_id": "case_7b10...",
  "status": "RUNNING",
  "attempt_no": 1,
  "retry_count": 0,
  "lease_expire_time": "2026-09-26T00:01:30Z",
  "last_heartbeat": "2026-09-26T00:00:00Z",
  "failure_reason": null,
  "progress": null,
  "estimated_remaining_time_ms": null,
  "result_id": null,
  "error": null,
  "created_at": "2026-09-26T00:00:00Z",
  "finished_at": null
}
```

`POST /predictions` 与 `POST /jobs/occlusion` 的 `202` 响应固定为 `job_id,case_id,status=CREATED,status_url`，分类额外给出等于 `job_id` 的 `prediction_id`。`GET /predictions/{id}` 固定为 `prediction_id,job_id,status,result_id,prediction,error`；完成前 `result_id/prediction=null`，失败时只填脱敏 `error`。`prediction` 使用 `predicted_class`（0/1）、`class_label`、`positive_probability`、`predicted_class_confidence`、`inference_time_ms`、`model_version`、`preprocessing_version` 和 `source=LIVE_CASE`。正类概率与预测类别置信度不能混用。`GET /jobs/{id}` 的 `progress`/ETA 允许 `null`，时间为 UTC ISO 8601；`error` 为 `{"code","message"}` 或 `null`，`FAILED` 时其 `code` 等于 `failure_reason`。

`CREATED` 是本轮指定的 v2 初态；上游文档的 `PENDING` 及 P0 `/api/v1` 的状态只用于迁移映射。无安全取消协议，因此 v2 不提供取消路由或 `CANCELLED` 状态。前端刷新后可凭所有者身份和 Job ID 恢复查询。

## Job State Machine v1.0

| 状态 | 含义 | 唯一允许的下一状态 |
| --- | --- | --- |
| `CREATED` | Backend 已保存请求、幂等键和版本，正在校验 | `QUEUED`、`FAILED` |
| `QUEUED` | 输入有效且可被匹配 Worker 领取；重试退避也在此状态 | `RUNNING`、`FAILED` |
| `RUNNING` | 恰有一个有效 Attempt/租约 | `COMPLETED`、`QUEUED`、`FAILED` |
| `COMPLETED` | Backend 已验证并发布唯一结果 | 无，终态 |
| `FAILED` | 永久失败、重试用尽或输入过期 | 无，终态 |

只有 Backend 能写 Job 状态：API/验证器创建并排队；调度器响应已认证 Worker 的 `POST /workers/jobs/claim`，在一个事务中锁定 `QUEUED` Job、核对模型与输入、创建 Attempt、更新 `attempt_no`/`retry_count`、生成仅该 Worker 可用的高熵 lease token、设置 `lease_expire_time=服务器当前时间+90 秒`，然后写 `RUNNING`。Worker 不能直接写状态，只能通过 Heartbeat 续租或通过 Submit Result 报成功/失败。用户只能创建和查询任务。租约和状态并发变更采用条件更新，同一 Job 同时最多一个有效 Attempt。

`retry_count` 是**已领取的重试次数**：首次领取为 0，第二次为 1，第三次为 2；最多 **2 次重试、3 次总领取**。可重试错误为租约超时/Worker 失联、临时传输失败、明确的暂时性 GPU 资源不可用；首次失败后至少 30 秒、第二次失败后至少 120 秒再次派发。输入、模型 checkpoint 哈希和协议版本在同一 Job 的所有 Attempt 中固定。DICOM/预处理确定性错误、模型或协议哈希不符、越权、结果 Schema/资产哈希错误、输入到期，或第三次领取失败时进入 `FAILED`。Backend 依据服务端错误码白名单判断可重试性，不信任 Worker 自报 `retryable`。`failure_reason` 存稳定脱敏失败码；不存路径、堆栈或患者信息。

Worker 每 15 秒发 Heartbeat；Backend 验证 Worker、Attempt 和 lease token 后，在同一事务更新 Job/Attempt 的 `last_heartbeat` 与 `lease_expire_time=服务器当前时间+90 秒`，并更新节点的 `last_heartbeat_at`。无效或已到期的心跳不能续租。节点 45 秒无成功心跳派生为 `OFFLINE`，不再派新 Job；运行中 Job 等租约实际到期才回收。回收器最长每 15 秒检查，先使旧 Attempt/lease 失效，再按次数和输入可用性转 `QUEUED` 或 `FAILED`；晚到结果返回 `409 STALE_ATTEMPT`。有效租约内短暂断网可继续，租约到期后 Worker 不得自行续算或上传旧结果。

`lease_expire_time` 和 `last_heartbeat` 在非 `RUNNING` Job 中为 `null`。`FAILED` 必填 `failure_reason` 和 `finished_at`；`COMPLETED` 必有一个可见 Result 和 `finished_at`。原始 DICOM 到期后不再领取或重试；已下载输入且租约仍有效的 Attempt 可完成。v2 **不实现运行中 cancel，也不提供取消接口或 `CANCELLED` 状态**。P0 的排队取消保持在其旧版本边界内。

## Result API

Job 完成后 `GET /jobs/{id}` 和 `GET /predictions/{id}` 提供 `result_id`，再通过 `GET /results/{result_id}` 取完整结果。响应包含 `contract_version=2.0`、Case/Slice、model/checkpoint/preprocessing/protocol 版本、`source=LIVE_CASE`、分类或遮挡结果、资产 ID 和 provenance；不得含原始 DICOM、私有对象键、路径、token 或患者信息。只有 `COMPLETED` Job 的已验证结果可见；`FAILED` 不生成成功 Result。

云端原始 DICOM 仅私有临时保存，默认上传后 **7 天**清除，部署可配置有限正整数天；`input_expires_at` 是上传时确定的具体到期时间。云端不提供长期 DICOM 下载或归档能力。Inference Result、图层资产和解释所需的匿名元数据默认长期保存，不随原始 DICOM 到期自动删除；经批准的删除或保留策略另行处理。Worker 临时缓存按 [worker_protocol_v1_freeze.md](worker_protocol_v1_freeze.md) 清理。

遮挡位置按尺度与游标分页，返回数值而非仅从 PNG 反推；热图和预览资产用同一 Result 归属授权。资产请求同时校验用户 → Case → Job → Result → asset_id，任何一环不匹配返回 404。服务端流式读取私有存储，禁止裸露通用文件目录或 Gradio 文件路由。响应需使用 `Content-Type` 白名单和 `X-Content-Type-Options: nosniff`。

完整 Result 顶层字段固定为 `result_id,job_id,case_id,slice_id,kind,contract_version,source,status,model_id,model_version,preprocessing_version,protocol_id,prediction,scale_summaries,cross_scale,provenance,assets,created_at`。`PREDICTION` 的 `scale_summaries/cross_scale/assets` 为空数组；`OCCLUSION` 的尺度摘要、跨尺度数值和位置项沿用现有冻结算法契约，位置数组只经分页端点返回。无效正响应区域的 `candidate_status=insufficient_positive_response`、`candidate_layer=null`、`candidate_area_fraction=null`，不能伪造病灶。资产描述仅含 `asset_id,layer_kind,width,height,coordinate_space,media_type`；不含私有存储键。位置分页响应固定 `result_id,scale,positions,next_cursor`，`next_cursor=null` 表示结束。

## 通用错误、身份与版本

用户路由需经部署的认证组件解析为 `users.auth_subject`；本设计只冻结 Backend 的所有者授权，登录/刷新凭据端点由独立认证契约定义。Worker 路由使用独立预配 Bearer，用户 token 不能调用。所有错误采用 `code,message,retryable,request_id,details`；常用状态为 401 未认证、403 Worker 禁用、404 对象不可见、409 幂等/状态冲突、410 输入过期、413 超限、415 非 DICOM、422 格式/去标识/参数错误、503 存储或调度不可用。错误信息不得暴露 PHI、路径、堆栈、checkpoint 位置或 Worker token。

`/api/v2` 与 `/api/v1` 可并存，但不把 P0 SQLite 数据或 Gradio 本机认证自动视作 v2 多用户权限。Capability/health 如要对外提供，应分别声明 v2 已实现能力和服务健康；不因离线算法存在而宣称在线 Worker/模型可用。

## 冻结输入版本

本组三份正式冻结文档共同基于仓库 HEAD `021e4f56103e53c82b5abf76465f62fb4f1bc6c3` 和以下本地原文 SHA-256；文件名为来源标识，不表示原文已经包含本组新增的实施决策。

| 原文 | SHA-256 |
| --- | --- |
| `EpiLocate_Backend_API_Contract_v2.0.docx` | `08dacbeee507afdb461e094729ff66968e651cb10df2bb6db8a91e9fe0323d66` |
| `EpiLocate_Database_Schema_v1.0.docx` | `48b6033210619e0de89c4786b405d368a2dab7677674762ce18daef79b470c89` |
| `EpiLocate_AI_Worker_Architecture_v1.0.docx` | `c6f95172e9c0c395a06ebf431bc9becbc2d4bc5665421b34350c311d4303be07` |
| `EpiLocate_Deployment_Architecture_v1.0.docx` | `59ab8f74285ea2137f12b514af9a7ecfe3d8e1d163b20b0632c61adbbbc8741d` |
