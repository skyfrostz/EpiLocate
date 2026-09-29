# EpiLocate Canonical Source Map — handoff candidate

此表区分当前路径与尚未执行的迁移。当前仓库是独立的 sanitized Git root；表中的分支和 SHA 是内部来源指针，不是本仓库的 Git 祖先。应用实现来源为 Phase 5 `4d717a3753ef307ab370adeafaf5a00da4dc7af9`；仅 Landing 从研究分支按路径导入 `apps/landing/`，没有合并研究分支；其他应用与服务保持原路径。完整内部历史仅保留在本地，详见 [Source Provenance](../handoff/SOURCE_PROVENANCE.md)。

| 组件 | 当前唯一来源 | 来源分支及提交 | 拟议目标 | 阶段 |
| --- | --- | --- | --- | --- |
| Landing | `apps/landing/`（来自 `flow-fluidity/`） | `research/stage1-validation-backup` @ `f59738a606d15ff7062bbc64fc316ba276035ce4` | 当前已按路径导入；未上线 | Handoff candidate |
| Vue AI Web | `frontend/` | Phase 5 @ `f80d4cf` | `apps/ai-web/` | 后续评估 |
| Showcase | `aid_site/` | Phase 5 @ `f80d4cf` | `apps/showcase/aid_site/` | 后续评估 |
| Review | `epilocate_review_server/` | Phase 5 @ `f80d4cf` | `apps/review/epilocate_review_server/` | 后续评估 |
| Backend v2 | `backend_v2/` | Phase 5 @ `f80d4cf` | `services/backend/backend_v2/` | 后续评估 |
| Session Gateway | `session_gateway/` | Phase 5 @ `f80d4cf` | `services/gateway/session_gateway/` | 后续评估 |
| AI Worker | `worker/` | Phase 5 @ `f80d4cf` | `services/worker/worker/` | 后续评估 |
| Deployment templates | `deploy/mvp/` | Phase 5 @ `f80d4cf` | `deploy/mvp/` 暂保持 | Handoff candidate 增补 GPU/Release 文件 |
| 项目文档 | `docs/` 及独立文档分支 | Phase 5；文档分支另见下文 | `docs/` | Phase 1 整理 |

独立文档来源：`docs/backend-api-phase5-gpu-mvp` @ `4ae2e59ae144e273441884fa676e628a1944a689`，`docs/project-history-engineering-journal` @ `c312d3933f7fe83772542773ae1419a7af44d63c`，以及 `codex/repository-consolidation-v1` @ `f5438fe90dfa4895e0d49a1f688b7d2cd9df36a0`。当前候选已逐文件纳入必要文档；这不表示原分支整体合并。

`algorithm/`、`src/`、`scripts/`、`configs/` 属于仍被调用或受冻结边界约束的研究/算法路径；`gradio_service/` 仍有运行依赖。它们在本轮规划中保留在仓库根目录，不列入自动归档。Landing 已按路径审计导入；研究数据、构建产物和本地环境未随之导入。

本清单只描述代码来源及目标。线上 `/mvp/`、GPU 节点、数据库迁移和域名状态必须在切换前单独复核；此文件不是线上已切换的证明。
