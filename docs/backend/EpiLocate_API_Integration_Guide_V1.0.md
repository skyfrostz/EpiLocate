# EpiLocate 前后端 API 接口协议与前端接入指南 V1.0

- **文档编号：** EPI-API-FE-001
- **版本：** V1.0
- **日期：** 2026-09-29
- **文档状态：** Phase 5 GPU-only Engineering MVP 代码核对版，供前端重构与联调
- **适用 Git 基线：** 应用实现 `4d717a3753ef307ab370adeafaf5a00da4dc7af9`；开发分支当前 `f80d4cf406689cd031f993090783e281db93c4ef`；既有 API 文档 `ab36dea60e518ae86d8b9749d876d94d2102511d`
- **交接对象：** 前端负责人陈奕冰
- **项目负责人：** 钟佳桦

> **使用结论。** 当前 Vue 应通过同源 Session Gateway 使用 15 个面向浏览器的接口：3 个认证接口和 12 个 Backend v2 用户接口。Job 结果只能从已完成的 `LIVE_CASE` Result 读取。DICOM 和热图都由受授权的 Backend API 返回；浏览器不获取 Worker 凭据或私有对象存储地址。页面刷新后按 URL 中的 Case、Job、Result ID 重新查询。本文把已实现行为与重构建议分别标识。

## 修订记录

| 版本 | 日期 | 修订内容 | 状态 |
| --- | --- | --- | --- |
| V1.0 | 2026-09-29 | 根据 Phase 5 应用代码、测试、GPU MVP 验收与失败事故，整理正式前端接入合同 | 当前交接版 |

## 目录

1. 文档范围与事实边界
2. 系统调用架构
3. Base URL 与部署路径
4. 认证与 Session
5. Case API
6. DICOM 上传与读取
7. Prediction Job
8. Occlusion Job
9. Job 生命周期
10. FAILED Job 与错误处理
11. Result API
12. Asset API
13. Viewer 与 Cornerstone 数据契约
14. 前端刷新恢复
15. 前端状态模型
16. HTTP 状态与错误码
17. TypeScript 类型参考
18. 完整用户流程
19. 联调检查表
20. 当前 Open Issues
21. 不应使用的接口
22. 参考文档

## 1 文档范围与事实边界

本协议覆盖 Vue Frontend — Session Gateway — Backend v2 的浏览器调用，以及前端必须理解的 Case、Slice、Job、Result、Asset 和 Viewer 数据关系。Worker 的 Register、Heartbeat、Claim、Submit 属于独立服务边界，前端只观察 Job 状态；本文不教前端调用 Worker 接口。

本文件不定义 FrozenBaseline 数学、CUDA 实现、PostgreSQL 运维、MinIO 管理、Nginx 内部配置、Review Server、aid_site 或 Gradio 调试接口。它也不承诺临床可用性、正式生产等级或 CPU/GPU 数值等价。**事实优先级：当前代码 → Git 基线 → 测试 → 已提交验收报告 → Phase 5 文档 → 历史文档。** 旧冻结稿与代码冲突之处，以代码为准并列入第 20 章。

应用/部署代码在 `4d717a3`；`352152c` 增加最终验收和运维材料，`f80d4cf` 增加 GPU 失败事故与恢复材料。这两次后续提交没有修改 Backend、Gateway、Worker 或 Vue 业务接口代码。当前 MVP 测试入口并非正式生产环境。

## 2 系统调用架构

```text
Browser（同源 HTTPS、HttpOnly Cookie）
   │
   ▼
Vue Frontend（Route Guard、Pinia、Cornerstone）
   │  /auth/* 与用户 /api/v2/*
   ▼
Session Gateway（Session/CSRF；注入服务器端用户 Bearer）
   │
   ▼
Backend v2（身份验证、Case owner、Job/Result/Asset 授权）
   ├── PostgreSQL：用户、Case、Job、Result、Asset 元数据
   └── 私有 MinIO：临时 DICOM 与结果 PNG
         ▲
         │ Worker 输入短时签名 GET；结果提交回 Backend
         ▼
Worker Agent（独立 Worker Bearer、Claim/Heartbeat/Submit）
   └── 当前 MVP：RTX 3090 CUDA 推理
```

Browser 不直连 PostgreSQL、MinIO 管理端点或 Worker；Worker API 不走浏览器 Gateway。Backend 负责保存、授权和调度，推理在独立 Worker 运行。长期代码保留 CPU、CUDA、AUTO 设备选择；当前测试部署只启动 GPU Worker，ECS CPU Worker 未启动。

## 3 Base URL 与部署路径

**API Contract。** 用户业务 API 前缀为同源根路径 `/api/v2`，认证 API 为同源根路径 `/auth`。当前 `frontend/src/api/client.ts` 默认 `VITE_API_BASE_URL=/api/v2`；Fetch 使用 `credentials:"include"`。登录代码直接调用 `/auth/login` 等根路径。组件不要写固定域名，也不要把 SPA 的路径前缀追加在 API 前。

**当前 MVP Deployment Example。** `https://project.xbstu.com/mvp/` 是 Phase 5 GPU-only MVP **测试入口**。当前部署的 Vue 静态文件位于 `/mvp/`，Vite 构建时 `VITE_PUBLIC_BASE=/mvp/`；Router 使用 `createWebHistory(import.meta.env.BASE_URL)`。因此浏览器页面可在 `/mvp/jobs/{id}`，但 API 仍请求同源 `/api/v2/jobs/{id}`，认证仍请求 `/auth/session`。Nginx 当前把浏览器用户 API 送 Gateway、Worker API 单独送 Backend。未来迁移域名或子路径时需同时核对 Vite base、Router base、Gateway public origin 与反向代理配置；`/mvp/` 不是永久产品协议。

## 4 认证与 Session

### 4.1 真实登录流程

