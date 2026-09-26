# EpiLocate Worker Protocol v1.0 Freeze

状态：**正式冻结版 v1.0，待最终确认后进入实现**。适用于 Cloud Control Plane 与已预配 AI Worker 的第一阶段轮询通信，公共基址为 `/api/v2`。任务领取按 Design Freeze Review 修订为有副作用的 `POST /workers/jobs/claim`，不保留旧 `GET /workers/jobs/next` 别名。Worker 只处理临时 DICOM、冻结模型推理、遮挡和图层生成；云端负责身份、Case、调度、结果和资产权限。没有 WebSocket、消息队列、自动扩缩容、自动模型发布或医院多租户权限。

## 传输、身份与通用格式

- 所有 Worker 请求使用 HTTPS（TLS 1.2 或更新）；Cloud 和 Worker 间不得接受明文 HTTP。Worker 使用独立的 `Authorization: Bearer <worker-token>`，不能使用用户 token。管理员在部署时预配随机 `worker_id` 与高熵 token；`worker_id` 对应数据库 `worker_nodes.node_id`，数据库只存 token SHA-256，token 由 Worker 本地受保护配置持有。Register 是激活/更新能力，不是匿名领取凭据。停用节点或轮换 token 后旧 token 立即失效。
- 每个请求必须带 `X-Request-ID`（UUID）。服务器按其生成/回显请求追踪 ID；日志不能记录 Authorization、lease token、签名 URL、DICOM 内容或文件名。Worker 响应统一 `Cache-Control: no-store`。领取使用 POST，因为它会原子地使 Job 从 `QUEUED` 进入 `RUNNING`。
- 标准错误体：`{"code":"STABLE_CODE","message":"脱敏说明","retryable":false,"request_id":"uuid","details":{}}`。`retryable` 是对**当前 HTTP 请求**能否安全重发的提示，不能代替 Job 的重试分类。认证和对象归属先于返回资源是否存在的细节。
- 所有 `job_id/case_id/slice_id/worker_id` 均为匿名公共 ID。Worker 没有枚举其他 Case、结果或 Worker 的权限；领任务只授予该 Attempt 的输入读取和结果提交范围。输入签名 URL 最长有效 5 分钟，绑定私有对象、方法和有效期；不放在日志、持久结果或浏览器响应中。
- v1 每节点最多一个 `RUNNING` Attempt。节点心跳间隔 15 秒，离线判定 45 秒，Job 租约 90 秒；以服务器时间为准。状态、重试与终态见 [backend_api_contract_v2_freeze.md](backend_api_contract_v2_freeze.md)。

## 1. Register

`POST /api/v2/workers/register`。预配 token 对应的 `worker_id` 必须与请求一致；模型列表只声明 Worker 本地已通过哈希核验的 checkpoint。

请求（`application/json`）：

```json
{
  "worker_id": "node_4e9c...",
  "worker_version": "1.0.0",
  "hardware": {"accelerator": "CUDA", "gpu_memory_mib": 6144},
  "supported_model_versions": [{"model_id": "baseline_resnet18", "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
  "max_concurrent_jobs": 1
}
```

响应 `200`：

```json
{
  "worker_id": "node_4e9c...",
  "registered": true,
  "heartbeat_interval_seconds": 15,
  "offline_after_seconds": 45,
  "lease_seconds": 90,
  "max_concurrent_jobs": 1,
  "server_time": "2026-09-26T00:00:00Z"
}
```

同一已授权节点重复注册且能力摘要相同，返回同一配置；能力变化可更新非身份字段并写审计。禁用节点 `403 WORKER_DISABLED`；`worker_id` 与 token 不匹配 `403 WORKER_ID_MISMATCH`；未预配或无 token `401 WORKER_UNAUTHENTICATED`；参数或模型哈希格式错误 `422 INVALID_WORKER_CAPABILITIES`。Register 不会创建新模型版本，也不会信任 Worker 自称的模型可用性：派单前还要与 Cloud 的 `model_versions.checkpoint_sha256` 精确匹配。

