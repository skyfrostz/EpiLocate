# Worker API 与 Job lifecycle — Phase 5 implementation

**代码基线：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9`；核对 `backend_v2/api/app.py`、`services/jobs.py`、`workers/sweeper.py`、`worker/{client,agent,config,device}.py`。这是 [Worker Protocol v1 冻结稿](worker_protocol_v1_freeze.md) 的实现对照，**不改变 Worker 协议**。浏览器只读 Job/Result；Worker API 必须使用独立预配的 Worker Bearer，直接到 Backend，不经 Session Gateway。

## Worker 身份与路由

Worker token 的 SHA-256 对应 `worker_nodes.token_hash`，`worker_id` 必须等于该节点的 `node_id`。每个 Worker 请求都有 `Authorization: Bearer …` 与 UUID `X-Request-ID`；缺失或不合法分别得到 401/422，禁用节点 403。普通用户 token 不能调用 Worker API，Worker token 不能调用用户 API。当前 Backend 验证 `X-Request-ID` 为 UUID，但**不会按旧冻结稿所述回显此 ID**；错误 `request_id` 独立生成。Worker 响应带 `Cache-Control:no-store`。以下路径都有 `/api/v2` 前缀。

| 方法与路径 | 核心请求 | 成功响应 |
| --- | --- | --- |
| `POST /workers/register` | `worker_id,worker_version,hardware,supported_model_versions:[{model_id,checkpoint_sha256}],max_concurrent_jobs:1` | 200 `worker_id,registered:true,heartbeat_interval_seconds:15,offline_after_seconds:45,lease_seconds:90,max_concurrent_jobs:1,server_time` |
| `POST /workers/heartbeat` | `worker_id,activity_state:"IDLE"|"RUNNING"|"ERROR",active_attempt:null|{job_id,attempt_id,lease_token}` | 200 `worker_id,connectivity:"ONLINE",activity_state,lease_expire_time,server_time,drain:false` |
| `POST /workers/jobs/claim` | UUID `Idempotency-Key`；`worker_id,available_capacity:0|1,supported_model_versions` | 200 Claim JSON；无匹配任务或新请求 capacity=0 为 204 |
| `POST /workers/jobs/{job_id}/result` | multipart `manifest` JSON 字符串和零或多个 `assets[]` PNG | 200 `job_id,attempt_id,accepted:true,job_status,result_id:null|string,server_time` |
| `POST /workers/results` | 与上一行相同，不带路径 Job ID | 同上；当前 Backend 保留的等价别名 |

Register 更新本节点能力，不匿名创建 Worker；能力列表中的 `checkpoint_sha256` 必须是 64 位小写十六进制。Backend 派单时取已注册能力、Claim 声明和 ACTIVE ModelVersion 的交集，按 model ID 与 checkpoint SHA 精确匹配。Worker 本地 `MODEL_HASH` 必须等于 FrozenBaseline checkpoint SHA，`MODEL_VERSION=MODEL_HASH`。Worker 运行模式保留 `CPU`、`CUDA`、`AUTO`；模式不是 Job/Result API 字段。Phase 5 MVP 测试部署只启动 RTX 3090 CUDA Worker，ECS CPU Worker 未启动，不能据此声称 CPU/GPU 结果数值可互换。

## Claim、lease、心跳与重试

`POST /workers/jobs/claim` 对 `QUEUED` Job 原子创建 `JobAttempt`、设置 `attempt_no`，将 Job 改为 `RUNNING`，并返回：
```json
{
  "job_id":"job_…","case_id":"case_…",
  "input_reference":{"url":"signed HTTPS DICOM GET","sha256":"64 hex","expires_at":"UTC ISO 8601"},
  "model_version":{"model_id":"baseline_resnet18","checkpoint_sha256":"64 hex",
    "preprocessing_version":"…","protocol_id":"…"},
  "lease_expire_time":"UTC ISO 8601",
  "job_parameters":{"kind":"PREDICTION|OCCLUSION","slice_id":"slice_…","scales":[16,32,64]},
  "attempt_id":"UUID","attempt_no":1,"lease_token":"secret"
}
```
输入 URL 是**仅交给 Worker** 的私有对象签名 GET，最长 300 秒，且不会超过 DICOM 保留期。浏览器 DICOM/热图均走鉴权 Backend 代理。Claim 同 key、同 worker 与同能力摘要，在 Attempt 尚有效时重放同一 Job/Attempt/lease token，可更新输入 URL；重放时 `available_capacity=0` 仍可取回原 Claim。同 key 不同摘要为 `409 CLAIM_KEY_CONFLICT`，已结束为 `409 CLAIM_ALREADY_FINISHED`；节点忙为 `409 WORKER_BUSY`。新的 `available_capacity=0` 返回 204，不新建 Job。无匹配任务返回 204，下一轮使用新 key。

新 Claim 需要已注册且最近 45 秒有成功心跳的节点。首次租约 90 秒；Worker 每 15 秒发 Heartbeat。携带当前 Attempt 的心跳验证 Worker、Job、lease token、未过期状态后，将 Job 与 Attempt 的 `last_heartbeat` 和 `lease_expire_time` 更新至服务器当前时间 +90 秒。空闲心跳只更新节点；`RUNNING` 必须带 `active_attempt`，`IDLE/ERROR` 不能带。离线节点不再接新 Job；原 Job 到 lease 到期才由 Backend sweeper 回收，晚到的未被接受结果为 `409 STALE_ATTEMPT`。

Job 状态及操作者：

| 状态变化 | 执行者与条件 |
| --- | --- |
| 新建 `CREATED` | 用户 POST 创建；Backend 写记录 |
| `CREATED → QUEUED` 或 `FAILED` | Backend Validator / 15 秒 sweeper；输入过期或 ModelVersion 失效则失败 |
| `QUEUED → RUNNING` | 已认证 Worker Claim 触发 Backend 原子领取 |
| `RUNNING → COMPLETED` | Backend 验证有效 Attempt、Result、模型与输入哈希、资产后写唯一 Result |
| `RUNNING → QUEUED` | 可重试失败或 lease 过期且输入仍在有效期内，延迟重派 |
| `RUNNING → FAILED` | 不可重试失败、输入过期或次数耗尽 |
| `COMPLETED/FAILED` | 终态；无用户/Worker cancel 接口 |

首次领取 `attempt_no=1,retry_count=0`；最多三次领取、两次重试。重试白名单为 `INPUT_DOWNLOAD_FAILED`、`TEMPORARY_GPU_UNAVAILABLE`、`TEMPORARY_TRANSPORT_FAILURE`、`LEASE_EXPIRED`；失败后退避 30 秒、120 秒。其他 Worker 错误码视为永久失败。创建阶段输入过期为 `FAILED/INPUT_EXPIRED`；Claim 时输入到期也失败；Result 失败提交由 Backend 判断重试。Heartbeat 不能复活过期 lease。Job 查询中的 `progress` 和 ETA 当前为 `null`，前端只能显示状态与时间，不应据轮询次数推算进度。没有运行中 cancel。

## Result 提交与幂等

Worker 实际使用 `POST /workers/jobs/{job_id}/result`；Backend 也接受 `POST /workers/results`。两者使用 `multipart/form-data`：`manifest` 为 JSON 字符串，`assets[]` 为与 manifest 中 `part_name` 对应的 PNG 文件，整个处理上限 64 MiB。带路径版本先检查路径 `job_id` 与 manifest 一致。成功 manifest 必须含 `worker_id,job_id,attempt_id,lease_token,outcome:"SUCCEEDED",model_id,checkpoint_sha256,input_sha256,result,assets`；失败 `outcome:"FAILED"`，`result:null`、`assets:[]`，另带 `error:{code,message}`。Backend 检查 Attempt 归属和租约、checkpoint 与输入 SHA、Result 的 `contract_version:"2.0"`/`source:"LIVE_CASE"`、分类与遮挡 schema、每个 PNG 的格式/尺寸/字节数/SHA。Result JSON 长期存入 PostgreSQL；图层 PNG 和元数据写入私有对象存储及 Asset 表，Result 只能经拥有者 API 读取。

同一 Attempt 相同规范化提交摘要重发时返回保存的 200 响应，即使首次 HTTP 响应丢失或后来租约到期；同 Attempt 不同 payload 为 `409 RESULT_CONFLICT`。未接受且 lease 过期为 `409 STALE_ATTEMPT`。Worker 不得修改其他 Case/Job，不能将 Mock 结果提交为 `LIVE_CASE`。当前实现以 `await part.read()` 将 manifest/资产读入内存，再写对象；旧冻结稿的“流式接收”尚未实现，属容量风险。

常见错误：401 `WORKER_UNAUTHENTICATED`，403 `WORKER_DISABLED/WORKER_ID_MISMATCH/WORKER_NOT_REGISTERED`，409 `STALE_ATTEMPT/RESULT_CONFLICT/WORKER_OFFLINE/WORKER_BUSY/CLAIM_KEY_CONFLICT`，413 `RESULT_TOO_LARGE`，422 `RESULT_SCHEMA_INVALID/ASSET_HASH_MISMATCH/MODEL_HASH_MISMATCH/INPUT_HASH_MISMATCH`。服务端错误体为 `code,message,retryable,request_id,details`。Worker 仅在有效 lease 内继续处理；原始输入、解码像素和中间缓存应在任务结束后清理。

## Phase 5 验证边界

GPU-only Full-Chain MVP 的 CUDA Prediction 与 16/32/64 Occlusion、Result/Asset 存储和浏览器刷新功能已通过工程验证。固定 CPU/GPU **数值**一致性仍 **FAILED / OPEN**：最大派生偏差 `0.001049876`，容差 `0.0001`。这不改变 Worker 报文或 `LIVE_CASE` 结果 API 的功能通过结论，但禁止宣称 CPU/GPU 数值等价；详见 [Phase 5 验收报告](../phase5/gpu_full_chain_mvp_report.md)。