```text
LoginView → POST /auth/login {username,password}
          → Gateway 校验 Origin 与 Argon2 密码
          → Gateway 用服务器保存的用户 Bearer 探测 Backend GET /api/v2/cases?limit=1
          → 创建 8 小时 Session，Set-Cookie
          → 返回 {username,csrf_token}
          → 前端更新内存认证状态并进入 next 指定的受保护路由
```

| 方法与路径 | 请求 | 成功 | 失败重点 |
| --- | --- | --- | --- |
| `POST /auth/login` | JSON `username,password`；同源 `Origin` | 200 `username,csrf_token`；Set-Cookie | 401 `INVALID_CREDENTIALS`；403 `ORIGIN_REJECTED`；429 `LOGIN_RATE_LIMITED`；503 账户/Backend 不可用 |
| `GET /auth/session` | 自动携带 Cookie | 200 `username,csrf_token` | 401 `UNAUTHENTICATED`；503 `ACCOUNT_UNAVAILABLE` |
| `POST /auth/logout` | Cookie、同源 Origin、`X-CSRF-Token` | 204，撤销 Session 并清 Cookie | 401 未认证；403 Origin/CSRF 拒绝 |

登录示例（占位值不是可用凭据）：

```http
POST /auth/login HTTP/1.1
Content-Type: application/json
Origin: https://example.invalid

{"username":"user_xxx","password":"<由用户输入，不写入日志>"}
```

```json
{"username":"user_xxx","csrf_token":"<仅当前会话使用>"}
```

Gateway Cookie 名 `__Host-epilocate_demo`，属性 `HttpOnly; Secure; SameSite=Strict; Path=/`，最长 8 小时。浏览器脚本不能读取 Cookie 内容。Gateway SQLite 仅持有 Session token 哈希、到期和撤销状态；Backend 的 `user_credentials` 仅保存用户 Bearer 的 SHA-256。浏览器不得保存 Backend Bearer、Worker token、密码或 S3 凭据。POST 用户 API 和 Logout 需同源 Origin 与 `X-CSRF-Token`；GET 不要求 CSRF。登录按账户和来源 IP 限流。

### 4.2 Route Guard 和失效

当前 `router.beforeEach` 首次进入路由时调用 `GET /auth/session`；未认证则进入 `/login?next=<原路径>`。登录成功按 `next` 返回。刷新后先重新获取 Session 与 CSRF，再查业务对象。Logout、8 小时到期、管理员撤销、账户禁用都可使 Session 无效。业务 API 的任何 401 会清空前端认证内存；用户需重新登录。

**当前限制。** `GET /auth/session` 只检查 Gateway Session、账户状态和 token 文件可用性，**不会每次探测 Backend 凭据是否被撤销**。Backend 用户 Bearer 在 Session 存续中失效时，会在后续业务请求返回 401。Route Guard 当前只在本页首次加载认证状态，非每次切路由强制复验。

**错误体差异。** Gateway 显式拒绝返回 `{"code":"…"}`；Backend 业务错误返回 `code,message,retryable,request_id,details`；登录请求体不符合 Pydantic Schema 时，FastAPI 默认返回 `422 {"detail":[…]}`。前端先判断 HTTP status，再读取可选的 `code`，不能假设所有失败都有统一 `message`。

## 5 Case API

### 5.1 创建、列表与详情

| 方法与路径 | 输入 | 成功响应 | 前端用途 |
| --- | --- | --- | --- |
| `POST /api/v2/cases` | JSON `{"patient_id":null}` 或本人已有匿名 Patient ID；`Idempotency-Key` | 201 `case_id,patient_id,status:"CREATED",created_at` | 新建 Case，不自动上传或创建 Job |
| `GET /api/v2/cases?limit=20&cursor=…` | `limit` 1–100；owner 绑定不透明 cursor | 200 `items,next_cursor` | 本人列表和分页 |
| `GET /api/v2/cases/{case_id}` | URL 中公共 Case ID | 200 Case 详情 | 恢复 Case 与 Slice |

Case 详情与**当前列表项**都是完整的 Case tree；旧稿“列表只返回摘要”的描述不适用于现行代码：

```json
{
  "case_id":"case_xxx","patient_id":"pat_xxx","status":"READY",
  "created_at":"2026-09-29T00:00:00Z",
  "input_expires_at":"2026-10-06T00:00:00Z",
  "studies":[{"study_id":"study_xxx","series":[{"series_id":"series_xxx",
    "slices":[{"slice_id":"slice_xxx","ordinal":0,"width_px":512,"height_px":512}]}]}]
}
```

Backend 按 `owner_user_id` 隔离 Case，Slice 必须属于该 Case；Job 指向 Case/Slice，Result 指向 Job，Asset 指向 Result。无权 Case 与不存在 Case 都返回 `404 CASE_NOT_FOUND`，不得根据 ID 猜测其他用户资源。`CREATED` 表示 Case 尚无输入；上传后 `READY`；输入清理后可为 `EXPIRED`；`DELETING` 不对普通用户开放。列表由服务端排序并签名 cursor，前端不要自行构造。

## 6 DICOM 上传与读取

`POST /api/v2/cases/{case_id}/upload` 使用 `multipart/form-data`，表单字段 `input_kind=dicom_series` 与一个 `file`，必须带 `Idempotency-Key`。当前只接收一个已去标识的 CT DICOM Slice，文件最多 20 MiB；校验 CT SOP Class/Modality、尺寸上限、部分身份标签、私有标签和 BurnedInAnnotation。Backend 读取头部以创建 Study/Series/Slice，**不保证 Worker 环境已能解码压缩 PixelData**。一次 Case 只能上传一个输入，重复上传换键为 `409 CASE_ALREADY_HAS_INPUT`。

```http
POST /api/v2/cases/case_xxx/upload HTTP/1.1
Idempotency-Key: 8b2c8f40-2f2c-4f8c-a209-1d72ebbe9561
Content-Type: multipart/form-data; boundary=<browser-generated>

input_kind=dicom_series
file=<de-identified CT DICOM binary>
```

