# Frontend Integration Guide — Phase 5 Backend / Gateway

**交接对象：** 前端负责人 B（陈奕冰）。**事实基线：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。先读此文，再读 [Backend API Contract](backend_api_contract_phase5.md) 与 [Session Gateway Contract](session_gateway_contract_phase5.md)；Worker 细节只需了解 [Job lifecycle](worker_api_job_lifecycle_phase5.md)。本指南据 `frontend/src/api/client.ts`、`auth/session.ts`、`router/index.ts`、Pinia stores、`ResultDetailView.vue`、`viewer/geometry.ts` 及 Backend/Gateway 代码核对，供 Vue UI 重构使用。

## 路径配置与浏览器调用

- API 合同基址是同源根路径 `/api/v2`，当前 `ApiClient` 默认即此值，可由 `VITE_API_BASE_URL` 配置。登录基址是同源 `/auth`，当前前端直接请求 `/auth/login`、`/auth/session`、`/auth/logout`。组件不要拼接固定域名。
- SPA 静态入口可部署在子路径。Vue Router 使用 `createWebHistory(import.meta.env.BASE_URL)`，Vite 构建使用 `VITE_PUBLIC_BASE`。**SPA base 与 API base 是两个配置**：部署到 `/mvp/` 时 SPA 路径带 `/mvp/`，API/Auth 仍是同源根 `/api/v2`、`/auth`。如果未来反向代理改动，先改部署配置与 API base，勿把当前测试路径写进组件或永久契约。
- Phase 5 当前 MVP 测试入口 `https://project.xbstu.com/mvp/`，仅作为**当前部署示例**，不是正式生产。该部署 Nginx 使浏览器用户 API 经过 Gateway，Worker API 直达 Backend。ECS CPU Worker 当前未启动，线上演示只含 GPU Worker；应用仍保留 CPU/CUDA/AUTO 模式。
- 开发 Vite 代理 `/auth` 与 `/api/v2` 到 `API_PROXY_TARGET`，必须指向 Gateway 的浏览器入口；不在 Vite 注入用户/Worker token。真实 Cookie/Origin 流程需在 HTTPS 同源入口验证。

## Session 与 Route Guard

页面首次进入受保护路由，调用 `GET /auth/session`，带 `credentials:"include"`；200 保存 `username` 与 `csrf_token` 到内存认证状态，401 清空并重定向 `/login?next=<原路由>`。登录 `POST /auth/login` 送 `username,password`，成功即得到同样 JSON，Cookie 由浏览器自动保管。所有用户业务 fetch 都 `credentials:"include"`；POST 设置 `X-CSRF-Token` 和需要的 `Idempotency-Key`。退出 `POST /auth/logout` 同样带 CSRF，204 后清内存与本地视图偏好。

Route Guard 不能把 Pinia 是否有 Case/Job、或 sessionStorage 是否有用户名当成认证凭据。Gateway Session 可在页面打开时到期/撤销；任一业务 API 401 应清空认证状态并引导重新登录。403 通常是 Origin/CSRF 错误，不应当按“资源不存在”处理。Gateway 自身错误 JSON 只有 `code`，Backend 错误 JSON 较完整；Error UI 按 `status + code` 决策，`message/request_id/retryable` 可选读取。401、403、404、410 的用户文案应区分：未登录、请求被拒、资源不可见、原图/资产已到期。重试 5xx/网络错误时保留原 `Idempotency-Key`，不要自动创建第二个 Case/Job。

## Pinia 状态与恢复策略

建议继续维持如下内存状态；**服务端是数据真相**，不持久化响应数据或私有资源：

| 状态域 | 可保存 | 刷新后的来源 |
| --- | --- | --- |
| Auth | `username,csrfToken,loaded,error`；只在内存 | `GET /auth/session`；Cookie 由浏览器管理 |
| Cases | 当前列表、`nextCursor`、选中 Case、加载/错误 | `GET /cases` 或 URL 中的 `case_id` 对应 `GET /cases/{id}` |
| Jobs | `byId,currentId,isPolling,timedOut,lastUpdatedAt,error` | URL 中 `job_id` → `GET /jobs/{id}`，进行中恢复轮询 |
| Results | 当前 Result、资产加载状态、经授权 Blob 的 `objectURL` | URL 中 `result_id` → `GET /results/{id}`，再重取资产 |
| Viewer 偏好 | 当前 Result 的 scale/layer/overlay 开关/透明度/相机位置，可按账户隔离存 `sessionStorage` | 仅作为 UI 偏好；重新校验 Result、DICOM、图层元数据后才恢复叠加 |

当前页面路由为 `/`、`/cases`、`/cases/:id`、`/jobs/:id`、`/results/:id`、`/login`。创建 Job 后导航到 `/jobs/{job_id}`，不要只在前端内存中保留 ID。刷新 Job 页时立即 GET；`CREATED/QUEUED/RUNNING` 继续轮询，`COMPLETED` 按 `result_id` 打开 Result，`FAILED` 显示 `error.code/message`。当前 Pinia 每 3 秒轮询，10 分钟客户端超时或连续 3 次错误会停；**停轮询并不取消服务器 Job**，可再次按 ID 查询。Result 页刷新时独立按 ID 加载 Result、Case、DICOM 与选中图层；不需要重新提交 Job。若只记得 Case ID，当前 `GET /cases/{id}` 不返回 Job 列表，尚无 Case→Job 列举路由；Job/Result 深链或客户端已知 ID 是恢复入口。

