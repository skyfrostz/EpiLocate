# QA 问题与分配

## QA-BE-001：热力图资产缺少对象授权

- 状态：**FAIL / OPEN**；归属：后端负责人，外部集成启用前由集成负责人复核。
- 被测提交：`3b3c270869663293769f99ab3cbc180904185a1f`。
- 输入：本仓库 synthetic DICOM，经真实三尺度遮挡产生的 `result_id` 与 `response-16.png` 资产 ID；请求不带身份凭据。
- 预期：若该路由按受保护影像资产对外提供，匿名或跨病例请求应为 401/403，不能只依赖知道资产 ID。
- 实际：`GET /api/v1/assets/response-16.png?result_id=<synthetic-result-id>` 返回 200 与 PNG。证据为 `evidence/http_probe.json` 的 `asset_requires_authorization`。服务文档也声明当前仅限 loopback 且尚无认证/对象授权。
- 复现：用 synthetic fixture 上传并完成遮挡；取 result 中 `response_layer.asset_id` 和 `result_id`；在无身份凭据的新 HTTP client 中请求资产。
- 日志：QA 专用 Uvicorn 访问日志记录该 GET 为 200；没有患者或正式测试影像参与。
- 修复验收：在固定后端提交上核对可选 Bearer Token 的启用与服务端传递方式；启用时匿名/无效 Token 请求 401、合法同病例请求 200，并验证跨病例对象边界，且有独立回归测试。若坚持 P0 本机无认证范围，集成入口必须保持 loopback 隔离，不得将该路由公开为受保护能力。

## QA-ENV-001：固定集成输入未提供

- 状态：**BLOCKED**；归属：集成负责人。
- 当前前端和后端工作区均有未提交改动，固定 frontend/backend/integration SHA 与统一环境尚未提供。
- 影响：真实新页面、刷新/断网、联合端到端验收不能执行；不把旧 Gradio `run_dicom` 的通过结果代替新页面 QA。