```json
{
  "case_id":"case_xxx","study_id":"study_xxx","series_id":"series_xxx",
  "slice_id":"slice_xxx","status":"READY",
  "input_expires_at":"2026-10-06T00:00:00Z"
}
```

`DICOM_NOT_DEIDENTIFIED` 由 **Backend `services/cases.py`** 产生，HTTP 422；它不是 Gateway 登录错误，也不是 Worker 推理错误。用户曾见的英文“DICOM not deidentified”来自 Backend 默认 `message`。前端应安全地提示“请上传已去标识的 CT DICOM”，不得展示或记录被拒绝文件的患者字段。其他常见错误：413 `INPUT_TOO_LARGE`，415 `UNSUPPORTED_INPUT_KIND`/`UNSUPPORTED_DICOM`，422 `INVALID_DICOM`/`INVALID_DICOM_DIMENSIONS`，409 `CASE_ALREADY_HAS_INPUT`，404 `CASE_NOT_FOUND`。同一上传键、同一文件 SHA 的重放可返回原结果；新文件配旧键是 409。

`GET /api/v2/cases/{case_id}/dicom` 在确认 owner、保留期、媒体类型和 SHA-256 后返回 `application/dicom` Blob，供 Cornerstone 文件管理器使用。原图默认临时保留 7 天（可配置 1–365 天），到期后该 owner 得到 `410 INPUT_EXPIRED`；Case 元数据与已完成 Result 仍可用。云端不是长期 DICOM 归档。读取接口不签发浏览器 S3 URL。

## 7 Prediction Job

`POST /api/v2/predictions` 接受 JSON `case_id,slice_id,model_id` 和 `Idempotency-Key`，返回 HTTP 202：

```json
{
  "job_id":"job_xxx","prediction_id":"job_xxx","case_id":"case_xxx",
  "status":"CREATED","status_url":"/api/v2/jobs/job_xxx"
}
```

示例请求：`{"case_id":"case_xxx","slice_id":"slice_xxx","model_id":"baseline_resnet18"}`。Backend 仅接受该 Case 内有效 Slice 和已登记 ACTIVE ModelVersion；新 Job 固定模型、协议和输入哈希。响应 `CREATED` 是创建时值，查询可能已推进到 `QUEUED` 或 `RUNNING`。前端应保存 `job_id` 到路由 `/jobs/{id}`，调用 `GET /api/v2/jobs/{id}` 轮询，直到 `COMPLETED` 或 `FAILED`。也可用 `GET /api/v2/predictions/{prediction_id}` 取分类摘要，`prediction_id` 与 Job ID 相同；未完成时 `prediction:null`。成功 Result 才标记 `source:"LIVE_CASE"`，不接入 `/api/v1` Mock。

创建失败可能为 404 Case/Slice 不可见、410 `INPUT_EXPIRED`、422 `MODEL_UNAVAILABLE` 或 409 `IDEMPOTENCY_CONFLICT`。重复提交时沿用同一幂等键；不要因 HTTP 超时立即生成第二个键。

## 8 Occlusion Job

`POST /api/v2/jobs/occlusion` 接受 `case_id,slice_id,model_id,protocol_id,scales` 与 `Idempotency-Key`。当前协议接受不重复且非空的 `16/32/64` 子集，且 `protocol_id` 必须与 ACTIVE ModelVersion 一致；当前全尺度 UI 发送 `[16,32,64]`。202 返回 `job_id,case_id,status:"CREATED",status_url`，没有 `prediction_id`。查询状态使用同一个 `GET /api/v2/jobs/{job_id}`。

完成后 Result 含 `prediction`、`scale_summaries`、`cross_scale` 和 Asset 清单，位置记录另走分页接口。每尺度摘要有 block size、stride、fill、基线概率、中位绝对变化、flip rate、候选状态与可为空的三层图。全三尺度且三层均有效时会有 9 张 PNG；某尺度候选响应不足时 `candidate_layer=null`，资产数会减少。**729/169/36** 是当前 FrozenBaseline MVP 对验收输入测得的位置数量，可作示例，**不是 API 固定字段或所有输入的永久常量**。前端若需要计数，分页取完对应尺度的 `positions` 后再统计。

## 9 Job 生命周期

```text
CREATED ──Backend 验证──▶ QUEUED ──Worker Claim──▶ RUNNING
   │                         │                      ├──有效结果──▶ COMPLETED
   └──校验失败──▶ FAILED      └──输入过期──▶ FAILED    ├──可重试故障──▶ QUEUED
                                                  └──不可重试/次数用尽──▶ FAILED
```

上述是**数据库 Job 状态**；`CLAIMED` 是 Attempt 的内部 outcome，不是对前端公开的 Job 状态。`PENDING`、`CANCELLED` 也不是 v2 Job 状态，当前没有运行中 cancel API。

| Job 状态 | 用户可见含义 | UI 动作 |
| --- | --- | --- |
| `CREATED` | 请求已保存，待 Backend 验证 | 显示等待并继续查询 |
| `QUEUED` | 可领取或重试退避中 | 继续查询，不推算进度 |
| `RUNNING` | Worker 持有有效 Attempt/lease | 继续查询；可显示最近心跳 |
| `COMPLETED` | 唯一成功 Result 已保存 | 按 `result_id` 打开 Result |
| `FAILED` | 终态失败，无成功 Result | 显示安全错误码和恢复动作 |

Worker 领取使 Job 从 `QUEUED` 到 `RUNNING`，首次 Attempt 90 秒 lease；15 秒一次 Heartbeat 续租，节点 45 秒无心跳停止新派单；后端清理器回收过期 Attempt。白名单临时故障可延迟重派，最多 2 次重试、3 次领取；Job 的 `retry_count` 首次为 0。用户 API 的 `progress` 和 `estimated_remaining_time_ms` 当前均为 `null`，UI 不能用轮询次数伪造百分比。刷新页面后按 URL Job ID 再查，不重新提交或取消 Job。