## 2. Heartbeat

`POST /api/v2/workers/heartbeat`。注册后每 15 秒发送；活动 Attempt 的 `lease_token` 由 Claim 返回，仅在本请求和结果提交中使用。

请求（`application/json`）：

```json
{
  "worker_id": "node_4e9c...",
  "activity_state": "RUNNING",
  "active_attempt": {
    "job_id": "job_8c2a...",
    "attempt_id": "uuid",
    "lease_token": "opaque-secret"
  }
}
```

空闲时 `activity_state=IDLE` 且 `active_attempt=null`；本地故障可报 `ERROR`，但 Backend 仍独立判断已有租约。响应 `200`：

```json
{
  "worker_id": "node_4e9c...",
  "connectivity": "ONLINE",
  "activity_state": "RUNNING",
  "lease_expire_time": "2026-09-26T00:01:30Z",
  "server_time": "2026-09-26T00:00:00Z",
  "drain": false
}
```

无活动 Attempt 时 `lease_expire_time=null`。服务端只在当前 Job 为 `RUNNING`、Attempt 为 `CLAIMED`、token/Worker 均匹配且租约未过期时续租；把 Job 与 Attempt 的 `last_heartbeat` 和 `lease_expire_time=服务器当前时间+90 秒` 在同一事务内更新，同时更新 WorkerNode 的 `last_heartbeat_at`。重复 Heartbeat 安全，绝不额外创建 Job。错误：`401 WORKER_UNAUTHENTICATED`、`403 WORKER_DISABLED/WORKER_ID_MISMATCH`、`409 STALE_ATTEMPT`、`422 INVALID_HEARTBEAT`。节点超过 45 秒无成功心跳派生 `OFFLINE`，但当前 Job 要等租约届满才重派。

## 3. Claim Job

`POST /api/v2/workers/jobs/claim`，`application/json`，`Idempotency-Key` 必填且为本次领取生成的 UUID。Bearer token 决定节点，不能仅凭请求中的 `worker_id` 取得任务。请求固定字段：

```json
{
  "worker_id": "node_4e9c...",
  "available_capacity": 1,
  "supported_model_versions": [
    {"model_id": "baseline_resnet18", "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
  ]
}
```

`available_capacity` 为整数 0 或 1；对新的 Claim，0 返回 `204 No Content`，不改变任何 Job。服务端先检查同 key 的已存在领取，以允许 Worker 在首次响应丢失后以 `available_capacity=0` 重放；`claim_request_digest` 由 `worker_id` 和排序后的 `supported_model_versions` 计算，不含随领取变化的 `available_capacity`。同 key 但摘要不同返回 `409 CLAIM_KEY_CONFLICT`。`supported_model_versions` 与该 Worker 最近注册的能力取交集，不能扩权或改写 ModelVersion。响应 `204` 还表示当前无匹配 Job；响应 `200` 表示已在数据库事务中原子领取，必须至少含以下字段：

```json
{
  "job_id": "job_8c2a...",
  "case_id": "case_7b10...",
  "input_reference": {
    "url": "https://private-object-store/signed-temporary-url",
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "expires_at": "2026-09-26T00:05:00Z"
  },
  "model_version": {
    "model_id": "baseline_resnet18",
    "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "preprocessing_version": "formal-resnet18-baseline-rule-b-v1",
    "protocol_id": "stage1-occlusion-instability-v1"
  },
  "lease_expire_time": "2026-09-26T00:01:30Z",
  "job_parameters": {"kind": "OCCLUSION", "slice_id": "slice_a921...", "scales": [16, 32, 64]},
  "attempt_id": "uuid",
  "attempt_no": 1,
  "lease_token": "opaque-secret"
}
```

