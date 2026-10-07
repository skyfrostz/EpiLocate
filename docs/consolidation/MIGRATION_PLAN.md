# EpiLocate Consolidation — 后续执行闸门

本文件保留原 Phase 0 分期方案。交接候选已经完成 Phase 1 中的 Landing 路径限定导入与部分文档整合；其他 Phase 1 发布审计、Phase 2 目录迁移和 Phase 3 主线/归档均未完成。当前实际路径以 [SOURCE_MAP](SOURCE_MAP.md) 为准。

## Phase 0（本次）

从固定 Phase 5 提交创建隔离 worktree 和 `codex/repository-consolidation-v1`，建立 `apps/`、`services/`、`docs/`、`deploy/`、`archive/` 的规划视图。新增内容限 Markdown 清单；不复制或移动业务源码，不修改入口、导入、部署、数据库、Worker runtime 或服务器。当前 `docs/` 和 `deploy/` 沿用基线现有目录。

## Phase 1 — 来源收口与文档（另行执行）

1. 复核 Phase 5、Landing、Backend API docs、Engineering docs 各固定提交及文件差异；明确文档版本与 Phase 5 基线的差异。
2. 从 `flow-fluidity/` 做路径限定、文件级审计的 Landing 导入；排除研究材料、隐私数据、缓存、构建产物和本地环境。独立构建并保持现有域名路由。
3. 逐项整理文档，标明代码已实现、环境已验证和生产已验收的不同证据；不直接合并研究分支或文档分支。

## Phase 2 — 应用与服务迁移（另行执行）

1. 按 [SOURCE_MAP](SOURCE_MAP.md) 分批迁移 Vue、Showcase、Review、Backend、Gateway 和 Worker；每批独立提交、构建和接口/启动检查。
2. 更新相应 Python 包入口、导入、相对路径和部署模板引用只在该批迁移获得批准后进行。`algorithm/`、`src/`、`scripts/`、`configs/` 与 `gradio_service/` 继续留在根目录，直到依赖与冻结协议另行审定。
3. 保持 API 协议、数据库 schema/migration 和 Worker 推理行为不变；环境中验证后再提出任何上线切换。

## Phase 3 — 验收、主线和归档（另行执行）

1. 复核全量差异、构建、接口、CPU/GPU 证据、部署模板及回滚路径；生产状态只根据真实服务器与 GPU 节点验收声明。
2. 验收后才评估把 `develop` 从 P0 基线推进到收敛后的工程主线；禁止强推，确认分支前后关系与远端状态。正式 release tag 单独决策。
3. 逐个审计历史 worktree 的已跟踪、未跟踪、忽略文件，先保全有价值的数据与独有提交，再考虑分批移除工作目录。参考 [archive 清单](../../archive/README.md)；当前没有任何归档或删除动作。

任何阶段发现未保护的数据、无法解释的独有提交或线上路径依赖时暂停对应迁移，并保留原目录与运行方式。