`GET /api/v2/jobs/{job_id}` 示例：
```json
{
  "job_id":"job_xxx","kind":"OCCLUSION","case_id":"case_xxx",
  "status":"RUNNING","attempt_no":1,"retry_count":0,
  "lease_expire_time":"2026-09-29T00:01:30Z","last_heartbeat":null,
  "failure_reason":null,"progress":null,"estimated_remaining_time_ms":null,
  "result_id":null,"error":null,
  "created_at":"2026-09-29T00:00:00Z","finished_at":null
}
```

## 10 FAILED Job 与错误处理

### 10.1 当前 API 已提供

`GET /api/v2/jobs/{id}` 对**存在且属于当前用户的失败 Job 仍返回 HTTP 200**，其中 `status:"FAILED"`、`result_id:null`、`failure_reason` 和 `error:{code,message}` 表示失败。它不是 HTTP 500，也不会生成成功 Result。失败对象示例：

```json
{
  "job_id":"job_xxx","kind":"PREDICTION","case_id":"case_xxx",
  "status":"FAILED","attempt_no":1,"retry_count":0,
  "lease_expire_time":null,"last_heartbeat":null,
  "failure_reason":"INFERENCE_FAILED",
  "progress":null,"estimated_remaining_time_ms":null,
  "result_id":null,
  "error":{"code":"INFERENCE_FAILED","message":"Job failed."},
  "created_at":"2026-09-29T00:00:00Z","finished_at":"2026-09-29T00:00:15Z"
}
```

`failure_reason`/`error.code` 是稳定脱敏错误码；`error.message` 可能非常笼统。Job 对象目前**没有** `retryable`、`user_action`、`public_detail`、traceback 或插件名字段；不能把普通 HTTP 错误体里的 `retryable` 误用于 Job 内嵌 `error`。

### 10.2 真实事故与当前 UX 限制

2026-09-29 两个历史 GPU Job 因 Worker Python 环境缺少 JPEG Lossless 解码依赖而返回 `INFERENCE_FAILED` / `Job failed.`；两者停在 `FAILED`、无 Result、没有自动重试。Backend 上传阶段只核对 DICOM 头，因此 Case 可以是 `READY`，但 Worker 像素解码仍可能失败。补齐运行环境依赖后，在**原 Case 上新建的** Prediction/Occlusion Job 成功；历史失败记录没有改写。这证明故障恢复，不改变 API Schema。当前 `JobDetailView` 仅显示 `error.message`，所以用户看不到可安全展示的失败分类。这是 **CURRENT LIMITATION**，不是某个未被文档化的详细错误响应。

**推荐重构，非当前 API 新字段：** 根据稳定 `failure_reason`/`error.code` 做前端安全映射。例如 `INPUT_EXPIRED` 提示创建新 Case 并重传；`INFERENCE_FAILED` 提示推理未完成、保留 Job ID 供支持人员排查，不建议重复上传或承诺必然重试；`LEASE_EXPIRED` 若 Job 已回到 `QUEUED` 则继续轮询。用本地文案区分“可由用户修复”“等待服务恢复”“联系维护者”，不展示 Worker traceback、签名 URL、文件路径、患者元数据。若未来需要 `public_detail` 或 `suggested_action`，必须另定 Backend 契约并验证脱敏后再接入。

### 10.3 HTTP 错误与 Job 失败要分开

HTTP 401/403/404/410/422 表示这次读取或创建请求失败；`status=FAILED` 则是一个成功读取的 Job 业务终态。客户端请求超时或断网，不代表服务器 Job 已失败；继续凭 ID 查询即可。客户端轮询停止也不改变服务器状态。Asset 的 410 或 503 不会把已完成 Job 自动改成 FAILED。

## 11 Result API

`GET /api/v2/results/{result_id}` 仅对拥有该 Job、且 Job 已 `COMPLETED` 的用户可读。前端只有在 Job `COMPLETED` 且 `result_id` 非空、Result `status:"COMPLETED"`、`source:"LIVE_CASE"`、`contract_version:"2.0"` 与所请求 ID 一致时，才进入展示。Result 详情不含整个 `positions` 数组。

| 字段 | 类型与含义 |
| --- | --- |
| `result_id,job_id,case_id,slice_id` | 匿名公共 ID；用来关联资源 |
| `kind,status,source,contract_version` | `PREDICTION|OCCLUSION`、`COMPLETED`、`LIVE_CASE`、`2.0` |
| `model_id,model_version` | 模型标识；`model_version` 为 checkpoint SHA-256 |
| `preprocessing_version,protocol_id` | 输入预处理与遮挡协议版本 |
| `prediction` | 分类结果，遮挡 Result 也包含 |
| `scale_summaries,cross_scale` | 遮挡尺度及跨尺度指标；分类 Result 为空数组 |
| `provenance` | `input_sha256,checkpoint_sha256,preprocessing_version,protocol_id` |
| `assets,created_at` | 资产描述数组、Result 创建时间 |

`prediction` 包含 `predicted_class` (0/1)、`class_label`、`positive_probability`、`predicted_class_confidence`、`inference_time_ms`。正类概率与被预测类别的置信度是不同数值。遮挡摘要的候选图层可能为 `null`，`candidate_status:"insufficient_positive_response"` 时不可伪造候选病灶。`cross_scale` 记录尺度对及可能为空的统计指标。

`GET /api/v2/results/{result_id}/positions?scale=16&cursor=0&limit=100` 仅适用于遮挡 Result；`scale` 为 16、32 或 64，`cursor` 是非负整数偏移，`limit` 为 1–1000。返回 `{result_id,scale,positions,next_cursor}`，下一页 cursor 为数字字符串或 `null`。位置记录字段是 `x,y,block_size,baseline_positive_probability,masked_positive_probability,prediction_flip,decision_confidence_drop,candidate_response`。Result 摘要**没有** `position_count` 字段，前端需要时自行累计分页数量。

## 12 Asset API