Backend 只挑 `QUEUED`、`next_attempt_at <= now()`、输入未过期、checkpoint 哈希在该 Worker 已注册能力中的 Job。Claim 原子创建 Attempt、存 `claim_key` 和请求摘要、将 Job 改为 `RUNNING` 并设置 90 秒 lease。相同 Worker、相同 `Idempotency-Key` 且 Attempt 仍有效时，重复 Claim 返回同一 Job、Attempt 和可重建的同一 lease token，并可刷新输入签名 URL，**不领取第二个 Job**；该 key 对应的 Attempt 已终结时返回 `409 CLAIM_ALREADY_FINISHED`。不同 key 但节点已有活动 Attempt 时返回 `409 WORKER_BUSY`。无任务的 `204` 不创建 Attempt；之后重新轮询应生成新 key。lease token 用服务端密钥对 Attempt/节点派生并只存其哈希；服务端密钥轮换须先处理活跃租约。不同 Worker 并发 Claim 由行级锁保证仅一方领取。错误：`401 WORKER_UNAUTHENTICATED`、`403 WORKER_DISABLED/WORKER_ID_MISMATCH`、`409 WORKER_BUSY/CLAIM_ALREADY_FINISHED/CLAIM_KEY_CONFLICT`、`422 INVALID_CLAIM`、`503 SCHEDULER_UNAVAILABLE`。

Worker 下载输入后必须校验 `input_reference.sha256`，只写受限临时目录；不解析为路径名或患者标识。下载失败用 Submit Result 报可重试传输故障；签名 URL 过期但租约仍有效、原始对象尚在 7 天临时保留期内时，可用原 `Idempotency-Key` 重复 Claim 获取刷新地址。Worker 本地模型哈希不匹配时不得推理，应报 `MODEL_HASH_MISMATCH`。

## 4. Submit Result

`POST /api/v2/workers/results`，`multipart/form-data`：`manifest` 是 UTF-8 JSON，`assets[]` 为可选二进制图层。单次请求上限 64 MiB；Cloud 必须流式接收而非整包读入内存。每个资产须在 manifest 中列出 MIME、字节数和 SHA-256，服务端逐一校验。失败报告不得附资产。

成功 `manifest` 的必填字段为 `worker_id,job_id,attempt_id,lease_token,outcome,model_id,checkpoint_sha256,input_sha256,result,assets`。`outcome=SUCCEEDED` 时，`result` 必须含 `contract_version=2.0`、`source=LIVE_CASE`、`case_id`、`slice_id`、`kind`、`model_id`、`model_version`（与 checkpoint SHA 相同）、`preprocessing_version`、`protocol_id`。分类结果还须含 `prediction`，字段为 `predicted_class`（0/1）、`class_label`、`positive_probability`、`predicted_class_confidence`、`inference_time_ms`；遮挡结果还须含 `prediction`、`scale_summaries`、`cross_scale`、`positions`，各尺度和位置的数值/空值语义沿用 `docs/interfaces/algorithm_api_contract.yaml` 的 `ScaleSummary`、`CrossScaleMetric`、`OcclusionPosition`，服务端按 v2 顶层字段严格验证。`assets` 中每项须有 `asset_id,part_name,layer_kind,media_type,size_bytes,sha256`，`asset_id` 必须与结果图层引用一致。数组顺序不得改变结果摘要；摘要取规范化 manifest（排除 lease token）与按 `part_name` 排序的资产 SHA-256。

成功 `manifest` 示例（展示分类任务；哈希与 ID 为形状示例）：

```json
{
  "worker_id": "node_4e9c...",
  "job_id": "job_8c2a...",
  "attempt_id": "uuid",
  "lease_token": "opaque-secret",
  "outcome": "SUCCEEDED",
  "model_id": "baseline_resnet18",
  "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "input_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "result": {
    "contract_version": "2.0", "source": "LIVE_CASE",
    "case_id": "case_7b10...", "slice_id": "slice_a921...", "kind": "PREDICTION",
    "model_id": "baseline_resnet18", "model_version": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "preprocessing_version": "formal-resnet18-baseline-rule-b-v1",
    "protocol_id": "stage1-occlusion-instability-v1",
    "prediction": {"predicted_class": 0, "class_label": "negative",
      "positive_probability": 0.0256, "predicted_class_confidence": 0.9744,
      "inference_time_ms": 120}
  },
  "assets": []
}
```

