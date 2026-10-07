# Backend API Contract — Phase 5 implementation

**代码基线：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9`，核对 `backend_v2/api/app.py`、`backend_v2/services/{cases,jobs,retention,storage}.py`、`backend_v2/models/entities.py`。本文件描述该提交的**已实现行为**，替代 [v2.0 设计冻结稿](backend_api_contract_v2_freeze.md) 作为前端联调依据；不是新协议提案。所有用户 API 位于同源 `/api/v2`，浏览器先经 [Session Gateway](session_gateway_contract_phase5.md)。Worker API 见 [Worker 与 Job 文档](worker_api_job_lifecycle_phase5.md)。

## 身份、错误与版本边界

Backend 用户路由接受服务端注入的 `Authorization: Bearer <user-token>`；浏览器只持有 Gateway 的 HttpOnly Cookie 和非保密 CSRF 值。Backend 的 `user_credentials` 只存 token SHA-256、到期与撤销状态。缺失、无效、过期、已撤销或停用用户均返回 `401 UNAUTHENTICATED`。不同所有者的 Case、Job、Result 统一按不可见资源返回 404。Worker Bearer 独立，不能访问用户路由。部署例子与路径配置见 [前端集成指南](frontend_integration_guide_phase5.md)，**MVP 测试域名和 `/mvp/` 不是永久 API 基址**。

Backend 业务错误格式为 `{"code":"...","message":"...","retryable":false,"request_id":"uuid","details":{}}`；Pydantic 请求验证错误为 `422 INVALID_REQUEST`。Gateway 显式拒绝的请求只有 `{"code":"..."}`，其登录请求体 Schema 错误由 FastAPI 返回 `422 {"detail":[…]}`；转发的 Backend 错误原样保留。因此客户端必须先按 HTTP status 处理，优先读取可用的 `code`，其余字段均为可选。401 清空前端登录态并重新校验 Session；403 表示已认证但 Origin/CSRF 或 Worker 权限拒绝；404 不证明资源不存在；410 表示**有权访问的**输入或资产过期；409 表示幂等键、状态或租约冲突。网络超时不能当作 Job 失败。

## 路由总览

除 Worker 行外，以下均需 Gateway Session（直接访问 Backend 时需用户 Bearer）。`Idempotency-Key` 为必填请求头，长度 8–128 字符；Worker Claim 另要求 UUID。

| 方法 | 路径（均在 `/api/v2` 下） | 成功 | 用途 |
| --- | --- | --- | --- |
| POST | `/cases` | 201 JSON | 创建 Case |
| GET | `/cases?limit=20&cursor=...` | 200 JSON | 本人 Case 列表 |
| GET | `/cases/{case_id}` | 200 JSON | Case 与 Study/Series/Slice |
| POST | `/cases/{case_id}/upload` | 201 JSON | 单个去标识 CT DICOM |
| GET | `/cases/{case_id}/dicom` | 200 `application/dicom` | 授权读取仍保留的原始 DICOM |
| POST | `/predictions` | 202 JSON | 创建分类 Job |
| GET | `/predictions/{prediction_id}` | 200 JSON | 分类 Job 摘要 |
| POST | `/jobs/occlusion` | 202 JSON | 创建遮挡 Job |
| GET | `/jobs/{job_id}` | 200 JSON | 两种 Job 统一状态 |
| GET | `/results/{result_id}` | 200 JSON | 完成的 Result |
| GET | `/results/{result_id}/positions?scale=16&cursor=0&limit=100` | 200 JSON | 遮挡位置分页 |
| GET | `/results/{result_id}/assets/{asset_id}` | 200 `image/png` | 授权热图字节 |
| POST | `/workers/register`、`/workers/heartbeat`、`/workers/jobs/claim`、`/workers/results`、`/workers/jobs/{job_id}/result` | 200/204 | 直达 Backend 的 Worker 专用路由 |

没有 v2 用户端 cancel、Case 删除、患者级预测或批量 DICOM 路由。`/api/v1` Mock 和旧 Gradio 入口不属于本契约。

## Case

`POST /cases`：JSON `{"patient_id":null}`；也可传同一用户现有匿名 `pat_…` ID。响应 `{"case_id":"case_…","patient_id":"pat_…","status":"CREATED","created_at":"UTC ISO 8601"}`。同一用户、同一键、同一请求重放原响应；不同请求为 `409 IDEMPOTENCY_CONFLICT`。无权使用的 Patient ID 返回 404。

`GET /cases`：`limit` 为 1–100，默认 20；`cursor` 是绑定用户、带签名的不透明游标。响应 `{"items":[CaseDetail,…],"next_cursor":null|"opaque"}`，**当前实现的列表项也是完整 Case 结构**，含 `studies`，不能按旧稿假定只给摘要。Case 详情形状：

```json
{
  "case_id": "case_…", "patient_id": "pat_…", "status": "READY",
  "created_at": "UTC ISO 8601", "input_expires_at": "UTC ISO 8601",
  "studies": [{"study_id":"study_…","series":[{"series_id":"series_…",
    "slices":[{"slice_id":"slice_…","ordinal":0,"width_px":112,"height_px":80}]}]}]
}
```

`POST /cases/{case_id}/upload`：`multipart/form-data`，字段 `input_kind=dicom_series` 和一个 `file`，仍只支持**单个 CT DICOM Slice**；最大 20 MiB，尺寸和去标识检查在 Backend 执行。成功返回 `case_id,study_id,series_id,slice_id,status:"READY",input_expires_at`。相同键和文件摘要重放结果；已有输入换键返回 `409 CASE_ALREADY_HAS_INPUT`。创建 Case、上传、创建 Job 是三个独立动作；`READY` 只表示输入可用，不代表推理完成。错误包括 `404 CASE_NOT_FOUND`、`413 INPUT_TOO_LARGE`、`415 UNSUPPORTED_INPUT_KIND/UNSUPPORTED_DICOM`、`422 DICOM_NOT_DEIDENTIFIED/INVALID_DICOM`。

Case 由 `owner_user_id` 隔离；Job 引用该 Case 与其中的 Slice，Result 经 Job 归属该 Case，Asset 经 Result 归属该 Case。`GET /cases/{case_id}/dicom` 先检验 owner、输入保留期、存储类型与 SHA-256，再返回 `application/dicom`，`Cache-Control: private,no-store`。未授权为 404，拥有者的原图到期为 `410 INPUT_EXPIRED`，完整性失败为 503。默认原 DICOM 临时保留 7 天（配置 1–365 天）；清理器删除对象并可将 Case 标为 `EXPIRED`，匿名元数据与已有 Result 保留。云端不是长期 DICOM 归档。

## 创建与查询 Job

分类：`POST /predictions`，JSON `{"case_id":"case_…","slice_id":"slice_…","model_id":"baseline_resnet18"}`。遮挡：`POST /jobs/occlusion`，上述三字段加 `"protocol_id":"stage1-occlusion-instability-v1","scales":[16,32,64]`；`scales` 可为不重复的 16/32/64 非空子集，但必须与 ACTIVE ModelVersion 的协议一致。两者都要求 `Idempotency-Key`；响应 `{"job_id":"job_…","case_id":"case_…","status":"CREATED","status_url":"/api/v2/jobs/job_…"}`，分类额外返回 `prediction_id=job_id`。输入过期为 `410 INPUT_EXPIRED`，Case/Slice 不可见为 404，模型不可用或参数不符为 422。相同用户同一键必须有相同请求摘要，否则 409；相同键重放返回同一个 Job。

`GET /jobs/{job_id}` 返回：
```json
{
  "job_id":"job_…","kind":"OCCLUSION","case_id":"case_…",
  "status":"RUNNING","attempt_no":1,"retry_count":0,
  "lease_expire_time":"UTC ISO 8601","last_heartbeat":null,
  "failure_reason":null,"progress":null,"estimated_remaining_time_ms":null,
  "result_id":null,"error":null,"created_at":"UTC ISO 8601","finished_at":null
}
```
状态仅为 `CREATED → QUEUED → RUNNING → COMPLETED|FAILED`，租约失效或可重试失败可从 `RUNNING → QUEUED`。创建响应中的 `CREATED` 是响应固定字段；读取时可能已经被清理器推进。前端把 `CREATED/QUEUED/RUNNING` 都视为进行中，继续 `GET /jobs/{id}`；**不使用 `PENDING` 状态**。当前 `progress` 和 ETA 始终为 `null`，不可制造百分比。终态 `COMPLETED` 才有 `result_id`；`FAILED` 有 `failure_reason`、`error:{code,message}` 和 `finished_at`。Job ID 与会话所有者可在刷新后独立恢复查询；不重新创建 Job。`GET /predictions/{prediction_id}` 以相同 Job ID 查询分类摘要，返回 `prediction_id,job_id,status,result_id,prediction,error`；完成前 `prediction=null`，完成后多出 `model_version,preprocessing_version,source:"LIVE_CASE"`。完整生命周期见 [Worker 与 Job 文档](worker_api_job_lifecycle_phase5.md)。

## Result、位置和资产

只有已完成 Job 可读 Result。成功 Result 的顶层为 `result_id,job_id,status:"COMPLETED",created_at,contract_version:"2.0",source:"LIVE_CASE",case_id,slice_id,kind,model_id,model_version,preprocessing_version,protocol_id,prediction,scale_summaries,cross_scale,provenance,assets`。`model_version` 是 checkpoint SHA-256；`provenance` 含 `input_sha256,checkpoint_sha256,preprocessing_version,protocol_id`。Prediction 内含 `predicted_class` (0/1)、`class_label`、`positive_probability`、`predicted_class_confidence`、`inference_time_ms`；正类概率与预测类别置信度不能混用。分类 Result 的遮挡数组和资产数组为空。

遮挡 Result 的 `scale_summaries` 每项含 `block_size`、`stride=block_size/2`、`fill=0.5`、`baseline_positive_probability`、`median_absolute_probability_change`、`flip_rate`、`candidate_status`、`candidate_area_fraction`，以及 `response_layer`、`candidate_layer`、`comparison_grid_layer`。每个非空图层含 `asset_id,layer_kind,width,height,coordinate_space,value_min,value_max,origin,x_axis,y_axis,display_interpolation_only`。图层类型分别是 `CANDIDATE_RESPONSE`、`CANDIDATE_TOP10`、`COMPARISON_GRID`；若 `candidate_status="insufficient_positive_response"`，`candidate_layer` 和 `candidate_area_fraction` 为 `null`。图层是**模型决策响应，不是病灶标注**。`cross_scale` 是尺度对指标数组，字段 `scale_a,scale_b,spearman,top10_iou,dice,normalized_center_distance,normalized_l1,pearson`，各指标可为 `null`。

`positions` 不在 Result 详情内；用 `GET /results/{result_id}/positions?scale=16|32|64&cursor=0&limit=100` 分页。响应 `{result_id,scale,positions:[…],next_cursor:null|"整数偏移"}`，`limit` 为 1–1000。每个位置含 `x,y,block_size,baseline_positive_probability,masked_positive_probability,prediction_flip,decision_confidence_drop,candidate_response`。`scale_summaries` **没有** `position_count` 字段；每尺度数量需遍历分页计算，不能把一次验收的 729/169/36 写为固定 API 值。

`assets` 是实际保存的资产清单，每项含 `asset_id,layer_kind,width,height,coordinate_space,media_type:"image/png",asset_url`。`asset_url` 是同源 Backend 路径 `/api/v2/results/{result_id}/assets/{asset_id}`，**不是 S3 签名 URL**，不带固定 300 秒生命周期。全三尺度且每尺度三图层时会出现 9 个资产；实际数量应以 `scale_summaries` 中非空图层和 `assets` 清单为准。浏览器通过 Session Gateway 以 Cookie 发 GET；Backend 再验证 Result owner、Asset 归属、保留期、MIME、字节数和 SHA-256，返回 PNG、`private,no-store`。无权为 404，已到期为 `410 ASSET_EXPIRED`，完整性/类型异常为 503。前端不可使用私有对象键或向浏览器暴露 S3 access key、secret key、Worker 输入签名 URL。Worker 领取输入时另获最长 5 分钟的签名 DICOM URL；它与浏览器 Asset API 是不同路径。

## 已知接口偏差与限制

1. 旧 v2 冻结稿的“资产 URL 由私有存储签发、最长 300 秒”与当前用户 API 不符；当前返回鉴权 Backend 代理路径。代码中的 `signed_asset_get` 方法未被该用户路由调用。
2. 旧稿称“流式”返回资产；当前 Backend 和 Gateway 都将对象/上游响应读入内存后返回。现有上传和 Gateway 请求体也整包读取，分别有 20 MiB 和 21 MiB 限制。
3. `GET /cases` 当前返回完整 Case 树，不是仅摘要。Worker `X-Request-ID` 仅验证 UUID，错误中的 `request_id` 由 Backend 另生成，并非回显该请求头。
4. 当前系统 GPU-only MVP 工程全链路通过，但固定 CPU/GPU 派生数值一致性仍 **FAILED / OPEN**：最大偏差 `0.001049876`，固定容差 `0.0001`。这是算法/QA Open Issue，不能写成 API 功能失败或 CPU/GPU 可互换证明；不得修改 FrozenBaseline、checkpoint 或容差。