**当前实现与旧稿不同。** `GET /api/v2/results/{result_id}` 的 `assets[]` 含 `asset_id,layer_kind,width,height,coordinate_space,media_type,asset_url`，其中 `asset_url` 是同源鉴权 Backend 路径：

```text
/api/v2/results/{result_id}/assets/{asset_id}
```

它不是给浏览器的 300 秒 S3 Signed URL，也不含 MinIO 私有对象键。当前 `ApiClient.getResultAsset` 用 Result ID 和 Asset ID 构造同一路径，带 Session Cookie 取 `image/png` Blob，然后创建本地 `objectURL`；切换和卸载时撤销 Blob URL。直接在 `<img>` 使用受保护 URL 若不经过该客户端封装，也要确保同源 Cookie 与错误处理符合浏览器行为。没有为浏览器提供通用 MinIO URL。

Backend 对 Asset 请求再次验证用户 → Job/Result → Asset 归属，以及保留期、媒体类型、字节长度和 SHA-256。无权/不存在为 404，拥有者的 Asset 到期为 `410 ASSET_EXPIRED`，存储类型或完整性异常为 503。Asset GET 返回 `Content-Type:image/png`、`Cache-Control:private,no-store`；当前 Backend 与 Gateway 会读入对象/上游内容后再响应，不是完整端到端流式通道。原始 DICOM 的浏览器读取见第 6 章，走独立的鉴权 Case 路径。Worker 领取输入时所用的最长 300 秒签名 DICOM GET，只给 Worker，不给浏览器。

## 13 Viewer 与 Cornerstone 数据契约

当前 Viewer 把 `GET /cases/{id}/dicom` 返回的 Blob 包装为 File，交给 Cornerstone3D 本地文件管理器。Case tree 提供 `slice_id,width_px,height_px`；Result 提供同一 `case_id/slice_id`、`provenance.input_sha256`、模型与协议版本；`scale_summaries` 给每尺度图层；`assets[]` 给 Asset 清单。前端先核对这些 ID 和元数据，再请求 PNG 并核对解码尺寸。

**已实现的叠加闸门：** 只对已完成的 `LIVE_CASE` 遮挡 Result 生效；模型 ID、checkpoint、预处理、协议必须匹配 `frontend/src/viewer/geometry.ts` 已审计的单切片映射；DICOM Blob 的 SHA-256 必须等于 Result provenance；选定图层必须属于所选尺度且与 Asset 描述的 `layer_kind,coordinate_space,width,height,media_type` 一致。响应与候选图层为 `ALGORITHM_224`、224×224；比较图为 `COMPARISON_14`、14×14，仅用于显示插值；方向字段为 `TOP_LEFT_PIXEL_EDGE/RIGHT/DOWN`。候选图层在 `candidate_status` 非 valid 时不可用于叠加。

原图像素尺寸来自 Case Slice，模型空间为 224×224。Cornerstone 当前 StackViewport 根据 `imageData.indexToWorld([x-0.5,y-0.5,0])` 与 `worldToCanvas` 对像素边界建立画布映射，缩放/平移时更新；不要用简单 CSS 层叠假设原图永远是 224×224。几何闸门失败时仍可独立显示合规热图，但禁用 CT Overlay。它只验证二维单 Slice 像素关系，不证明三维配准。Heatmap 表示模型决策响应，**不是病灶金标准或临床诊断**。

## 14 前端刷新恢复

```text
刷新受保护 URL
  → GET /auth/session（恢复用户名与 CSRF）
  → /cases/:id：GET Case；如有输入，再 GET Case DICOM
  → /jobs/:id：GET Job；非终态继续轮询
  → /results/:id：GET Result → 并行 GET Case / DICOM → 核 SHA
                 → GET 当前图层 PNG → 核图层与尺寸 → 恢复安全的 Viewer 偏好
```

刷新后不要重新 POST 创建 Case/Job，也不要保存或复用上一页的 Blob URL。当前前端在 Job 页以路由 ID 每 3 秒查询，客户端 10 分钟超时或连续 3 次错误就停，但服务端任务继续运行；“重新查询”可继续按原 ID 检索。Result 页按 URL 的 Result ID 重新加载，`sessionStorage` 只保存尺度、图层、Overlay 开关、透明度和相机视角偏好；真正数据再次受授权读取，并且只有重新通过 DICOM SHA、版本和资产几何检查才恢复叠加。当前 Phase 5 浏览器 E2E 已验证这一刷新路径。DICOM 已过期时仍可查询 Result 与独立图层，但 CT 与叠加无法恢复。

## 15 前端状态模型

| 域 | CURRENT IMPLEMENTATION | RECOMMENDED REDESIGN |
| --- | --- | --- |
| AuthState | `auth/session.ts` 内存 reactive：`username,csrfToken,loaded,error`；Cookie 由浏览器持有 | 统一 401 响应与登录跳转；永不持久化凭据 |
| CaseList / CurrentCase | Pinia `cases`：items、cursor、selected、加载/错误 | 以服务端 Case 列表/详情为真相；账号变化时清缓存 |
| CurrentJob | Pinia `jobs`：byId、currentId、轮询/超时/错误 | URL 保持 Job ID；区分 HTTP 失败与业务 `FAILED` |
| PredictionResult / OcclusionResult | Pinia `results` 只有一个 current Result 与当前 Asset Blob URL | 按 `kind` 派生视图；校验来源与版本；切换时撤销 Blob URL |
| ViewerState / OverlayState | Result 页 refs 与 `sessionStorage` 保存视图偏好；Case/Result/DICOM 再读 | 视图偏好按账户和 Result 隔离，恢复前强制通过几何与权限检查 |

**当前缺口：** `clearSession()` 会清认证与部分 Viewer 偏好，但不统一调用 Case/Job/Result Pinia store 的 `reset/clear`。业务 API 401 会触发 `auth.username` 置空，`App.vue` 监听后通常立即跳登录；内存中的 Case/Job 缓存仍可能残留至页面卸载、重新加载或手动清理。重构应在注销、401、账户切换时统一清敏感 store；这是前端建议，不是 Backend 当前接口的附加保证。当前 `frontend/src/api/types.ts` 把 CaseList 的 items 写为摘要类型，而 Backend 实返完整树；`ResultAsset` 类型未列出实返的 `asset_url`。重构时以第 5、12 章实返字段校正 TypeScript 类型。

