# EpiLocate Canonical Source Map

当前主线保留原公开 `main` 历史，并按文件导入独立 Clinical Canvas 快照 `117ce7a61c6bd8ba6893ecb83445d8647c9965a1`。下表的内部来源提交只是来源指针，不是新主线的祖先。目录保持原位；完整内部历史留在本地，详见 [Source Provenance](../handoff/SOURCE_PROVENANCE.md)。

| 组件 | 当前路径 | 本次来源 | 状态 |
| --- | --- | --- | --- | --- |
| Landing | `apps/landing/` | Clinical Canvas 快照；最早来自 Stage 1 备份的 `flow-fluidity/` | 源码纳入，未由本次部署 |
| Vue AI Web | `frontend/` | Clinical Canvas `117ce7a`，另移植 `8a5928f` 的会话、超时、幂等、焦点行为 | 本地测试与浏览器验收见整合报告 |
| Showcase | `aid_site/` | Clinical Canvas 快照 | 独立应用，保持原路径 |
| Review | `epilocate_review_server/` | Clinical Canvas 快照 | 独立应用，保持原路径 |
| Backend v2 | `backend_v2/` | Clinical Canvas 快照；任务幂等适配 `8a5928f` | API v2 与现有迁移不变 |
| Session Gateway | `session_gateway/` | Clinical Canvas 快照 | 会话契约不变 |
| AI Worker | `worker/` | Clinical Canvas 快照；安全诊断移植 `f548a62` | 无 GPU 运行验收 |
| 研究工具 | `src/`, `scripts/`, `scripts/research/`, `configs/` | 冻结 Stage 1；D10 `d88cc36` 的四个离线工具及测试 | 仅公开工具，无私有检查点与逐患者证据 |
| 部署模板 | `deploy/mvp/` | Clinical Canvas 快照 | 本次未部署 |
| 项目文档 | `docs/` | Clinical Canvas 快照、当前研究状态及整合记录 | 历史证据保留原语境 |

旧独立文档来源：`docs/backend-api-phase5-gpu-mvp` @ `4ae2e59ae144e273441884fa676e628a1944a689`，`docs/project-history-engineering-journal` @ `c312d3933f7fe83772542773ae1419a7af44d63c`，以及 `codex/repository-consolidation-v1` @ `f5438fe90dfa4895e0d49a1f688b7d2cd9df36a0`。这些已在 Clinical Canvas 文件快照中按文件纳入，不表示原分支整体合并。

`algorithm/`、`src/`、`scripts/`、`configs/` 属于仍被调用或受冻结边界约束的研究/算法路径；`gradio_service/` 仍有运行依赖。它们在本轮规划中保留在仓库根目录，不列入自动归档。Landing 已按路径审计导入；研究数据、构建产物和本地环境未随之导入。

本清单只描述代码来源。线上 `/mvp/`、GPU 节点、数据库和域名状态必须单独复核；Git 主线更新不构成部署证明。
