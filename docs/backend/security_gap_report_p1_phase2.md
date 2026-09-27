# EpiLocate P1 Phase 2 Security Gap Report

审计基线：`91528fc07617d753d3582ab7d93ad617dbc7ad94`，分支 `feature/p1-auth-security`。

本报告记录当前代码的实际行为，不以旧文档替代运行代码。审计范围为 `backend_v2/`、Vite proxy、现有数据库模型和 P1 测试。

## 已有控制

- 用户路由要求 `Authorization: Bearer`，当前实现将 token 做 SHA-256 后与环境变量 `EPILOCATE_V2_USER_TOKEN_HASHES` 中的 hash 比较，再查询 active `User`。
- Worker 路由从 `worker_nodes.token_hash` 查找节点，检查 `disabled_at`，并要求 `worker_id` 与 token 对应节点一致。
- Case、DICOM、Job、Prediction、Result、Positions、Asset 均按当前用户或其 Case owner 过滤；跨 owner 的公开 ID 返回 404。
- DICOM 通过私有对象存储服务端读取并复验 SHA-256；输入到期返回 410 `INPUT_EXPIRED`。
- Worker Claim/Heartbeat/Result 校验 Attempt、Worker、lease token、模型 hash、输入 hash、结果 schema 和资产 hash。
- Result Asset 读取通过 Result → Job → owner 关系校验，响应不返回 S3 access key/secret。
- Vite proxy 只在本地服务端注入 `API_PROXY_USER_TOKEN`，前端 bundle 不包含该变量；前端使用 Backend bearer 认证语义，没有 Mock fallback。
- 当前应用没有自定义请求日志或凭据打印逻辑；Worker provision 只输出 token 文件位置并以 `0600` 写入。

## 已确认缺口

### 用户凭据

- 用户 bearer 只有部署环境 JSON hash，没有数据库凭据记录、单凭据过期时间、撤销时间或凭据级审计标识。
- `User.is_active` 只能整体停用用户，不能撤销单个 token；当前 local env hash 也没有正式 revoke 操作。
- env JSON 解析错误会在依赖执行时直接抛出，缺少统一的 503 配置错误处理。
- 没有 OIDC discovery、登录、刷新或 cookie session；生产边界依赖外部认证组件或 Vite proxy 注入静态 bearer。
- 当前测试主要使用单个固定测试 token，未覆盖 expired/revoked credential 或两个独立用户。

### 资源授权

- 现有 owner 查询路径基本正确，但没有一组覆盖 Case、DICOM、Job、Result、Positions、Asset 的双用户隔离回归测试。
- Result 详情在完成 owner 检查后调用 `signed_asset_get` 并把 `asset_url` 返回给浏览器。该 URL 的路径包含私有 S3/MinIO object key，违反“浏览器不得获得 private object key”的 Phase 2 要求。
- Asset proxy endpoint 已经可以在服务端读取私有对象，因此可保留前端功能并停止向浏览器返回直接存储 URL。

### Worker 边界

- Worker token 与用户 token 使用不同存储和依赖，现有实现能够阻止普通用户调用 Worker API、Worker 调用用户 Case API；缺少专门的反向调用回归测试。
- Worker token 有 `disabled_at` 撤销路径，但没有独立的 rotation/revocation 操作记录；本阶段保持 Worker v1 报文语义不变，只验证已有节点停用控制。

### Storage 与日志

- 输入 signed URL 最长 300 秒并绑定私有对象；Result asset signed URL 也受 300 秒上限，但当前公开 Result 返回 URL 的对象 key 暴露需要修复。
- Asset `retention_until` 字段存在，但正常结果写入未设置独立到期时间；结果默认为长期保存，输入 7 天 TTL 仍按现有契约执行。
- 服务端没有记录 Authorization、lease token、DICOM 内容或对象 URL 的应用日志；需在测试中保持这一边界，部署 access log 仍应由网关脱敏。

## Phase 2 修复方向

1. 增加 `user_credentials` 表，只保存高熵 bearer 的 SHA-256、签发时间、过期时间和撤销时间；保留明确 opt-in 的 local env hash bootstrap，生产默认关闭。
2. 提供一次性、`0600` token 文件的用户凭据 provision/revoke 命令；认证失败统一返回 401，不区分不存在、过期和撤销 token。
3. Result 描述只返回授权 API asset route，不返回直接 S3/MinIO signed URL；服务端保留 signed URL 仅用于 Worker 输入或内部对象操作。
4. 新增双用户授权、凭据生命周期、Worker/User 交叉调用、signed URL TTL 和 P0 兼容回归测试。
5. 更新 Frontend/Vite proxy 说明：本地 token 只由服务端代理持有；生产使用同一 Backend bearer 机制或在边缘完成 OIDC 到 bearer 的受控映射，前端不持有服务器凭据。