## 16 HTTP 状态与错误码

| HTTP 状态 | 当前错误体或响应 | 含义 | 前端动作 |
| --- | --- | --- | --- |
| 200 | JSON、DICOM 或 PNG；FAILED Job 也是 200 JSON | 读取成功 | 再按 `job.status` 判断业务终态 |
| 201 | Case 创建或 DICOM 上传 JSON | 资源已创建 | 保存 Case/Slice ID |
| 202 | Job 创建 JSON，状态字段 `CREATED` | 已受理，不代表完成 | 跳 Job 页并轮询 |
| 204 | Logout；Worker 无任务 Claim（前端不调用） | 无响应体 | Logout 后清前端状态 |
| 400 | 当前列出的用户业务路由没有固定 400 错误码 | 可能来自网关/HTTP 层，非稳定业务契约 | 显示安全通用错误，记录状态 |
| 401 | Gateway `{"code":"UNAUTHENTICATED"}` 或 Backend 标准错误体 | Session/凭据缺失或失效 | 清状态、回登录，保留安全的目标路由 |
| 403 | Gateway Origin/CSRF 拒绝；Worker 禁用属于独立边界 | 请求不被允许 | 检查同源/CSRF；不要盲重试 |
| 404 | `CASE_NOT_FOUND/JOB_NOT_FOUND/RESULT_NOT_FOUND/ASSET_NOT_FOUND` 等 | 不存在或无权访问，不可区分 | 显示“不可访问或不存在” |
| 409 | `IDEMPOTENCY_CONFLICT/CASE_ALREADY_HAS_INPUT` 等 | 请求与已有状态冲突 | 沿用原 key 核对请求；不要自动新建 |
| 410 | `INPUT_EXPIRED/ASSET_EXPIRED` | 有权资源已过保留期 | DICOM 需新 Case/重传；资产提示不可用 |
| 413 | `INPUT_TOO_LARGE/REQUEST_TOO_LARGE` | Backend 20 MiB 或 Gateway 21 MiB 上限 | 阻止超限文件 |
| 415 | `UNSUPPORTED_DICOM/UNSUPPORTED_INPUT_KIND` | 格式不支持 | 请用户更换符合合同的 DICOM |
| 422 | Backend `INVALID_REQUEST` 或业务码；Gateway 登录校验可为 `{"detail":[…]}` | 参数、去标识或结果查询有误 | 用 status+可选 code 映射脱敏文案 |
| 429 | Gateway `LOGIN_RATE_LIMITED` | 登录限流 | 等待后再试 |
| 500 | 无稳定公开 500 业务错误 schema 承诺 | 内部/反向代理异常 | 通用错误、保留 Job ID，勿暴露响应原文 |
| 503 | Backend `STORAGE_NOT_CONFIGURED` 等或 Gateway `BACKEND_UNAVAILABLE` | 服务或存储不可用 | 可稍后查询原 ID；勿假定 Job 失败 |

Backend 明确抛出的业务错误通常为 `{"code":"STABLE_CODE","message":"脱敏说明","retryable":false,"request_id":"uuid","details":{}}`；`retryable` 只描述**这次 HTTP 请求**的重发提示，不是 Job 业务重试决定。Gateway 显式错误只有 `code`，校验错误可能只有 `detail`，反向代理可能返回非 JSON。解析器必须允许缺字段和网络超时。所有错误展示都不应包含患者数据、Bearer、S3 签名查询参数或服务器路径。

## 17 TypeScript 类型参考

以下类型描述**当前 HTTP 响应**，为陈奕冰重构时的起点；不会更名蛇形字段。日期是 UTC ISO 8601 字符串。实际实现应对非 JSON、缺字段和网关校验错误作运行时防护。

```ts
type CaseStatus = 'CREATED' | 'READY' | 'EXPIRED' | 'DELETING'
type JobStatus = 'CREATED' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
type JobKind = 'PREDICTION' | 'OCCLUSION'
type Scale = 16 | 32 | 64

interface SessionUser {
  username: string
  csrf_token: string
}
interface BackendApiError {
  code: string
  message: string
  retryable: boolean
  request_id: string
  details: Record<string, unknown>
}
// Gateway 显式错误只有 code；登录参数校验可能只有 detail。
type GatewayError = { code: string } | { detail: unknown[] }

interface Slice {
  slice_id: string
  ordinal: number
  width_px: number
  height_px: number
}
interface Series { series_id: string; slices: Slice[] }
interface Study { study_id: string; series: Series[] }
interface Case {
  case_id: string
  patient_id: string
  status: CaseStatus
  created_at: string
  input_expires_at: string | null
  studies: Study[]
}
interface CaseList {
  items: Case[] // 当前 Backend 实返完整 tree
  next_cursor: string | null
}
interface CreatedCase {
  case_id: string
  patient_id: string
  status: 'CREATED'
  created_at: string
}
interface UploadedCase {
  case_id: string
  study_id: string
  series_id: string
  slice_id: string
  status: 'READY'
  input_expires_at: string
}
interface AcceptedJob {
  job_id: string
  case_id: string
  status: 'CREATED'
  status_url: string
  prediction_id?: string // 仅 POST /predictions
}
interface JobError { code: string; message: string }
interface Job {
  job_id: string
  kind: JobKind
  case_id: string
  status: JobStatus
  attempt_no: number
  retry_count: number
  lease_expire_time: string | null
  last_heartbeat: string | null
  failure_reason: string | null
  progress: number | null // 当前为 null
  estimated_remaining_time_ms: number | null // 当前为 null
  result_id: string | null
  error: JobError | null
  created_at: string
  finished_at: string | null
}
interface PredictionValues {
  predicted_class: 0 | 1
  class_label: 'negative' | 'positive'
  positive_probability: number
  predicted_class_confidence: number
  inference_time_ms: number
}
interface PredictionJob {
  prediction_id: string
  job_id: string
  status: JobStatus
  result_id: string | null
  prediction: (PredictionValues & {
    model_version: string
    preprocessing_version: string
    source: 'LIVE_CASE'
  }) | null
  error: JobError | null
}
```

