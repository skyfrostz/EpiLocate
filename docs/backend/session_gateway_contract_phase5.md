# Browser Session Gateway / Auth Contract — Phase 5 implementation

**代码基线：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9`；以 `session_gateway/app.py`、`store.py`、`manage.py`、`backend_v2/auth/credentials.py`、`frontend/src/auth/session.ts` 为准。Gateway 为浏览器提供同源密码登录与可撤销 Session；Backend v2 仍负责用户凭据验证和每次资源授权。此文只描述现有工程行为，不把当前 MVP 测试站点写成永久部署要求。用户业务字段见 [Backend API Contract](backend_api_contract_phase5.md)。

## 浏览器路径、身份与保密边界

浏览器请求同一 HTTPS origin 的 `/auth/*`、`/api/v2/{cases|predictions|jobs|results}*`。Gateway 只转发允许的用户 API GET/POST，拒绝 `//`、`..` 和其他方法/路径，**不转发 Worker API**。Gateway 清除浏览器自带的 Authorization，读取该账户对应的服务器端 Backend Bearer，向 loopback Backend 注入；浏览器、Pinia、Vite 构建中都不保存该 Bearer。账户文件保存 Argon2 密码哈希及 token 文件路径；Backend 数据库只存用户 token SHA-256。Gateway Session SQLite 仅存随机 Cookie 值的 SHA-256、用户名、到期/撤销时间。Worker token、S3 凭据和私有对象键也不能传给浏览器。

Cookie 名为 `__Host-epilocate_demo`，属性 `HttpOnly; Secure; SameSite=Strict; Path=/`，有效期 8 小时；Session 服务端同样检查过期与撤销。CSRF token 随登录与会话校验 JSON 返回，供前端仅在内存中保存，并在 POST 请求头 `X-CSRF-Token` 提交。Gateway 对登录以及所有状态变更的用户 API/Logout 严格要求 `Origin` 等于配置的**裸 HTTPS origin**；CSRF 值用固定时间比较。站点的 SPA 子路径（如 `/mvp/`）不属于 Origin。

## 登录、校验、失效

| 方法与路径 | 请求 | 成功 | 常见失败 |
| --- | --- | --- | --- |
| `POST /auth/login` | JSON `{"username":"…","password":"…"}`；`Origin` 必填 | 200 `{"username":"…","csrf_token":"…"}`，Set-Cookie | 401 `INVALID_CREDENTIALS`；403 `ORIGIN_REJECTED`；429 `LOGIN_RATE_LIMITED`；503 `ACCOUNT_UNAVAILABLE` / `BACKEND_UNAVAILABLE` |
| `GET /auth/session` | 自动带 Cookie；不需 CSRF | 200 同上，用于页面首次加载/刷新和 Route Guard | 401 `UNAUTHENTICATED`；503 `ACCOUNT_UNAVAILABLE` |
| `POST /auth/logout` | Cookie、匹配的 `Origin`、`X-CSRF-Token` | 204，撤销 Session 并清 Cookie | 401 `UNAUTHENTICATED`；403 `ORIGIN_REJECTED` / `CSRF_REJECTED` |
| `GET/POST /api/v2/…` | Cookie；POST 另需 Origin 和 CSRF；原用户路由的请求体与 Idempotency-Key | 保留 Backend 状态码、Content-Type 与内容 | Gateway 401/403/404/413/503，或 Backend 的业务错误 |

登录校验密码后，Gateway 用该账户的 Backend Bearer 向 `GET /api/v2/cases?limit=1` 探测；只有 Backend 返回 200 才签发 Session。新登录会撤销请求中已有的 Session。登录失败按 IP 与用户名分别限流：10 分钟内各最多 5 次尝试，成功清除该组合的尝试记录。用户名只允许字母、数字、下划线、点和短横线，最长 96 字符。

Session 失效路径：8 小时到期、主动 Logout、管理员撤销该用户全部 Session、禁用 Gateway 账户、替换账户配置时管理命令撤销旧 Session。丢失/无效 Cookie 或账户已禁用返回 401；账户指向的 Backend token 文件缺失或不可读返回 503。**`GET /auth/session` 不向 Backend 重新探测 token 是否已被撤销**；如 Backend 凭据在 Session 存续中失效，Gateway Session 检查仍可能返回 200，而后续业务 API 返回 Backend 401。前端遇任何用户 API 401 应清空登录态、引导重新登录。更新账户 token 文件或撤销 Gateway Session 需由运营流程完成。

Gateway 显式拒绝的请求错误体仅为 `{"code":"STABLE_CODE"}`，响应 `Cache-Control:no-store`；登录请求体不符合 Pydantic Schema 时，FastAPI 默认返回 **422 `{"detail":[…]}`**。转发 Backend 错误时保持其 `{"code","message","retryable","request_id","details"}` 结构；客户端不能假定所有错误都有 `code`、`message`、`retryable` 或 `request_id`。Gateway 请求体上限 21 MiB；超过为 413 `REQUEST_TOO_LARGE`。未允许的路径或方法为 404 `NOT_FOUND`。Proxy 连接 Backend 失败为 503 `BACKEND_UNAVAILABLE`。

## Route Guard 与前端状态

前端路由（`frontend/src/router/index.ts`）进入受保护页时首次调用 `GET /auth/session`；401 导向登录页并保留 `next` 路径。登录成功后更新内存中的用户名和 CSRF 值。刷新页面时 Cookie 自动随同源请求发送，先重新取得 CSRF 值，再查询 Case/Job/Result。不要把密码、Backend Bearer、Cookie 值、Worker 凭据或 S3 签名 URL放进 Pinia/localStorage/sessionStorage。浏览器 API fetch 设置 `credentials:"include"`；POST 带 `X-CSRF-Token` 与需要的 `Idempotency-Key`。Cookie 无法由 JavaScript 读取，不能用本地 token 存在与否作为 Route Guard 判断。

当前前端只在一次页面加载中缓存 `auth.loaded`，不会每次路由切换重新请求 Session；业务 API 401 会清空内存认证。由此，Session 在浏览期间被撤销后，直到业务请求或显式 `loadSession(true)` 才可能感知。此为现行 UI 行为，重构时应保持服务端授权为准。

## 当前部署示例，非 API 契约

Phase 5 MVP 测试入口是 `https://project.xbstu.com/mvp/`，不是正式生产环境。Nginx 现将 `/mvp/` 提供 Vue SPA，将同源根路径 `/auth/` 和浏览器 `/api/v2/` 指向 Gateway，将 `/api/v2/workers/` 单独指向 Backend。应用部署到其他域名或子路径时，配置 public origin、Vite base、反向代理路由；不要在组件中写死此测试域名。Worker 直达 Backend 的 HTTPS origin，不经过浏览器 Session Gateway。
