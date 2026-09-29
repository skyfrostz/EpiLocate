# Worktree / research archive 清单（Phase 0）

本文件是**保全与后续核验清单**，不是实际归档结果。当前未移动、删除、清理或归档任何 worktree。`git` 提交可被 Phase 5 包含，并不代表工作目录里的未跟踪或忽略文件已得到保护；移除前必须分别核对三类文件和独有提交。

## 保留为工作源

| Worktree（均位于 `LOCAL_WORKTREE/`） | 分支 / 用途 | 当前处理 |
| --- | --- | --- |
| `EpiLocate-p1-phase5-dual-mode-server-demo` | `codex/p1-phase5-dual-mode-server-demo` @ `352152ce`；AI System 主线 | 保留，作为代码来源与回滚参照 |
| `EpiLocate-consolidation-v1` | `codex/repository-consolidation-v1` @ `352152ce`；本次规划 | 保留，后续分阶段实施 |
| `EpiLocate-backend-api-phase5-gpu-mvp` | `docs/backend-api-phase5-gpu-mvp` @ `ab36dea6` | 保留，待核对并纳入文档 |
| `EpiLocate-project-history-engineering-journal` | `docs/project-history-engineering-journal` @ `f8504dc4` | 保留，存在独有文档提交 |
| `infectious-ct-ai` | `research/stage1-validation-backup` @ `f59738a6`；研究与 Landing 来源 | 保留，禁止整体合并或清理研究资料 |
| `EpiLocate-develop` | `develop` @ `021e4f56`；P0 正式基线 | 保留，待 Phase 3 验收后再决定推进 |

## 未来逐项核验的历史 worktree

以下只是候选，不表示现在可安全删除。目录前缀仍为 `LOCAL_WORKTREE/`。

| Worktree | 分支 / 当前提交 | 后续核验重点 |
| --- | --- | --- |
| `EpiLocate-backend-v2` | `feature/backend-v2` @ `fbd3c580` | 提交已包含于 Phase 5；检查忽略的本地数据库/运行数据 |
| `EpiLocate-frontend-v1` | `feature/frontend-v1` @ `345b336e` | 提交已包含于 Phase 5；检查忽略的依赖和构建文件 |
| `EpiLocate-worker-v1` | `feature/worker-v1` @ `1f90321b` | 提交已包含于 Phase 5；检查模型/运行数据 |
| `EpiLocate-p1-gpu-worker` | `feature/p1-gpu-worker` @ `396d188b` | 提交已包含于 Phase 5；检查 GPU 本地证据 |
| `EpiLocate-p1-heatmap-ct-fusion` | `feature/p1-heatmap-ct-fusion` @ `77ef944e` | 检查研究产物与可复现实验资料 |
| `EpiLocate-p1-phase25-qa` | `codex/p1-phase25-integration-qa` @ `c9a5cc63` | 检查 QA 原始证据 |
| `EpiLocate-p1-phase35-integration` | `codex/p1-phase35-integration` @ `02c8ef9c` | 检查集成运行产物 |
| `EpiLocate-p1-phase45-integration` | `integration/p1-phase45-heatmap-ct` @ `b069a8ce` | 检查冻结边界与实验资料 |
| `infectious-ct-ai-frontend-real` | `feat/p0-frontend-real` @ `93d2e8f0` | 检查 P0 本地文件 |
| `infectious-ct-ai-p0` | `codex/p0-real-algorithm` @ `3b3c2708` | 忽略的 `gradio_service` 数据、日志、存储必须保全 |
| `infectious-ct-ai-p0-backend-real` | `feat/p0-backend-real` @ `3aabb798` | 检查 P0 本地文件 |
| `infectious-ct-ai-p0-integration` | `feature/p1-auth-security` @ `df506562` | 检查凭据与本地运行数据，勿写入仓库 |
| `infectious-ct-ai-p0-qa` | `test/p0-real-qa` @ `7366dd3c` | 检查 QA 原始证据 |
| `infectious-ct-ai-p0-qa-integration` | `test/p0-integration-final-qa` @ `b63c7d21` | 有独有提交，先审阅再决定保留方式 |

## 特别保护：Codex 管理的 detached worktree

`CODEX_MANAGED_WORKTREE/4f1a/infectious-ct-ai` 与 `CODEX_MANAGED_WORKTREE/62d4/infectious-ct-ai` 当前均在 `65d1861d`，可见修改及大量未跟踪 Stage 1 研究文件。禁止将它们纳入普通历史目录清理；先由对应任务/所有者确认内容与保存位置。

后续每个候选至少记录：`git status --short`、`git status --ignored --short`、独有提交/文件清单、数据归属与保全位置、可恢复验证结果。若任一项不明，保留目录。不得执行 `git clean`、`git reset --hard`、强推或直接删除研究文件。
