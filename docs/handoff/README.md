# EpiLocate Frontend Handoff

负责人：钟佳桦

前端接手：陈奕冰

本目录是 Phase 5 **Engineering MVP** 的前端交接入口。当前系统 **Not Production · Not Clinical**；GPU 功能链路的历史验收不代表 CPU/GPU 数值等价或持续线上可用。本仓库是独立 sanitized Git root，不包含完整内部开发历史；[SOURCE_PROVENANCE](SOURCE_PROVENANCE.md) 记录了文件树来源和排除范围。发布与部署门槛见 [HANDOFF_STATUS](HANDOFF_STATUS.md)。

## Start Here

1. [Project Context](../project/PROJECT_CONTEXT.md)：应用边界、冻结研究与证据等级。
2. [Frontend Handoff Document v1.1](<EpiLocate Frontend Handoff Document v1.1.docx>)：职责、现状与接手顺序。
3. [Frontend Redesign Proposal v1.1](<EpiLocate Frontend Redesign Proposal v1.1.docx>)：重构建议，不等于已实现行为。
4. [API Interface Guide V1.0](../backend/EpiLocate_API_Integration_Guide_V1.0.md) 与 [脱敏 Word 版](<EpiLocate_前后端_API接口协议与前端接入指南_V1.0.docx>)。
5. [Frontend Integration Guide](../backend/frontend_integration_guide_phase5.md) 与 [Backend API Contract](../backend/backend_api_contract_phase5.md)。
6. 当前 Vue 代码：[`frontend/`](../../frontend/README.md)，包括 Router、Pinia、Case/Job/Viewer/Heatmap。
7. 前端测试：`frontend/src/**/*.test.ts`、`frontend/geometry-qa/` 和 `frontend/package.json` 的脚本。

三份 Word 是经过单独元数据清理的正式候选副本；原件留在原工作区。两份前端 Word 的当前版本是 v1.1，未发现对应的 v1.1 Markdown 源。根 `.gitignore` 仍忽略其他 DOCX，仅放行本目录的正式交接件。

## Canonical Source

| 组件 | 当前路径 | 来源 |
| --- | --- | --- |
| AI Web | `frontend/` | Phase 5 `f80d4cf406689cd031f993090783e281db93c4ef` |
| Backend | `backend_v2/` | 同上 |
| Session Gateway | `session_gateway/` | 同上 |
| GPU Worker | `worker/` | 同上；冻结模型另在 `algorithm/` 等路径 |
| Deployment | `deploy/mvp/`、`deploy/gpu/`、`deploy/release/` | Phase 5 模板加本候选的依赖与来源机制 |
| Welcome Landing | `apps/landing/` | 从研究分支 `f59738a606d15ff7062bbc64fc316ba276035ce4` 的 `flow-fluidity/` 逐文件导入 |

陈奕冰负责 `frontend/`，未来若经单独评审迁移则负责 `apps/ai-web/`；范围包括 Login、Case UI、Job UI、Viewer、Heatmap、Router、Pinia 与前端测试。Landing、Showcase、Review、Backend、Gateway、Worker、部署和 FrozenBaseline 不在此次前端职责内。不要把旧 Review 或 Aid 账户当作 AI Web Session。

## Current Baseline and Live URLs

- 当前快照分支：`handoff/pre-b-transfer-20260929`，Git 历史从独立 root commit 开始；内部来源 SHA 仅用于文件来源核对，不能用本仓库 `git log` 还原完整开发史。最终 Handoff SHA 以 `git rev-parse HEAD` 和部署目录的 `SOURCE_COMMIT` 双重核对；Git 文件不能可靠地自写其最终 SHA。
- Welcome：`https://project.xbstu.com/welcome/` 已从 GitHub sanitized 提交部署并完成桌面、移动浏览器全页检查；根 `/` 保留 Review。最终部署 SHA 应以运行时 `SOURCE_COMMIT` 与 GitHub ref 核对；验收结果见 [HANDOFF_STATUS](HANDOFF_STATUS.md)。
- AI Web 工程测试入口：`https://project.xbstu.com/mvp/`，已切至同一 Git-based candidate release；HTTP 可达与现有服务健康检查不等于最终 GPU E2E 或生产验收。
- GPU AI Node 由负责人主动释放：**TEMPORARILY OFFLINE / INTENTIONALLY RELEASED**。历史架构验证保留；最终 Git-based GPU E2E 等待新节点。参见 [HANDOFF_STATUS](HANDOFF_STATUS.md)。
- CPU/GPU 数值一致性、失败 Job UX、Worker traceback、生产加固与备份恢复状态见 [HANDOFF_STATUS](HANDOFF_STATUS.md)。
