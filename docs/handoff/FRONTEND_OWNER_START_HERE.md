# EpiLocate Frontend Owner — Start Here

**前端负责人：陈奕冰。** 当前开发分支为 `feature/frontend-redesign-phase5`，**Initial Source Baseline** 为公开 sanitized Handoff 提交 `4e38fd32765e7c69ae0b7389cb91fe057c938472`（`handoff/pre-b-transfer-20260929`）。此分支若增加接手文档，HEAD 会成为新的仅文档提交；代码起始基线仍是上述 SHA。公开仓库从独立洁净 Git root 开始，不包含完整内部开发历史。当前产品是 **Engineering MVP · Not Production · Not Clinical**。

## 先读这些资料

按顺序阅读：

1. [Handoff README](README.md)：项目边界、交接入口和当前系统状态。
2. [Frontend Handoff Document v1.1](<EpiLocate Frontend Handoff Document v1.1.docx>)：负责人职责与现有流程。
3. [Frontend Redesign Proposal v1.1](<EpiLocate Frontend Redesign Proposal v1.1.docx>)：重构方案，建议不等于已实现行为。
4. [前后端 API 接口协议与前端接入指南 V1.0](<EpiLocate_前后端_API接口协议与前端接入指南_V1.0.docx>)；便于检索的 [Markdown API Guide](../backend/EpiLocate_API_Integration_Guide_V1.0.md)。
5. [Phase 5 Frontend Integration Guide](../backend/frontend_integration_guide_phase5.md) 与 [API Contract](../backend/backend_api_contract_phase5.md)：实现细节以当前代码和实测响应复核。
6. [Project Context](../project/PROJECT_CONTEXT.md)：架构、研究边界与证据等级；其旧部署状态段落是历史记录。[Handoff Status](HANDOFF_STATUS.md) 冻结时仍写前端分支远端待 GPU，本轮已获授权创建并推送，实际分支状态以 GitHub ref 和本文交接记录为准。
7. [`frontend/` README](../../frontend/README.md)、代码和测试。

## 系统与负责范围

当前用户路径为 [Welcome](https://project.xbstu.com/welcome/) → [AI System](https://project.xbstu.com/mvp/) → 未登录时 Login → Case / Job / Viewer / Result。`apps/landing/` 是展示入口；`frontend/` 是实际 AI Web，使用 Vue 3、TypeScript、Vite、Vue Router、Pinia、Ant Design Vue 和 Cornerstone。浏览器经同源 Session Gateway 调用 Backend v2；Backend 管理 Case、Job、Result 与授权，独立 Worker 执行推理。Review、Aid 与 AI System 的账户及会话互不等同。

**唯一当前开发目录为 `frontend/`。** `apps/ai-web/` 只是未来 Repository Consolidation 的目录规划，迁移获批前不要在其中另起实现。负责 Login、Case/Job/Result UI、Viewer、Heatmap/Overlay、Router、Pinia、API 接入、错误/加载/空白/失败状态、测试、视觉统一、响应式体验与 Challenge Cup 演示体验。重构应保留已验证的 Auth、Session、API 契约、Case → Job → Result、Viewer 和刷新恢复行为；热图标为模型响应，不能表述为临床标注。Welcome Landing 与 Vue AI Web 保持各自边界。

未经负责人钟佳桦另行批准，不修改 `backend_v2/`、`session_gateway/`、`worker/`、`deploy/`、`algorithm/`、`src/`、`scripts/`、`configs/`、`apps/landing/`、`aid_site/`、`epilocate_review_server/`，也不改 FrozenBaseline、checkpoint、Worker Protocol、数据库 Schema、Nginx/systemd 或 CPU/GPU tolerance。发现 API 缺口时记录请求、响应状态、脱敏复现步骤和期望契约，提交钟佳桦，由 Backend owner 审核；前端不要自行改 Backend。

## 本地开始

建议在自己的仓库/独立 Worktree 开发，不进入交接负责人的 Handoff Worktree。分支空闲时，从仓库根目录执行：

```bash
git fetch origin
git worktree add <new-path> feature/frontend-redesign-phase5
cd <new-path>
git status --short --branch
git merge-base --is-ancestor 4e38fd32765e7c69ae0b7389cb91fe057c938472 HEAD
cd frontend
npm ci
npm test
npm run build
```

`frontend/package-lock.json` 已存在，使用 `npm ci` 保持锁定依赖，不在建立基线时升级。记录改动前的测试数量、构建结果与 HEAD。若同一仓库的该分支已被其他 Worktree 占用，先协调该 Worktree 的使用，不强制移动；可在自己的新 clone 中检出远端分支并建立独立工作目录。开发时可用 `npm run dev`；本地代理和 `/mvp/` 构建基址见 [集成指南](../backend/frontend_integration_guide_phase5.md)。

## 当前系统状态与待解决项

- ECS 的 `/welcome/` 与 `/mvp/` 来自 Git-based release，`SOURCE_COMMIT` 为 `4e38fd32765e7c69ae0b7389cb91fe057c938472`。这是工程测试入口，不代表生产或最终 GPU 验收。
- GPU AI Node：**TEMPORARILY OFFLINE / INTENTIONALLY RELEASED**。历史 RTX 3090 GPU 功能 E2E 为 PASS；最终 sanitized-SHA GPU E2E 为 **PENDING GPU RE-PROVISION**。GPU 暂时离线不阻塞前端重构。
- **Frontend OPEN：** FAILED Job 页面曾只显示 `Job failed.`。按稳定脱敏错误码设计安全分类、可否重试、建议动作与 Retry flow；区分网络、Session、推理失败。HTTP 请求超时不等于 Job 已失败，刷新后应按 Job ID 恢复查询。
- **API OPEN：** Gateway/Backend 错误体不完全统一，Login 校验可能返回 `422 detail`；前端类型与实返字段存在差异；缺少按 Case 列举 Job 的专用 route；部分上传、资产和代理路径整包读入内存。API 变更须走负责人和 Backend owner 审核。
- **Algorithm/QA OPEN：** 固定 CPU/GPU 数值一致性最大偏差 `0.0010498762130737305`，容差 `0.0001`，结果 **FAIL / OPEN**。这不属于前端修复范围，也不得通过 UI 文案改写为通过。

## Git、提交与汇报

只在 `feature/frontend-redesign-phase5` 开发；提交前检查 `git status` 和 diff，仅纳入职责范围内文件，不提交凭据、医疗影像、运行日志或本地缓存。将 UI/测试改动分成可审阅提交，提交信息说明意图；每轮记录起点 SHA、当前 HEAD、测试与构建结果。不要 merge `main`/`develop`，不要改写 Handoff 分支或 force push。公开 Handoff 固定 SHA 与内部完整证据历史有不同用途。

向钟佳桦汇报时列出：当前分支及 HEAD、改动页面/流程、接口差异及需 Backend owner 决策的事项、改动前后测试和 build、浏览器验证范围、仍待解决的失败体验或风险。只报告实际通过的环境与路径；GPU 最终 E2E 仍等待新节点。