失败时 `outcome=FAILED`、`result=null`、`assets=[]`，并带 `error:{"code":"INPUT_DOWNLOAD_FAILED","message":"Input transfer failed."}`。Worker 不决定最终 Job 状态或重试次数；Backend 按白名单区分可重试与永久失败。成功或失败接受后的响应均为 `200`：

```json
{
  "job_id": "job_8c2a...",
  "attempt_id": "uuid",
  "accepted": true,
  "job_status": "COMPLETED",
  "result_id": "result_3d1b...",
  "server_time": "2026-09-26T00:00:00Z"
}
```

失败报告的 `result_id=null`，`job_status` 为 `QUEUED` 或 `FAILED`。服务端验证 token、节点、Attempt、有效租约、Job/Case/Slice/模型/协议版本、输入哈希、JSON Schema、资产清单和每个字节哈希；先将资产置于不可见暂存，再在事务内写结果及终态，最后仅通过受授权的 Result/Asset API 暴露。提交内容生成规范化 SHA-256，记入 `job_attempts.submission_digest` 和已接受响应。先查已接受的同 Attempt 同摘要提交，重复时返回保存的响应，即使首次 HTTP 回包丢失或租约随后到期；同 Attempt 不同摘要 `409 RESULT_CONFLICT`；尚未接受且已过期/非本节点的 Attempt 返回 `409 STALE_ATTEMPT`。不能以结果上传创建 Case、修改其他 Job 或覆盖已完成结果。

错误：`401 WORKER_UNAUTHENTICATED`，`403 WORKER_DISABLED/WORKER_ID_MISMATCH`，`404 JOB_NOT_FOUND`（对无权节点可统一为 404），`409 STALE_ATTEMPT/RESULT_CONFLICT`，`413 RESULT_TOO_LARGE`，`415 UNSUPPORTED_ASSET_TYPE`，`422 RESULT_SCHEMA_INVALID/ASSET_HASH_MISMATCH/MODEL_HASH_MISMATCH`，`503 RESULT_STORAGE_UNAVAILABLE`。5xx 可用同一 Attempt/同一 payload 重发；若首次提交已被接受，租约到期后仍可重放已保存的响应；若未接受且租约已失效，以 `STALE_ATTEMPT` 为准。

## 权限与数据边界

Worker token 仅授予上述四类路由及其当前 Attempt 的临时输入。用户 token 不能调用 Worker API，Worker token 不能调用用户 Case 列表或 Result API。原始 DICOM 云端只在私有暂存保留，默认 7 天、可配置；云端不是长期 DICOM 存储。Inference Result 的 JSON 和图层资产长期保存，不受原始 DICOM 临时保留期影响；读取须经 Case 所有权和结果归属校验。Worker 推理结束并收到 Backend 结果接受后立即清理原始输入、解码像素和中间缓存；失败或租约失效也清理，异常退出后的残留由启动清理器在 24 小时内删除。Mock 结果不能提交为 `LIVE_CASE`；正式 validation 和 sealed test 不进入在线 Worker 通道。

## 失联、重试与失败收敛

Worker 每 15 秒心跳；Backend 验证当前 Attempt 后更新 `last_heartbeat` 并把 `lease_expire_time` 延至服务器当前时间 +90 秒。节点 45 秒无成功心跳即停止新派单，但已有 Attempt 直到 lease 到期才被回收。Backend 标记旧 Attempt 为 `EXPIRED` 并撤销 token；尚有输入且 `retry_count<2` 时退避后重新排队，新 Claim 生成新 Attempt。最多 2 次重试、3 次总领取；确定性错误、输入过期或次数耗尽进入 `FAILED`，`failure_reason` 为稳定脱敏错误码。晚到的未接受结果返回 `409 STALE_ATTEMPT`；Worker 不得在旧租约上继续上传。运行中不提供 cancel。