```ts
type LayerKind = 'CANDIDATE_RESPONSE' | 'CANDIDATE_TOP10' | 'COMPARISON_GRID'
type CoordinateSpace = 'ALGORITHM_224' | 'COMPARISON_14' | 'RAW_PIXEL_EDGE'
interface HeatmapLayer {
  asset_id: string
  layer_kind: LayerKind
  width: number
  height: number
  coordinate_space: CoordinateSpace
  value_min: number
  value_max: number
  origin: 'TOP_LEFT_PIXEL_EDGE'
  x_axis: 'RIGHT'
  y_axis: 'DOWN'
  display_interpolation_only: boolean
}
interface ScaleSummary {
  block_size: Scale
  stride: number
  fill: number
  baseline_positive_probability: number
  median_absolute_probability_change: number
  flip_rate: number
  candidate_status: 'valid' | 'insufficient_positive_response'
  candidate_area_fraction: number | null
  response_layer: HeatmapLayer | null
  candidate_layer: HeatmapLayer | null
  comparison_grid_layer: HeatmapLayer | null
}
interface CrossScaleMetric {
  scale_a: Scale
  scale_b: Scale
  spearman: number | null
  top10_iou: number | null
  dice: number | null
  normalized_center_distance: number | null
  normalized_l1: number | null
  pearson: number | null
}
interface Asset {
  asset_id: string
  layer_kind: LayerKind
  width: number
  height: number
  coordinate_space: CoordinateSpace
  media_type: 'image/png'
  asset_url: string // 同源 Backend 代理路径，不是 S3 URL
}
interface ResultBase {
  result_id: string
  job_id: string
  case_id: string
  slice_id: string
  status: 'COMPLETED'
  contract_version: '2.0'
  source: 'LIVE_CASE'
  model_id: string
  model_version: string
  preprocessing_version: string
  protocol_id: string
  prediction: PredictionValues
  provenance: {
    input_sha256: string
    checkpoint_sha256: string
    preprocessing_version: string
    protocol_id: string
  }
  created_at: string
}
interface PredictionResult extends ResultBase {
  kind: 'PREDICTION'
  scale_summaries: []
  cross_scale: []
  assets: []
}
interface OcclusionResult extends ResultBase {
  kind: 'OCCLUSION'
  scale_summaries: ScaleSummary[]
  cross_scale: CrossScaleMetric[]
  assets: Asset[]
}
type Result = PredictionResult | OcclusionResult
interface OcclusionPosition {
  x: number
  y: number
  block_size: Scale
  baseline_positive_probability: number
  masked_positive_probability: number
  prediction_flip: boolean
  decision_confidence_drop: number
  candidate_response: number
}
interface PositionsPage {
  result_id: string
  scale: Scale
  positions: OcclusionPosition[]
  next_cursor: string | null
}
```

`PredictionResult` 的空数组类型用于表达当前后端返回的空集合，不意味着 TypeScript 编译器可仅凭原始 JSON 保证内容正确。实际客户端在边界仍要核验 `kind`、来源、版本、ID 与资产归属。当前 Vue 类型定义尚未把 CaseList items 与 Asset 的 `asset_url` 完全对齐；这是重构待修正的类型差异，**不是新 Backend 字段**。

## 18 完整用户流程

| 步骤 | 浏览器动作 | API 与成功判断 |
| --- | --- | --- |
| 1 登录 | 用户提交账户信息 | `POST /auth/login` → 200，Session Cookie/CSRF |
| 2 列表 | 进入病例中心 | `GET /api/v2/cases` → 本人 items |
| 3 新建 | 创建匿名 Case | `POST /api/v2/cases` → 201 `case_id` |
| 4 上传 | 单个已去标识 DICOM | `POST /api/v2/cases/{id}/upload` → 201 `slice_id,status=READY` |
| 5 分类 | 创建 Prediction Job | `POST /api/v2/predictions` → 202 `job_id` |
| 6 等待 | 查询分类状态 | `GET /api/v2/jobs/{id}` → `COMPLETED` 与 `result_id` |
| 7 遮挡 | 创建 16/32/64 Job | `POST /api/v2/jobs/occlusion` → 202 `job_id` |
| 8 等待 | 查询遮挡状态 | `GET /api/v2/jobs/{id}` → `COMPLETED` 与 `result_id` |
| 9 展示 | 读 Result、Case、DICOM、图层 | `GET /results/{id}`、`GET /cases/{id}`、`GET /cases/{id}/dicom`、`GET /results/{id}/assets/{asset_id}` |
| 10 刷新 | 重新建立前端内存状态 | `GET /auth/session`，然后按 URL ID 重查所有必要资源 |

任何步骤失败都按第 10、16 章处理；Case `READY`、Job `COMPLETED` 与 Result `LIVE_CASE` 是三个不同判断，不得跳过。流程须使用去标识或 synthetic 输入。

## 19 前端联调检查表

以下是**待前端重构验收的检查项**，不是声称本轮全部重新执行：

