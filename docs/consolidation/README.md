# EpiLocate Consolidation — Phase 0 记录与交接候选

此隔离 worktree 从 Phase 5 MVP 固定提交 `352152ce95fc26eb2dc0a4c309521d50486472ba` 建立，分支为 `codex/repository-consolidation-v1`。

上段描述的是内部 Consolidation 分支当时的 Phase 0 历史状态，不是本仓库的 Git 祖先。本交接仓库是从已审计文件树制作的独立 sanitized Git root，已按路径将 Welcome Landing 导入 `apps/landing/`。Vue、Backend、Gateway、Worker、Showcase、Review 仍保留在根目录；`services/` 没有迁入业务源码。源码进入快照本身不证明 GitHub 发布或服务器部署。

来源与目标路径见 [SOURCE_MAP.md](SOURCE_MAP.md)，后续迁移闸门见 [MIGRATION_PLAN.md](MIGRATION_PLAN.md)，保全清单见 [archive/README.md](../../archive/README.md)。`deploy/` 与 `docs/` 在基线中已经存在，本阶段不迁移其现有内容。