## Case、Job、Result UI 的字段使用

Case 分创建和上传两步。`POST /cases` 需要 `Idempotency-Key`，可传 `patient_id:null`；上传到 `POST /cases/{id}/upload`，表单 `input_kind=dicom_series` 与单个 `file`，另一个幂等键。现阶段只支持一个去标识 CT Slice，最大 20 MiB。GET Case 后从 `studies[].series[].slices[]` 找 `slice_id`、`width_px`、`height_px`。`status=READY` 后才能显式创建 Prediction 或 Occlusion；Case 过期时已有 Result 可能仍可读，但原图返回 410，新 Job 无法运行，需新 Case 和新上传。

Prediction：`POST /predictions` 请求 `case_id,slice_id,model_id`，返回 `job_id` 且 `prediction_id=job_id`。Occlusion：`POST /jobs/occlusion` 额外提供 `protocol_id` 与不重复的 `scales`，目前全三尺度 UI 用 `[16,32,64]`。业务 ID、模型及协议需与已登记 ModelVersion 一致；不要因当前页面默认 `baseline_resnet18` 就把它误当所有部署永远唯一的模型。Job 读取字段详见 API Contract；`progress`、ETA 当前为 `null`，只显示真实状态。Prediction Result 里的 `positive_probability` 是正类概率，`predicted_class_confidence` 是预测类别置信度，不可混作一个百分比。`source` 必须是 `LIVE_CASE`，不查询或伪装 `/api/v1` Mock。

遮挡 Result 不把全部位置放在详情响应；如果 UI 要显示数值/位置计数，按 `scale` 对 `/results/{id}/positions` 用 `next_cursor` 翻页，客户端汇总实际数量。不要把某次验收的 729/169/36 当成接口常量。`scale_summaries` 中三个图层引用可为空；通过 `asset_id` 和 Result `assets[]` 对照再请求 PNG。全三尺度三图层可有九张，但缺失的候选层不能伪造。各层需要显示为模型响应、不是病灶或临床标注。

## Asset、DICOM 与 Cornerstone Viewer

Result `assets[].asset_url` 是 Backend 鉴权路径 `/api/v2/results/{result_id}/assets/{asset_id}`，不是 S3 签名 URL；当前 `ApiClient.getResultAsset` 实际用 ID 构造同一路径，带 Cookie 获取 `image/png` Blob，再以 `URL.createObjectURL` 显示，并在切换/卸载时 `revokeObjectURL`。Backend 校验 owner、Asset 所属 Result、保留期和哈希。重载页面需要重新 GET 资产，不复用旧 Blob URL。DICOM 用 `GET /cases/{case_id}/dicom` 获取 `application/dicom` Blob；加载为本地 File 交给 Cornerstone 的 file manager。原图到期为 410，已保存 Result 和独立图层仍可显示，但 CT 叠加需停止。

叠加前需核对 `Result.status=COMPLETED`、`source=LIVE_CASE`、`kind=OCCLUSION`，模型 ID、checkpoint hash、预处理与协议都在已审计几何映射名单中；Result 的 `case_id/slice_id` 与 Case 树一致；DICOM Blob 的 SHA-256 等于 `provenance.input_sha256`。选定图层须属于选定 `scale_summaries`，与 `assets[]` 中同 ID 的 `layer_kind,coordinate_space,width,height,media_type` 完全一致，PNG 解码尺寸也要吻合。`CANDIDATE_TOP10` 仅在 `candidate_status=valid` 时可用。

当前已审计单切片像素契约：响应/候选层 `ALGORITHM_224`、224×224；比较层 `COMPARISON_14`、14×14，仅放大显示；`origin=TOP_LEFT_PIXEL_EDGE,x_axis=RIGHT,y_axis=DOWN,display_interpolation_only=true`。由 Case Slice 的原始宽高按像素边界映射到 224×224 模型空间，再使用 Cornerstone 当前 `StackViewport` 的 `imageData.indexToWorld([x-0.5,y-0.5,0])` 和 `worldToCanvas` 建立画布位置；不能把 14×14 图当成更高分辨率的病灶证据。完整安全闸门在 `frontend/src/viewer/geometry.ts` 与 `CornerstoneSliceViewer.vue`，UI 重构应保留。几何不匹配时可显示独立图层，但禁用叠加。当前只验证单切片二维像素对齐，没有三维空间配准。

## 当前 MVP Deployment Example 与边界

此节不是 API Contract：`https://project.xbstu.com/mvp/` 是已验证的 Phase 5 GPU-only Full-Chain MVP **测试入口**。该环境在 Nginx 下将 Vue 静态文件置于 `/mvp/`，同源 `/auth/`、浏览器 `/api/v2/` 送 Gateway，`/api/v2/workers/` 送 Backend；私有 PostgreSQL/MinIO 不对浏览器开放。构建此部署用 `VITE_PUBLIC_BASE=/mvp/`；API 基址仍 `/api/v2`。长期架构保留 CPU/CUDA/AUTO，但当前测试链路只启动 GPU Worker。

GPU-only 全链路功能 PASS；固定 CPU/GPU 派生数值一致性 **FAILED / OPEN**（最大 `0.001049876`，容差 `0.0001`），属于算法/QA 问题，不能把它记为 API 接口失败，也不能省略限制。UI 保持研究性质的表述：热图是模型决策响应，不是病灶标注或临床诊断。