- [ ] Login：同源 Origin、200 Session 与 Cookie；错误密码 401，限流 429。
- [ ] Session restore：刷新受保护页后 `GET /auth/session` 恢复 CSRF。
- [ ] Logout：204 后清内存、敏感 Pinia 缓存与 Viewer 偏好。
- [ ] Create Case：201、匿名 ID、同 key 重放。
- [ ] Case List：分页、本人范围、完整 Case tree。
- [ ] Case Detail：study/series/slice 与 URL Case ID 一致。
- [ ] Upload DICOM：单文件、20 MiB、READY、Slice ID、幂等。
- [ ] Invalid DICOM：422/415 不泄露文件内容。
- [ ] De-identification failure：Backend `DICOM_NOT_DEIDENTIFIED` 安全文案。
- [ ] Prediction：202→轮询→`COMPLETED`→`LIVE_CASE`。
- [ ] Prediction failure：HTTP 200 的 `FAILED` Job 展示安全错误码，无 Result。
- [ ] Occlusion：请求 16/32/64，实际尺度与图层来自响应。
- [ ] Occlusion failure：保留 Job ID，展示状态与安全恢复建议。
- [ ] Asset loading：Cookie、PNG MIME、404/410/503 与 Blob URL 清理。
- [ ] Viewer：DICOM Blob、Slice identity、原始尺寸与 SHA 校验。
- [ ] Heatmap overlay：版本、尺度、方向、图层清单与 Cornerstone 坐标闸门。
- [ ] Refresh：Job、Result、DICOM、当前图层与安全 View 偏好恢复。
- [ ] Session expiration：401 清认证与敏感缓存、回登录。
- [ ] Network failure：超时/断网不误报 Job FAILED；凭 ID 重试查询。
- [ ] Cross-user ID：Case、Job、Result、Asset 不可越权读取。

## 20 当前 Open Issues

| 序号 | 当前事实与影响 | 建议后续处理 |
| --- | --- | --- |
| 1 | Gateway 显式错误只有 `code`，Backend 有完整五字段错误体 | 前端容错解析；将来统一契约需另立变更 |
| 2 | 登录 Pydantic 校验可返回 `422 detail` | 前端按 status 优先处理，不假定 `code` |
| 3 | Gateway 请求和上游响应、Backend 上传/资产读取存在整包内存缓冲 | 容量验证与流式实现另列工程任务 |
| 4 | `GET /auth/session` 不每次复验 Backend token | 业务 API 401 清态；如需强实时失效需另设计 |
| 5 | 当前没有按 Case 列举 Job 的专门路由 | 依靠 Job/Result 深链；需求确认后再设计新 API |
| 6 | FAILED Job 页面当前只显示 `Job failed.` 等通用消息 | 前端用稳定错误码映射安全分类和建议动作 |
| 7 | Worker 对未知异常缺少安全异常类型/traceback 观测 | 改日志前先做脱敏与签名 URL 屏蔽 |
| 8 | 合法 JPEG Lossless DICOM 可在 READY 后因 Worker 缺解码依赖失败 | 部署预检覆盖支持的 Transfer Syntax；不要用 READY 代表像素解码成功 |
| 9 | 前端登出/401 尚未统一清 Case/Job/Result Pinia 缓存 | UI 重构时清理所有敏感 store |
| 10 | CaseList/Asset TypeScript 声明落后于实返字段 | 对齐第 17 章，并加响应边界验证 |
| 11 | CPU/GPU 固定数值一致性 **FAILED / OPEN**：最大派生偏差 `0.0010498762130737305`，容差 `0.0001` | 算法/QA 单独调查；不改冻结模型或容差；不写成 API 功能失败或 PASS |

当前 GPU-only Full-Chain MVP 的真实 Prediction、三尺度 Occlusion、Result/资产持久化与浏览器刷新工程链路已经验证通过；这不等于生产、临床或 CPU/GPU 数值等价验收。Worker 人工运行、独立备份/恢复、静态加密与容量仍是部署事项，不应混进浏览器 API Contract。

## 21 不应使用的接口

陈奕冰本轮 Vue 重构只接入本文件列出的 `/auth` 和用户 `/api/v2` 路由。不要直接调用 aid_site、Review Server、Gradio debug、MinIO 管理、PostgreSQL 或 `/api/v2/workers/*`；它们属于不同应用或服务身份边界。也不要引入另一套认证中心的 AppID/AppSecret、OAuth code exchange、Webhook、Challenge 或第三方 HMAC OpenAPI 流程；Phase 5 浏览器认证是 Gateway Session 与后端预配用户凭据。未来新路由必须有独立实现、测试和契约变更后才能接入。

## 22 参考文档与核验位置

| 资料 | 用途 |
| --- | --- |
| [Frontend Integration Guide Phase 5](frontend_integration_guide_phase5.md) | Vue 当前调用和刷新恢复 |
| [Backend API Contract Phase 5](backend_api_contract_phase5.md) | 用户路由与字段 |
| [Session Gateway Contract Phase 5](session_gateway_contract_phase5.md) | Cookie、CSRF、错误体 |
| [Worker API / Job Lifecycle Phase 5](worker_api_job_lifecycle_phase5.md) | Job 状态、Worker 边界 |
| [GPU Full Chain MVP Report](../phase5/gpu_full_chain_mvp_report.md) | 工程 MVP 与数值限制 |
| GPU Final Handoff Report（Phase 5 分支，提交 `352152ce95fc26eb2dc0a4c309521d50486472ba`） | 最终浏览器与持久化验收 |
| GPU Failed Job Incident Report（Phase 5 分支，提交 `f80d4cf406689cd031f993090783e281db93c4ef`） | JPEG Lossless 故障与恢复 |
| [Engineering Journal](../project/ENGINEERING_JOURNAL.md) | 工程过程记录；不作为本协议字段来源 |
| [Project Context](../project/PROJECT_CONTEXT.md) | 项目上下文；不作为本协议字段来源 |

**代码核对：** `backend_v2/api/app.py`、`backend_v2/services/cases.py`、`backend_v2/services/jobs.py`、`backend_v2/services/storage.py`、`session_gateway/app.py`、`frontend/src/api/client.ts`、`frontend/src/auth/session.ts`、`frontend/src/router/index.ts`、`frontend/src/stores/`、`frontend/src/views/`、`frontend/src/viewer/geometry.ts`、`worker/client.py`、`worker/agent.py`。本文件描述实现，不引用私人凭据、患者数据或原始影像。
