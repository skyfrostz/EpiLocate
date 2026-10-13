# EpiLocate 工程开发日志

> 本日志把可以从 Git 和仓库证据确认的工程活动按归档日期整理。历史部分使用提交日期或报告日期，不把它当作完整的真实工作日程。无法确认的执行者、排查过程和日期会明确写出“证据不足”。
>
> 当前日志基线：`p0/integration` / `b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5`。
>
> 本文的旧分支与 SHA 是内部历史来源记录，不是本公开 sanitized snapshot 的 Git 祖先；参见 `docs/handoff/SOURCE_PROVENANCE.md`。

## 记录规则

- 同一天的 Backend、Frontend、Worker、QA、集成、科研和文档任务分开记录。
- 分支成果只写成对应分支成果；只有进入集成提交后才写成集成基线能力。
- 每条记录尽量包含分支、Worktree、Commit SHA、实际修改、验证证据和未完成事项。
- 没有会话记录时，不指定 Codex 执行者，不猜测排查过程。
- `MOCK`、`LIVE_CASE`、`FROZEN_VALIDATION` 始终分开。
- 测试通过表示指定环境和指定范围通过，不自动表示已部署或临床有效。

## 2026-09-22｜项目初始化与协议准备

### 离线 Baseline 工作区

**任务类型：** 离线数据与模型基础

**任务负责人：** Git 和仓库资料未记录，证据不足。

**分支 / Worktree：** 初始 `main` 祖先；历史 Worktree 未记录。

**关联 Commit：** `3bd03853c5123dab8f40e145c7b42aa05a3a15bb`

**今日工作目标：**

建立 EpiLocate 的 DICOM 整理、患者级拆分、预处理、Dataset/DataLoader 和 ResNet-18 Baseline 基础。

**今天完成了什么：**

- 加入 DICOM 整理、检查和元数据脚本。
- 加入患者级 split、预处理、Dataset、训练和模型初始化代码。
- 在 README 中记录 Baseline Step 1–12、开发用途和数据安全边界。

**为什么需要做这些工作：**

后续算法和服务必须使用固定、可复核的患者级数据和统一输入方式。

**遇到了什么问题：**

提交中没有逐步开发记录，无法确认当日具体报错或排查顺序。

**问题原因：**

证据不足，不能根据文件列表推断原因。

**最终如何解决：**

以提交中的脚本、配置、测试和 README 作为当前可追溯结果。

**验证结果：**

README 声明已完成 DICOM 整理、患者级划分、预处理、抽样 QC、DataLoader、模型初始化、tiny overfit、smoke 和 Baseline 训练。该结果没有被扩展成在线系统验收。

**今天留下的问题：**

没有在线 API、任务系统、Worker、Viewer 或对象权限。

**下一步计划：**

冻结系列选择规则并补充人工复核输入输出。

**关联文档或验收报告：**

- 初始 `README.md`
- `src/`
- `scripts/`
- `configs/`
- `tests/`

### Rule B 系列复核协议

**任务类型：** 数据治理协议

**任务负责人：** 未记录。

**分支 / Worktree：** `main` 祖先；Worktree 未记录。

**关联 Commit：** `db100c250d13f8cc3c53b315ca39c6d9f8d80c98`

**今日工作目标：**

让系列筛选和人工复核拥有明确版本、输入输出和校验规则。

**今天完成了什么：**

加入 `formal_series_selection_rule_b_v1.json`、准备脚本、决定校验脚本和测试。

**为什么需要做这些工作：**

避免后续数据处理静默替换系列选择结果。

**遇到了什么问题：**

完整人工讨论过程未进入仓库。

**问题原因：**

历史资料不足。

**最终如何解决：**

保留协议文件、脚本和测试作为工程证据。

**验证结果：**

提交包含 `tests/test_manual_series_decisions.py`；没有在线服务验收。

**今天留下的问题：**

协议冻结不等于科研结果或临床有效性通过。

**下一步计划：**

建立轻量服务原型。

**关联文档或验收报告：**

- `configs/formal_series_selection_rule_b_v1.json`
- `scripts/prepare_series_manual_review.py`
- `scripts/validate_manual_series_decisions.py`
- `tests/test_manual_series_decisions.py`

## 2026-09-23｜Gradio Mock 原型

### P0 Mock 服务

**任务类型：** Gradio/FastAPI 原型

**任务负责人：** Commit 未记录 Codex 执行者，证据不足。

**分支 / Worktree：** `origin/feat/gradio-demo-p0`；原 Worktree 未记录。

**关联 Commit：** `f153b9b5c15ffb8de86415fdbf38ac5cf0386248`

**今日工作目标：**

提供一个可以演示上传、提交 Job、轮询状态和读取结果的轻量服务外壳。

**今天完成了什么：**

- 加入 FastAPI/Gradio 调试服务。
- 加入 PNG/JPG Mock inference、SQLite Job、存储和合同。
- 加入 API、合同、Job 和 Mock 测试。

**为什么需要做这些工作：**

先验证交互和状态机，再接入真实 DICOM 与 FrozenBaseline。

**遇到了什么问题：**

该分支后来没有作为提交祖先直接进入 `p0/integration`。

**问题原因：**

后续 P0 真实接入在另一条集成线上重新引入相关文件。

**最终如何解决：**

后续实现保留 Mock 兼容入口，并通过 `source=MOCK` 与真实 `LIVE_CASE` 分开。

**验证结果：**

该分支保留本地测试文件；没有真实 DICOM 或生产部署证据。

**今天留下的问题：**

真实算法、DICOM 几何、认证、对象权限、多切片和生产存储尚未接入。

**下一步计划：**

对主线和 Mock 分支做接口审计，再从固定基线建立真实 P0 接入分支。

**关联文档或验收报告：**

- `gradio_service/README_WINDOWS.md`
- `gradio_service/gradio_debug/`
- `gradio_service/tests/`

## 2026-09-25｜周边服务

### 人工复核服务

**任务类型：** Review Server

**任务负责人：** 未记录。

**分支 / Worktree：** `main`；Worktree 未记录。

**关联 Commit：** `65d1861d8776c06038472c576f453a7b90256fa2`

**今日工作目标：**

提供人工 Series 复核、账户、导出和部署配置。

**今天完成了什么：**

加入 `epilocate_review_server/`、迁移、模板、静态资源、部署文件和测试。

**为什么需要做这些工作：**

人工复核需要独立的数据和访问边界，不应直接依赖在线推理服务。

**遇到了什么问题：**

没有完整部署操作记录。

**问题原因：**

证据不足。

**最终如何解决：**

以代码、测试和 `README_DEPLOY.md` 作为可追溯记录。

**验证结果：**

仓库包含 Review Server 测试；这不是 P0/P1 在线推理验收。

**今天留下的问题：**

与后续 Backend v2 的身份、数据和部署关系需要分别维护。

**下一步计划：**

保留 Review Server 作为独立组件。

**关联文档或验收报告：**

- `epilocate_review_server/README_DEPLOY.md`
- `tests/review_server/`

### 项目展示站

**任务类型：** 展示与说明服务

**任务负责人：** 未记录。

**分支 / Worktree：** `main` 后续祖先；Worktree 未记录。

**关联 Commit：** `14c114ab26226561615315f7d3d25e42fcec64cc`

**今日工作目标：**

提供项目概览、进度、系统说明和未来受控入口。

**今天完成了什么：**

加入 `aid_site/` 及其部署配置。

**为什么需要做这些工作：**

项目展示和在线影像推理需要保持不同的数据和安全边界。

**遇到了什么问题：**

真实影像服务尚未接入展示站。

**问题原因：**

展示站和算法服务是不同组件。

**最终如何解决：**

保留展示站独立目录，不把同名 API 当作真实影像 API。

**验证结果：**

有站点代码和 README；没有真实影像生产部署验收。

**今天留下的问题：**

展示站、Review Server 和 Backend v2 的身份委托仍需单独设计。

**下一步计划：**

在 P0 接口审计中明确组件职责。

**关联文档或验收报告：**

- `aid_site/README.md`
- `aid_site/API.md`

## 2026-09-26｜Stage 1 研究资料归档

**任务类型：** 并行科研资料归档

**任务负责人：** 未记录。

**分支 / Worktree：** 从 `65d1861d...` 分出的研究分支；当前备份分支为 `research/stage1-validation-backup`。

**关联 Commit：** `e81480d5e186905870e8e60cd5db7993706720ae`

**今日工作目标：**

保存 Stage 1 FrozenBaseline 验证、结果冻结和独立 QA 资料。

**今天完成了什么：**

加入 `analysis/`、`deliverables/stage1_materials_2026-09-25/`、冻结配置、协议、独立 QA 报告和探索性分析。

**为什么需要做这些工作：**

为科研响应、哈希、sealed-test 边界和后续复核保留可追溯证据。

**遇到了什么问题：**

该分支不是 `p0/integration` 的祖先，不能直接作为当前工程集成基线文件。

**问题原因：**

科研资料和服务集成沿着不同分支推进。

**最终如何解决：**

在工程历史中标记为并行科研证据链，引用其冻结 JSON 和报告，不把它写成已合并能力。

**验证结果：**

`result_freeze.json` 为 `FROZEN`，`independent_qa_report.json` 为 `PASS`，28 名患者、5,637 个切片，test pixels 未读取。

**今天留下的问题：**

候选区域是模型响应假设，不是病灶真值或临床定位。

**下一步计划：**

P0 真实算法分支复用冻结协议和模型边界。

**关联文档或验收报告：**

- `analysis/stage1_validation_exploratory_v1/report.md`
- `deliverables/stage1_materials_2026-09-25/result_freeze.json`
- `deliverables/stage1_materials_2026-09-25/independent_qa_report.json`

## 2026-09-26｜P0 真实接入、分角色开发与发布

### P0 FrozenBaseline 真实 API

**任务类型：** 算法服务接入

**任务负责人：** 未记录。

**分支 / Worktree：** `codex/p0-real-algorithm`；独立 Worktree 路径见 `docs/interfaces/p0_real_integration.md`。

**关联 Commit：** `34edd02637fd4d5a54fed37dd926229e43c5b69a`、`3b3c270869663293769f99ab3cbc180904185a1f`

**今日工作目标：**

让真实单切片 DICOM 经过 HTTP/Gradio 调用 FrozenBaseline，并保持 Mock 入口独立。

**今天完成了什么：**

- 接入 `algorithm/service.py`。
- 实现 Case、Prediction、Occlusion、Job、Result、位置和资产接口。
- 加入合成 DICOM、HTTP 向量、冻结 hash 检查和真实集成测试。

**为什么需要做这些工作：**

Mock 服务无法证明冻结模型可以安全地服务真实 DICOM。

**遇到了什么问题：**

本机代理环境导致 `httpx.InvalidURL: Invalid port ':1'`；真实 DICOM 的几何、资产和冻结目录写入边界也需要测试。

**问题原因：**

代理环境和服务运行目录/冻结数据目录的边界冲突。

**最终如何解决：**

测试时设置 `NO_PROXY/no_proxy=127.0.0.1,localhost`，使用独立 `APP_DATA_ROOT`，并增加冻结 hash、空间和资产边界验证。

**验证结果：**

`docs/interfaces/p0_verification_record.md` 记录 21 passed；HTTP 与 Gradio 结果均为 `LIVE_CASE`，位置 729/169/36，概率为 `0.025618407875299454`。

**今天留下的问题：**

单切片、本机 loopback、无完整对象级多用户授权，NIfTI、多切片、患者级和临床用途未完成。

**下一步计划：**

并行推进真实 Frontend、Backend 边界和独立 QA。

**关联文档或验收报告：**

- `docs/interfaces/p0_real_integration.md`
- `docs/interfaces/p0_verification_record.md`

### P0 Frontend 真实流程

**任务类型：** Frontend

**任务负责人：** 未记录。

**分支 / Worktree：** `feat/p0-frontend-real`；Worktree 路径在 Git worktree 记录中。

**关联 Commit：** `93d2e8f013d64979972bc88e7cbdba71007ca6b7`

**今日工作目标：**

让 Gradio 页面调用真实 Case/Slice/Prediction/Occlusion API，并在刷新后恢复 Job/Result。

**今天完成了什么：**

加入服务端 API client、真实 DICOM 页面、几何投影、16/32/64 px 图层和刷新状态；保留旧 PNG/JPG Mock 标签。

**为什么需要做这些工作：**

真实 API 只有在页面能正确展示来源、状态和图层时才可被团队联调。

**遇到了什么问题：**

无效 DICOM、网络错误、`MOCK` 来源和跨切片/几何不匹配需要拒绝叠加。

**问题原因：**

前端必须区分真实结果和旧兼容入口，并验证切片和坐标空间。

**最终如何解决：**

加入来源、切片、尺寸和仿射检查；失败只显示受控状态，不自动降级为 Mock。

**验证结果：**

分支报告记录 synthetic DICOM 真实上传、分类、三尺度遮挡和刷新恢复；它当时只代表分支级验收，需等待统一集成。

**今天留下的问题：**

当时未完成统一集成、认证和独立 QA。

**下一步计划：**

与 Backend 和 QA 分支合并到固定 P0 集成工作树。

**关联文档或验收报告：**

- `docs/interfaces/p0_frontend_integration_report.md`

### P0 Backend 边界

**任务类型：** Backend

**任务负责人：** 未记录。

**分支 / Worktree：** `feat/p0-backend-real`；Worktree 路径在 Git worktree 记录中。

**关联 Commit：** `3b400c39437ec6685b5f056fb039f9dcfe0bedb6`、`3aabb79803b318229740ec899c1eca524b1c1184`

**今日工作目标：**

补齐 Job 取消、幂等、失败脱敏和资产归属边界。

**今天完成了什么：**

修改 API、Job、存储和合同测试；增加 Backend integration report。

**为什么需要做这些工作：**

真实任务不能因为重复请求、错误输入或跨资源访问而产生不一致结果。

**遇到了什么问题：**

P0 仍是本机原型，Token 和逐对象授权不完整。

**问题原因：**

P0 的安全边界只覆盖 loopback 和可选 Bearer，尚未进入 Backend v2 的多用户模型。

**最终如何解决：**

固定 P0 范围，明确未完成接口返回 501，并保留后续 Backend v2 的独立设计。

**验证结果：**

分支报告记录 25 passed、真实 DICOM HTTP/Gradio smoke；只代表 Backend 分支。

**今天留下的问题：**

需要统一集成和独立 QA；不能把分支级测试写成最终基线能力。

**下一步计划：**

合并到 P0 集成线并执行固定 HEAD QA。

**关联文档或验收报告：**

- `docs/interfaces/p0_backend_integration_report.md`
- `docs/interfaces/p0_backend_contract_diff.md`

### P0 统一集成与独立 QA

**任务类型：** 集成 / QA

**任务负责人：** 未记录。

**分支 / Worktree：** `p0/integration` 和 `test/p0-integration-final-qa`。

**关联 Commit：**

- `ff2ad7c9bc6d005aecfa6d108166deeb27a43d70`
- `2130f3cfb4cbabc854cbcad3c412b893452c6338`
- `5a26141bf9a72444b7add19573900d9f7245e32f`
- 固定发布：`021e4f56103e53c82b5abf76465f62fb4f1bc6c3`
- 独立 QA：`b63c7d21d99bcd5fb26c586f0650b2aed19d3fda`

**今日工作目标：**

将 P0 Backend、Frontend 和 QA 分支合并到固定提交，并由独立 Worktree 复验。

**今天完成了什么：**

完成三次无冲突合并、Gradio 文件边界修正、Token-aware UI 和固定发布标签；独立 QA 在固定提交上运行全量测试、HTTP、浏览器和冻结检查。

**为什么需要做这些工作：**

分支级结果不能替代最终集成验证，尤其是权限、文件路由、Mock/LIVE_CASE 和冻结保护。

**遇到了什么问题：**

Token 模式下普通浏览器不能直接给 API Gradio 导航附加 Bearer；结果目录不能被通用文件路由暴露。

**问题原因：**

API 进程和浏览器 UI 的凭据边界不同；P0 文件路由必须限制到临时范围。

**最终如何解决：**

增加独立 `ui_server.py`，限制 `allowed_paths`，并保持真实错误不自动 Mock 回退。

**验证结果：**

`v0.1.0-p0-release` 固定提交；独立 QA 报告 82 passed、7 warnings，真实 HTTP、浏览器、Token/文件边界和 161/161 冻结哈希检查通过。

**今天留下的问题：**

仍是本机单切片原型，无公网部署、对象级多用户授权、正式 validation inference 或临床有效性。

**下一步计划：**

建立 Backend v2、Worker v1 和 Vue Frontend v1。

**关联文档或验收报告：**

- `docs/interfaces/p0_unified_integration_report.md`
- 独立 QA 分支的 `qa/final_p0_integration_qa_report.md`

## 2026-09-27｜Backend v2、Worker、Frontend 与 P1 QA

### Backend v2 与 Worker v1

**任务类型：** Backend / Worker

**任务负责人：** 未记录。

**分支 / Worktree：** `feature/backend-v2`、`feature/worker-v1`。

**关联 Commit：** `385cab52389a58f1c8493b452f663487ca2e7c0a`、`24d4fbf8674ce4f34070daebe006ea31ab13f647`、`5df1e05635bccbc872e7b697baf73957e96b4842`、`1f90321b7b6af9e2a69992c4259fd2dcf32944ed`

**今日工作目标：**

把 P0 本机任务外壳拆成 Backend 控制面和 Worker 执行面，并验证租约、heartbeat、结果资产和恢复。

**今天完成了什么：**

加入 Backend v2 API、Alembic schema、Case/Job/Result 服务，以及 Worker v1 claim/heartbeat/lease/result submit 和恢复逻辑。

**为什么需要做这些工作：**

后续系统需要结构化任务、可重试执行和明确的结果资产来源。

**遇到了什么问题：**

Worker 与 Backend 的状态、结果 payload 和冻结模型版本需要保持一致。

**问题原因：**

多组件系统中，Job 状态和结果提交不能依赖前端或本地文件约定。

**最终如何解决：**

冻结 Backend API、数据库和 Worker protocol，并增加 Worker v1 集成测试。

**验证结果：**

相关分支测试和协议文档已提交；随后通过 Phase 2 合并和 P1 QA 验证真实 CPU 流程。

**今天留下的问题：**

生产型 PostgreSQL/MinIO 和用户认证尚未完成。

**下一步计划：**

接入 Vue Frontend，并建立生产型本地栈。

**关联文档或验收报告：**

- `backend_v2/README.md`
- `worker/README.md`
- `docs/backend/backend_api_contract_v2_freeze.md`
- `docs/backend/worker_protocol_v1_freeze.md`
- `docs/backend/database_schema_freeze_v1.md`

### Vue Frontend v1

**任务类型：** Frontend

**任务负责人：** 未记录。

**分支 / Worktree：** `feature/frontend-v1`。

**关联 Commit：** `8a7952a1b0819e3db1630c3c486cf5544ef6a99a`、`345b336e8ed9698b79369451a39cecd2842913fe`

**今日工作目标：**

建立 Vue Dashboard、Case/Job/Result 页面，并接入 Backend v2 和 Cornerstone 单切片 Viewer。

**今天完成了什么：**

完成 Phase 1 页面骨架、Phase 2 API client、状态 stores、Result 页面、Cornerstone viewer 和集成测试。

**为什么需要做这些工作：**

Backend/Worker 结果需要有可维护的浏览器入口，而不是继续依赖 Gradio 原型页面。

**遇到了什么问题：**

需要处理 API 不可用、Job 状态、真实 Result、DICOM 几何和刷新恢复。

**问题原因：**

前端必须同时支持当前 P0/P1 契约和受控失败状态。

**最终如何解决：**

通过 stores、类型、Cornerstone viewer 和集成测试固定状态和显示边界。

**验证结果：**

分支级测试和构建通过；进入集成线后的最终能力以 P1 Phase 3.5/4.5 报告为准。

**今天留下的问题：**

当时还没有通用 Heatmap–CT spatial transform。

**下一步计划：**

进行认证、真实 CPU stack 和 Heatmap–CT 集成 QA。

**关联文档或验收报告：**

- `frontend/README.md`
- `frontend/docs/phase2_contract_notes.md`
- `frontend/src/viewer/`

### P1 Phase 2.5 安全 QA

**任务类型：** 集成 / QA

**任务负责人：** 未记录。

**分支 / Worktree：** `feature/p1-auth-security`、`codex/p1-phase25-integration-qa`。

**关联 Commit：** `df50656237e2ed63f7b6f7612dc290fdd395bde0`、`740e77c98e87ec3f81278116815195313a3678c5`、`c9a5cc6373ffc889725971e3cae5bc09252790bd`

**今日工作目标：**

建立用户/Worker 凭据分离、资源所有权和生产型存储的端到端安全边界。

**今天完成了什么：**

加入用户凭据表、认证 helper、迁移、provision/revoke 工具和安全测试；执行 PostgreSQL/MinIO、TLS Worker 和浏览器 QA。

**为什么需要做这些工作：**

P0 的 loopback 和单 Token 边界不能代表多用户对象授权。

**遇到了什么问题：**

迁移兼容、Owner/other user/anonymous 路由响应、Worker 与 User token 互用拒绝需要同时验证。

**问题原因：**

认证身份和资源所有权必须在 Backend、Worker、Result 和 Asset 层一致。

**最终如何解决：**

通过独立迁移测试、HTTP 权限矩阵、TLS Worker E2E 和前端服务端代理验证。

**验证结果：**

报告记录 Full Python 119 passed、Backend/Worker 37 passed、Frontend 21 passed，以及 PostgreSQL/MinIO 和真实 Worker 证据。

**今天留下的问题：**

GPU、Heatmap–CT fusion、公网生产部署和临床有效性仍未完成。

**下一步计划：**

执行 Worker 设备门控和 CPU reference 回归。

**关联文档或验收报告：**

- `docs/backend/p1_phase25_integration_qa.md`
- `docs/backend/auth_security_foundation_v1.md`
- `qa/evidence/p1_phase25/`

### P1 Phase 3 / 3.5 Worker 设备回归

**任务类型：** Worker / 集成 QA

**任务负责人：** 未记录。

**分支 / Worktree：** `feature/p1-gpu-worker`、`codex/p1-phase35-integration`。

**关联 Commit：** `396d188b6184ec08ce6b71e5f5b1dab7206dc00b`、`fd0e55ff52c20b58858e7ad26ff850e54bcd8a6d`、`02c8ef9c86d2b4aa338a38142bee25ee2234dc34`

**今日工作目标：**

明确 CPU/CUDA/AUTO 设备行为，并为未来 GPU 执行固定 CPU reference 比较门槛。

**今天完成了什么：**

加入设备选择、CUDA 拒绝、OOM 处理、benchmark、consistency 和 Phase 3.5 集成 QA。

**为什么需要做这些工作：**

不能在没有 NVIDIA/CUDA 的环境中把 CPU 回归写成 GPU 验收。

**遇到了什么问题：**

当前 Apple Silicon 主机没有 NVIDIA GPU，PyTorch CUDA runtime 为 `None`。

**问题原因：**

运行环境不具备实际 CUDA 执行条件。

**最终如何解决：**

显式报告 GPU 未验证，完成 CPU reference、CPU stack、权限和 Worker 回归。

**验证结果：**

Worker 29 passed，Backend 16 passed，Frontend 21 passed；CPU Prediction/Occlusion 完成，`LIVE_CASE`、9 assets、729/169/36；GPU numerical validation、benchmark、E2E 未执行。

**今天留下的问题：**

需要真实 NVIDIA 主机完成 GPU 数值、性能、长任务 heartbeat、OOM 和部署验证。

**下一步计划：**

完成 Heatmap–CT 2D 几何融合。

**关联文档或验收报告：**

- `docs/worker/p1_gpu_worker_phase3_report.md`
- `docs/worker/p1_phase35_integration_qa.md`
- `docs/worker/p1_phase35_cpu_stack_e2e.json`

### P1 Phase 4 Heatmap–CT 几何融合

**任务类型：** Frontend / QA

**任务负责人：** 未记录。

**分支 / Worktree：** `feature/p1-heatmap-ct-fusion`。

**关联 Commit：** `77ef944ec88db6992a16b395a13434d7065f4186`

**今日工作目标：**

在当前冻结预处理下，把授权 Heatmap 安全显示到 Cornerstone CT 上。

**今天完成了什么：**

完成 raw/model edge mapping、viewport affine、layer selector、opacity、hide/show、刷新恢复和 geometry QA fixture。

**为什么需要做这些工作：**

独立热图只有在切片、尺寸、来源、输入 hash 和 viewport 变换都匹配时才可叠加。

**遇到了什么问题：**

独立 `imageToWorldCoords` 在不等 spacing 和旋转 fixture 下与真实 StackViewport 不一致。

**问题原因：**

独立 helper 没有使用实际渲染 viewport 的 imageData 变换。

**最终如何解决：**

改用 `imageData.indexToWorld` 和 `worldToCanvas`，并在 camera/resize 后重算四角 affine。

**验证结果：**

分支报告记录几何单测、浏览器 marker、缩放/平移/resize 和刷新恢复；Frontend 32 tests、build 通过。

**今天留下的问题：**

API 仍没有通用 immutable `spatial_transform`；当前只允许精确版本 allowlist。

**下一步计划：**

在独立 P1 Phase 4.5 Worktree 合并并进行真实 CPU stack 集成验收。

**关联文档或验收报告：**

- `docs/frontend/heatmap_ct_geometry_contract.md`
- `docs/frontend/p1_phase4_fusion_report.md`

## 2026-09-28｜P1 Phase 4.5 集成验收

### Heatmap–CT Integration Acceptance

**任务类型：** 集成 QA

**任务负责人：** 报告角色为 Integration Lead；具体 Codex 执行者未记录。

**分支 / Worktree：** `integration/p1-phase45-heatmap-ct`；Worktree 为 `LOCAL_WORKTREE/EpiLocate-p1-phase45-integration`。

**关联 Commit：**

- 合并：`580b58ed2b5933c32198165e71be91198e2224de`
- 最终报告：`b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5`

**今日工作目标：**

在不修改 FrozenBaseline、Worker protocol、Backend API 和算法代码的前提下，完成 Phase 4.5 本地集成验收。

**今天完成了什么：**

合并 Phase 4 Frontend，运行 HTTPS Backend、PostgreSQL、私有 MinIO、CPU Worker 和 Vue 浏览器真实流程；检查上传、Prediction、Occlusion、Heatmap assets、刷新和所有权。

**为什么需要做这些工作：**

分支级几何通过后，需要验证它在完整 Backend/Worker/Frontend 栈中仍然可用。

**遇到了什么问题：**

报告仍把通用 spatial transform、GPU、3D registration、公网生产和临床有效性列为开放问题。

**问题原因：**

当前 API 只携带审计版本和来源信息，没有覆盖任意未来预处理的完整空间变换。

**最终如何解决：**

当前版本使用精确版本、输入 SHA、尺寸、图层语义和 viewport affine gate；不满足条件时关闭 overlay。

**验证结果：**

- Frontend 32 tests，build passed。
- Backend 16 tests。
- Worker 29 tests。
- PostgreSQL/MinIO round-trip passed。
- CPU Prediction/Occlusion `COMPLETED`，来源 `LIVE_CASE`。
- 9 个 Heatmap assets，位置 729/169/36。
- 浏览器 overlay、刷新恢复和所有权矩阵通过。

**今天留下的问题：**

GPU/CUDA、生产部署、通用 spatial transform、3D 配准、临床有效性和多切片/NIfTI 等仍未完成。

**下一步计划：**

等待负责人安排后续 Phase 5；不得把 Phase 5 预先写成已完成。

**关联文档或验收报告：**

- `docs/frontend/p1_phase45_integration_acceptance.md`
- `docs/frontend/p1_phase4_fusion_report.md`
- `docs/worker/p1_phase35_cpu_stack_e2e.json`

## 2026-09-28｜P1 Phase 5 开发分支工程记录

以下日期以报告执行日期或 Git 提交日期归档，不表示已还原每项工作的完整实际时间线。除报告明示的角色外，具体 Codex 执行者及未记录的排查过程证据不足。下列工作均在 `codex/p1-phase5-dual-mode-server-demo`、Worktree `LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo` 中发生；截至 `4d717a3753ef307ab370adeafaf5a00da4dc7af9` 未并入 `p0/integration`。各项状态只对该分支和所述环境有效。

### 1. Session Gateway / 多人浏览器入口

**任务类型：** Backend / 会话入口；**归档日期：** 2026-09-28（Git）。**任务负责人：** 未由提交证明，证据不足。

**开发前 HEAD / Commit：** `b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5` → `639bfec38283728b54b0b6ce7961df10ea9ec535`。

**目标与实际修改：** 让不同浏览器用户经 Session Gateway 登录，而 Backend Bearer 凭据留在服务端。新增各用户凭据映射、可撤销 SQLite 会话、Cookie/CSRF/限速与浏览器入口；Backend 所有权检查仍为最终边界。

**验证结果 / 状态：** Stage 1 报告记录 Gateway/Backend 19 passed、2 skipped，Worker 29 passed、Frontend 35 passed；此时仅为本地入口验证，尚无 GPU 或 ECS 新栈部署。后续 Stage 2 在本地完成两账户真实链路；本项不能据此写成 Stage 1 已验收远程 GPU。

**问题与未完成：** 当时需要独立 CPU Worker、真实存储和浏览器 E2E；具体编码排查顺序证据不足。

**证据：** `639bfec38283728b54b0b6ce7961df10ea9ec535` 的 `session_gateway/`、`docs/phase5/stage1_browser_entry_report.md`。

### 2. 独立 CPU Worker 本地全链路

**任务类型：** Worker / Backend / Frontend / 本地集成 QA；**归档日期：** 2026-09-28（Git/Stage 2 报告）。**任务负责人：** 未记录。

**开发前 HEAD / Commit：** `639bfec38283728b54b0b6ce7961df10ea9ec535` → `b07cfaefdeec4b382f530a8a22751b0ad8bafcfa`；报告提交 `e74f98432019eb46691e085b957fecb8e23ca1a3`。

**目标与实际修改：** 用与 Backend 分离的真实 CPU Worker 接入本地 PostgreSQL、MinIO、HTTPS Gateway 和 Vue 浏览器，覆盖两账户、Prediction、Occlusion、资产、租约与刷新恢复。

**验证结果 / 状态：** Stage 2 报告记录 Gateway/Backend 21 passed、Worker 29 passed、Frontend 36 passed 及构建通过；本地 `LIVE_CASE` 产生 729/169/36 个遮挡位置、9 个资产，并核查数据库与对象存储。**PASS：本地 CPU 工程链路**；macOS M5 Pro 和自签名 TLS 结果不是 ECS 或 CUDA 验收。

**问题与未完成：** GPU、目标服务器部署和生产容量仍未验证；不能用本地 CPU 时间推算 ECS 容量。

**证据：** `docs/phase5/stage2_cpu_worker_e2e_report.md`（`e74f98432019eb46691e085b957fecb8e23ca1a3`）。

### 3. 远程 GPU 接入准备与 ECS 只读审计

**任务类型：** 部署准备 / 环境审计；**归档日期：** 2026-09-28（报告及 Git）。**任务负责人：** ECS Stage 3B 记录为负责人授权，具体 Codex 执行者证据不足。

**开发前 HEAD / Commit：** `e74f98432019eb46691e085b957fecb8e23ca1a3` → `e3418783f669be0dc69060b55b42d4e7bad27365` → `7babd923c1d40d67c7abe4c0a0d957c60b8d4d0b` → `15d7b67b019df0dbf16afa93e447bde7b6d58b29`。

**目标与实际修改：** Stage 3A 整理部署门槛，Stage 3B 只读确认 ECS 的 Ubuntu x86_64、约 2 vCPU/3.5 GiB 内存、旧 Review/Nginx/TLS 和端口现场；随后增加远程 Worker 环境模板、SSH 转发候选配置与 4 项预检测试。准备报告还记录负责人提供的 RTX 3090、驱动及 PyTorch `2.4.0+cu121` 基础 CUDA 核验。

**验证结果 / 状态：** **PASS：限定范围的只读审计与配置预检**。Stage 3B 现场无新 PostgreSQL/MinIO 服务；`15d7b67...` 时未运行 FrozenBaseline CUDA、跨云 E2E 或新 ECS 部署。SSH 转发只是候选设计，最终 MVP 改用公网 HTTPS Worker API 与签名对象 GET。

**问题与未完成：** 当时防火墙/安全组、独立备份与恢复、峰值容量及 GPU 远程完整链路没有被此审计证明。负责人说明矩池云暂代本地 RTX 4050 计划节点；仓库只验证了矩池云节点，本地 RTX 4050 未见本阶段验收。

**证据：** `docs/phase5/stage3_ecs_readiness_report.md`、`docs/phase5/remote_gpu_node_preparation.md`、`qa/tests/test_remote_gpu_preflight.py`（分别见上述提交）。

### 4. GPU 节点本机 FrozenBaseline CUDA PoC

**任务类型：** Worker / 算法功能 QA；**执行与归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 报告未标明具体执行者。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** 在矩池云 RTX 3090 上用冻结 checkpoint 和仓库合成单切片运行真实 CUDA Prediction 与 16/32/64 px Occlusion；没有修改 FrozenBaseline、checkpoint、算法或 Worker 的 CPU/CUDA/AUTO 选择代码。本提交保存去敏 benchmark 摘要与报告。

**验证结果 / 状态：** **PASS：CUDA 功能执行**。PyTorch `2.4.0+cu121`，实际 device 为 `CUDA`；生成 729/169/36 个位置和 9 个 PNG。此项是 GPU 节点本机 PoC，不代表 CPU/GPU 数值等价或 ECS 远程持久化。

**问题与未完成：** 同次固定数值比较失败，见第 8 项；未凭 PoC 推断临床有效性或服务器容量。

**证据：** `docs/phase5/gpu_full_chain_mvp_report.md` 的 P0 与 GPU 环境部分、`docs/phase5/evidence/gpu_mvp/gpu-benchmark-summary.json`（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

### 5. ECS Control Plane MVP 部署

**任务类型：** Backend / 部署运维；**执行与归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 具体执行者未记录。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** 增加 `deploy/mvp/` 引导脚本、Nginx 路由、GPU Worker 启动脚本和四个新 systemd 单元；ECS 实际运行 Vue 静态站、Session Gateway、Backend v2、PostgreSQL、MinIO、Sweeper，旧 Review 根入口、Gradio 和 Aid 保留。新站仅在 `https://project.xbstu.com/mvp/` 作为测试入口；ECS 未启动 CPU Worker。

**验证结果 / 状态：** **PASS：本轮测试栈部署与服务检查**。报告记录四个新服务 active、Nginx `-t`、旧 `/healthz` 200、`/mvp/` 200、匿名 Case 401；`/mvp/` 构建及 ShellCheck 通过。PostgreSQL/MinIO 保持私有 loopback；GPU 节点使用独立 HTTPS 路径。

**问题与已确认处理：** 安全检查后抑制签名对象查询串访问日志，使用分离服务账户和更严格的凭据文件检查；最终复验见同一报告。部署记录没有证明医院正式环境或完整灾备能力。

**证据：** `deploy/mvp/`、`docs/phase5/gpu_full_chain_mvp_report.md` 的 Architecture、Resource、Changes and checks 部分（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

### 6. 远程 RTX 3090 GPU Worker E2E 与持久化

**任务类型：** Worker / Backend / 远程集成 QA；**执行与归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 未记录。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** GPU Worker 作为独立进程经 ECS HTTPS Worker API Register/Heartbeat/Claim/Submit，读取签名 HTTPS DICOM，运行 CUDA 并回传结果。运行方式为 GPU 节点 `tmux` 中的 `python -m worker`；提交新增可重用启动脚本及部署记录。

**验证结果 / 状态：** **PASS：指定 Worker 的远程工程链路**。两个 `LIVE_CASE` Job attempt 1 完成；PostgreSQL Result/Asset 行重读、MinIO 合成 DICOM 与 9/9 PNG 字节及 SHA-256 重核通过。Worker 日志记录 `CUDA`；数据库行本身不保存 `hardware.accelerator`。Worker 29 项回归和远程预检 4 项通过；它们不能替代实机 E2E，实机证据由报告独立给出。

**问题与未完成：** 领取窗口仅有指定 GPU Worker；未证明多 Worker 并发、实例释放持久性或自动崩溃重启。CPU Worker 代码仍保留，ECS 本轮未运行。

**证据：** `docs/phase5/gpu_full_chain_mvp_report.md` 的 P1、Remote Worker 与 Changes and checks 部分（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

### 7. Vue 浏览器真实链路

**任务类型：** Frontend / 浏览器 E2E QA；**执行与归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 未记录。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** 调整 Vue 路由与 Vite base path，使 `/mvp/` 子路径部署可重现；在公网 TLS 测试入口完成用户操作闭环。

**验证结果 / 状态：** **PASS：合成单切片浏览器 E2E**。Playwright Chromium 完成登录、DICOM 上传、Prediction、Occlusion、三尺度/图层、CT overlay、70% 透明度、刷新恢复和登出；报告附截图。Frontend 36 passed、`VITE_PUBLIC_BASE=/mvp/ npm run build` 通过。ECS 本轮只记录匿名 401；没有重新运行两账户授权矩阵，不能把 Stage 2 本地结果写成 ECS 两账户验收。

**问题与未完成：** 浏览器通过不代表临床有效性、数值等价、多用户吞吐或生产恢复。

**证据：** `frontend/src/`、`frontend/vite.config.ts`、`docs/phase5/gpu_full_chain_mvp_report.md` 的 P2 与 Browser evidence 部分、`docs/phase5/evidence/gpu_mvp/`（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

### 8. CPU/GPU 固定数值一致性失败

**任务类型：** 算法 QA / 未通过门槛；**执行与归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 未记录。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** 用固定 CPU reference 和容差比较 GPU PoC 结果，保留真实失败证据；未修改模型、checkpoint、CPU reference、算法或容差。

**验证结果 / 状态：** **FAILED / OPEN**，`comparison.passed=false`。派生数值最大绝对偏差 `0.0010498762130737305`，冻结容差 `0.0001`；224 个位置共 502 个派生路径失败。基础概率差 `0.00007169507443904877` 对其 `0.0001` 容差通过；解码 PNG 像素最大差 1 对容差 2 通过，但 9 个 PNG 字节哈希均不同。GPU CUDA 功能链路通过不能推出 CPU/GPU 可互换。

**问题原因 / 下一步：** 具体差异原因尚未确认；后续算法 QA 需独立分析，不得用改模型或放宽容差掩盖。

**证据：** `docs/phase5/gpu_full_chain_mvp_report.md` 的 Fixed CPU/GPU numerical comparison、`docs/phase5/evidence/gpu_mvp/gpu-benchmark-summary.json`（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

### 9. Production Hardening 未完成项

**任务类型：** 部署 / 安全 / 恢复待办；**归档日期：** 2026-09-28（MVP 报告/Git）。**任务负责人：** 后续负责人尚未在仓库指定。

**开发前 HEAD / Commit：** `15d7b67b019df0dbf16afa93e447bde7b6d58b29` → `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**目标与实际修改：** 记录 MVP 后仍需完成的生产门槛；本项是风险登记，不是“已完成加固”的提交。已做的服务账户分离、签名 URL 日志抑制、凭据文件模式检查不能替代以下工作。

**验证结果 / 状态：** **OPEN**。安装的 MinIO 配置静态加密为 false，SSE-S3 需要额外 KMS 或等效方案；Backend 仍用 MinIO root 凭据；GPU `tmux` Worker 无可靠自动重启；只有同盘回滚副本，缺独立异地备份及隔离恢复演练。CPU/GPU 数值门未通过；多用户吞吐、GPU 实例释放持久性和峰值资源未验证。

**下一步：** 分别评审数值差异、存储加密与最小权限、Worker 生命周期、异地备份恢复及容量。当前 `/mvp/` 是工程测试入口，不能标成 Production Ready。

**证据：** `docs/phase5/gpu_full_chain_mvp_report.md` 的 Remaining risks、Resource and deployment observations、Stop and rollback 部分（`4d717a3753ef307ab370adeafaf5a00da4dc7af9`）。

## 2026-09-28/29｜Phase 5 最终交接、GPU Job 事故与工程收敛准备

日期按报告执行时间或 Git 归档时间标注；没有依据时不补猜执行者。Phase 5 实现来源分支为 `codex/p1-phase5-dual-mode-server-demo`，Worktree `LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；未进入 `p0/integration`。收敛准备另在 `codex/repository-consolidation-v1` Worktree `LOCAL_WORKTREE/EpiLocate-consolidation-v1` 完成。

### 1. GPU Full-Chain MVP Final Handoff

**归档 / 执行日期：** 报告称 2026-09-28 22:50–23:05；Git commit `352152ce95fc26eb2dc0a4c309521d50486472ba`。**任务类型：** GPU E2E / 最终交接。**负责人：** 报告未指明具体执行者。

**Branch / Worktree / 开发前 HEAD：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；`4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**工作与证据：** 最终交接报告及运维说明、浏览器摘要、持久化审计和渲染完成截图。新 synthetic Case 经 Vue 登录/上传、Prediction、16/32/64 Occlusion、9 个 Heatmap Assets、三图层/CT Overlay、70% 透明度与刷新恢复；指定 RTX 3090 GPU Worker 的两任务完成，PostgreSQL/MinIO 的 DICOM 和 9 个对象复读哈希匹配。

**结果：** **PASS：该次 GPU-only Engineering MVP 功能验收。** Vue、Session Gateway、Backend v2、PostgreSQL、MinIO、Sweeper 和远程 GPU Worker 参与；ECS CPU Worker 未启动，Worker CPU/CUDA/AUTO 路径保留。不是 Production Ready、Clinical Ready 或正式医疗系统验收。

**未完成 / 后续：** CPU/GPU numerical consistency 仍 FAIL/OPEN，GPU Worker 自动重启、实例释放后持久性、异地备份/恢复及生产加固未完成。

**来源：** `docs/phase5/gpu_final_handoff_report.md`、`docs/phase5/gpu_worker_mvp_operations.md`、`docs/phase5/evidence/gpu_final/`（`352152ce95fc26eb2dc0a4c309521d50486472ba`）。

### 2. GPU Job Failure Regression

**归档日期：** 2026-09-29；事故时间窗由报告记录。**任务类型：** Worker / 用户流程回归。**负责人：** 未记录。

**Branch / Worktree / Commit：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；报告提交 `f80d4cf406689cd031f993090783e281db93c4ef`，起点 `352152ce95fc26eb2dc0a4c309521d50486472ba`。

**工作与证据：** 确认两项历史 Prediction 与 Occlusion Job 执行后失败；保持原失败记录及无 Result 状态。关联调查证据不进入公开快照。

**结果：** **FAIL（历史 Job 状态永久如实记录）。** 两项均 attempt 1 `FAILED`、无重试；不能由修复后的新任务改写成成功。

**后续：** 事故调查核对对象完整性和环境依赖，并通过新任务复验。

**来源：** 本快照中仅保留机制说明的 `docs/phase5/gpu_failed_job_incident_20260929.md`；受限调查证据留在内部历史。

### 3. Failed Job Incident Investigation

**归档日期：** 2026-09-29（报告审计时间 09:50–10:08）。**任务类型：** GPU Worker / Backend 事故调查。

**Branch / Worktree / 开发前 HEAD / Commit：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；`352152ce95fc26eb2dc0a4c309521d50486472ba` → `f80d4cf406689cd031f993090783e281db93c4ef`。

**调查内容：** 对照 PostgreSQL Job/attempt/Result、Worker 领取与心跳、MinIO 对象大小/hash、HTTPS 下载和 GPU 环境解析结果。两 Job 已被 Worker Claim 并提交失败，失败早于租约过期；不是 Worker 未运行、心跳丢失、超时/重试耗尽或结果资产上传失败。

**结果：** **根因调查 PASS：证据确认运行环境解析失败。** Worker 日志当时只有通用失败行而无 traceback，Backend/Sweeper journal 也无相应 Job 细节；因此原始故障日志本身不足以定位，原因由同一对象在节点上的受控只读复现确认。

**未完成 / 后续：** Worker 日志需补充不含影像元数据、凭据或签名 URL 的错误类型及安全上下文。

**来源：** `gpu_failed_job_incident_20260929.md` 的公开机制说明；详细调查记录留在内部证据链。

### 4. JPEG Lossless Decoder Root Cause

**归档日期 / 来源 Commit：** 2026-09-29 / `f80d4cf406689cd031f993090783e281db93c4ef`。**任务类型：** DICOM 解码故障分析。

**Branch / Worktree / 开发前 HEAD / Commit：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；起点 `352152ce95fc26eb2dc0a4c309521d50486472ba`，归档提交 `f80d4cf406689cd031f993090783e281db93c4ef`。

**确认原因：** 输入使用 JPEG Lossless Process 14（`1.2.840.10008.1.2.4.70`）。对象完整性核对通过；GPU 节点 pydicom `3.0.1` 访问 `pixel_array` 明确报缺少 JPEG Lossless decoder plugin。安装解码器后，受控复现解码为 `(512, 512)`、`int16`。没有证据把此次直接原因归到模型、协议或影像损坏。

**结果：** **根因已确认：E（DICOM 像素解析）+ J（GPU 环境依赖缺失）。** `requirements.txt` 已声明这两项依赖，但实际 GPU runtime 未安装；Backend READY 只检查 header，未覆盖 GPU 节点 PixelData 解码能力。

**未完成 / 后续：** 部署预检应使用获批的脱敏 Transfer Syntax fixture 验证实际 Worker runtime。

**来源：** 事故报告的 Root Cause 与受控环境复现；详细证据留在内部历史。

### 5. GPU Runtime Dependency Recovery

**归档日期 / 来源 Commit：** 2026-09-29 / `f80d4cf406689cd031f993090783e281db93c4ef`。**任务类型：** Worker 运行环境运维恢复。

**Branch / Worktree / 开发前 HEAD / Commit：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；`352152ce95fc26eb2dc0a4c309521d50486472ba` → `f80d4cf406689cd031f993090783e281db93c4ef`。

**实际操作：** 停止原 Worker 后，在隔离 Conda Python 环境只补装 `pylibjpeg==2.1.0`、`pylibjpeg-libjpeg==2.4.0`，再用现有 `run_gpu_worker.sh` 恢复 RTX 3090 Worker。恢复日志再次记录 `CUDA`，Backend 心跳恢复。报告确认 FrozenBaseline、checkpoint、PyTorch `2.4.0+cu121`、NumPy `2.0.0`、Worker/API 协议、容差和 DICOM 均未变；ECS CPU Worker 未启动。

**结果：** **PASS：事故节点手工恢复。** 此为 GPU 节点环境的人工修复，不是可复现镜像/锁文件/部署流水线验收。现有 requirements 声明并不证明该 GPU runtime 已可重建。

**后续：** 将依赖纳入可复现 GPU 环境，并在环境重建时用脱敏 JPEG Lossless fixture 检查；该项保持 OPEN。

**来源：** 事故报告“最小修复与回滚”、`gpu_worker_mvp_operations.md` 更新（`f80d4cf406689cd031f993090783e281db93c4ef`）。

### 6. GPU Recovery Revalidation

**归档日期 / 来源 Commit：** 2026-09-29 / `f80d4cf406689cd031f993090783e281db93c4ef`。**任务类型：** Worker / Browser / PostgreSQL-MinIO E2E。

**Branch / Worktree / 开发前 HEAD / Commit：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；起点 `352152ce95fc26eb2dc0a4c309521d50486472ba`，复验记录 `f80d4cf406689cd031f993090783e281db93c4ef`。

**实际验证：** 新建 Prediction 与 Occlusion，并另以仓库 synthetic fixture 新建同类任务。两轮 Worker assignment 指向指定 RTX 3090 节点，attempt 1 成功。关联任务标识不进入公开快照。

**结果：** **PASS：当时两轮修复后 GPU E2E。** 两组新 Job 均 COMPLETED / LIVE_CASE；每轮 9 个 Heatmap assets、729/169/36 positions。PostgreSQL/MinIO 对输入与全部资产复读大小/hash 匹配，浏览器结果和刷新恢复通过。

**边界 / 后续：** 两笔最初失败 Job 仍为 FAILED；修复后成功的是新 Job。事故报告称当时服务检查通过，不证明当前持续可用。CPU/GPU numerical consistency 仍 FAIL/OPEN。

**来源：** 本快照的机制说明与合成证据；受限调查证据仅保留在本地内部历史。公开快照有独立 Git root。

### 7. Architecture Boundary Audit

**归档日期 / 来源 Commit：** 2026-09-29 / `718d3220a2191aba0dd8fbfe1d673546997d1c04`。**任务类型：** 架构边界只读审计。**负责人：** 提交不证明具体执行者。

**Branch / Worktree / Base：** `codex/repository-consolidation-v1`；`LOCAL_WORKTREE/EpiLocate-consolidation-v1`；`352152ce95fc26eb2dc0a4c309521d50486472ba`。

**实际工作：** 对照固定来源分支和目录，形成组件来源与目标路径映射；定义迁移阶段，并识别 `algorithm/`、`src/`、`scripts/`、`configs/` 的研究冻结/运行时依赖边界以及 `gradio_service/` 的现有运行依赖。该项是“工程边界确认 / 收敛准备”，不是源码已迁移。

**结果：** **PASS：Phase 0 规划审计材料已提交。** 没有业务源码复制或移动。

**未完成 / 后续：** Phase 1 起的导入、接口/路径调整及验收均为后续独立阶段；迁移前需再核验各固定来源。

**来源：** `docs/consolidation/SOURCE_MAP.md`、`MIGRATION_PLAN.md`（`718d3220a2191aba0dd8fbfe1d673546997d1c04`）。

### 8. Canonical Source Map Audit

**归档日期 / 来源 Commit：** 2026-09-29 / `718d3220a2191aba0dd8fbfe1d673546997d1c04`。**任务类型：** Source Map / 仓库文档审计。

**Branch / Worktree / Base / Commit：** `codex/repository-consolidation-v1`；`LOCAL_WORKTREE/EpiLocate-consolidation-v1`；基线 `352152ce95fc26eb2dc0a4c309521d50486472ba`，Source Map 提交 `718d3220a2191aba0dd8fbfe1d673546997d1c04`。

**已记录映射：** Landing `flow-fluidity/` 来自 `research/stage1-validation-backup` @ `f59738a606d15ff7062bbc64fc316ba276035ce4`；AI Web `frontend/`、Showcase `aid_site/`、Review `epilocate_review_server/`、Backend `backend_v2/`、Gateway `session_gateway/`、Worker `worker/`、Deployment `deploy/mvp/` 均指向 Phase 5 canonical source branch `codex/p1-phase5-dual-mode-server-demo`，文档/验收 HEAD 为 `352152ce95fc26eb2dc0a4c309521d50486472ba`，应用/部署实现基线为 `4d717a3753ef307ab370adeafaf5a00da4dc7af9`。

**结果：** **PASS：迁移规划来源映射已记录。** Phase 5 Source Map 不把旧 `feature/frontend-v1`、旧 Backend Worktree 或旧 Worker Worktree 列为当前部署主线。

**未完成 / 边界：** 目标 `apps/`、`services/` 业务路径尚未建立，Source Map 不表示迁移、线上切换或唯一不可变的未来架构已完成；开始各 Phase 前须重验分支和目录。

**来源：** Source Map 表、Phase 5 最终交接报告及对应 Git 提交关系。

### 9. Repository Consolidation Plan

**归档日期 / 来源 Commit：** 2026-09-29 / `718d3220a2191aba0dd8fbfe1d673546997d1c04`。**任务类型：** 仓库迁移分期规划。

**Branch / Worktree / Base / Commit：** `codex/repository-consolidation-v1`；`LOCAL_WORKTREE/EpiLocate-consolidation-v1`；基线 `352152ce95fc26eb2dc0a4c309521d50486472ba`，计划提交 `718d3220a2191aba0dd8fbfe1d673546997d1c04`。

**工作：** 写明 Phase 1 来源收口与 Landing 路径导入、Phase 2 应用与服务逐批迁移、Phase 3 验收/develop 主线评估/归档闸门；规划中保留冻结算法和运行依赖，要求迁移、构建与线上切换分别核验，保护历史 Worktree 独有文件。

**结果：** **PASS：迁移计划文档已建立。** 计划本身不代表各 Phase 获准执行或已完成。

**已批准但未执行决策：** Frozen research runtime 本阶段不迁；`develop` 目标为 Engineering MVP 主线但须等待收敛验收。本次只读核验时 `develop` Worktree 仍在 `021e4f56103e53c82b5abf76465f62fb4f1bc6c3`；历史 Worktree 归档后分批移除且不用 force remove；Welcome Landing 仅列入代码规划，不改生产域名/Nginx/Review root。

**来源：** `docs/consolidation/MIGRATION_PLAN.md`、`archive/README.md` 和负责人本轮明确的决策边界。

### 10. Consolidation Phase 0

**归档日期 / Commit：** 2026-09-29 / `718d3220a2191aba0dd8fbfe1d673546997d1c04`。**Branch / Worktree / Base：** `codex/repository-consolidation-v1`；`LOCAL_WORKTREE/EpiLocate-consolidation-v1`；`352152ce95fc26eb2dc0a4c309521d50486472ba`。

**实际修改：** 新增 `apps/README.md`、`services/README.md`、`docs/consolidation/README.md`、`docs/consolidation/SOURCE_MAP.md`、`docs/consolidation/MIGRATION_PLAN.md`、`archive/README.md`。

**结果：** **PASS：Consolidation Preparation Completed。** 仅有目录说明、Source Map、迁移计划及 Archive 规划；未移动业务源码、修改 imports/运行路径/部署/服务器、删除 Worktree。不能称为 Repository Migration Completed。

**后续：** 每个后续 Phase 单独审计、提交与验收；Phase 0 不改变 `develop` 或线上服务。

**来源：** commit diff 的 6 个 Markdown 文件与 Consolidation README。

### 11. Frontend Handoff Preparation 与 Backend API Docs

**归档日期：** 接口文档 Commit 为 2026-09-28；Frontend 交接安排为负责人本轮说明，实际 UI 重构日期和执行者尚无证据。**任务类型：** 文档接口交接 / Frontend 责任边界。

**接口文档分支 / Worktree / Commit：** `docs/backend-api-phase5-gpu-mvp`；`LOCAL_WORKTREE/EpiLocate-backend-api-phase5-gpu-mvp`；`ab36dea60e518ae86d8b9749d876d94d2102511d`（本地远端跟踪引用指向同一提交）。该分支新增 Backend API Contract、Frontend Integration Guide、Session Gateway 与 Worker API/job lifecycle 文档，并对齐文档到 Phase 5 实现。

**Frontend 交接范围：** Phase 5 `frontend/` 是 UI Canonical Source。负责人将 Login、Case UI、Job UI、Viewer、Heatmap/Overlay、Router、Pinia 和 Frontend tests 交给陈奕冰；Landing、Showcase、Review、Backend、Gateway、Worker、Deployment、FrozenBaseline 与核心算法不在其负责范围。此为任务边界；本轮证据没有 UI 重构完成提交。

**结果 / 状态：** **PASS：接口文档版本与交接边界已识别；UI 重构尚未验收。** Backend API docs 在独立分支，未纳入 `p0/integration` 或 Phase 5 应用基线；必须注明版本 Commit，不能反推当前集成实现。

**来源：** `ab36dea60e518ae86d8b9749d876d94d2102511d`、Consolidation `SOURCE_MAP.md`、负责人交接任务说明。

### 12. Current Open Issues 与 Live Availability

**记录日期：** 2026-09-29（按当前可获得的报告归档）。**任务类型：** 集成状态和后续 QA 交接。

**相关 Branch / Worktree / Commit：** Phase 5 分支 `codex/p1-phase5-dual-mode-server-demo`、`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`，最终 GPU 报告 `352152ce95fc26eb2dc0a4c309521d50486472ba`、事故报告 `f80d4cf406689cd031f993090783e281db93c4ef`；架构收敛分支 `codex/repository-consolidation-v1`、`LOCAL_WORKTREE/EpiLocate-consolidation-v1`，规划提交 `718d3220a2191aba0dd8fbfe1d673546997d1c04`。

**OPEN：** CPU/GPU fixed numerical consistency FAIL（derived max `0.0010498762130737305` vs `0.0001`）；Frontend FAILED Job UX 仅显示通用消息，缺可安全展示的错误类型和用户重试建议；Worker 缺少充分且脱敏的 traceback/error context；GPU runtime 虽 requirements 已声明 JPEG Lossless 依赖，但实际环境曾漏装，环境重建可复现性仍未证明。另有 Worker 自动重启、实例释放持久性、异地备份/恢复、MinIO at-rest encryption、Backend root credential、容量/并发和生产/临床验收未完成。

**CURRENT LIVE AVAILABILITY: PENDING REVALIDATION。** 可取得的最后报告只记录 2026-09-29 10:08 前的修复后检查/E2E；没有更晚 Live Regression Audit。某次 E2E PASS 只说明该次验收通过，不能说明当前线上始终可用。

**下一步：** Frontend 重构中设计安全错误状态和 Retry guidance；Worker/平台完善不泄密的诊断与可复现 GPU 依赖；另行分析数值差异，完成恢复/生产审查并重跑实时验收。以上均未在本次历史报告中记为已完成。

**证据：** `gpu_failed_job_incident_20260929.md` 的 Open Issues 与检查时间、`gpu_final_handoff_report.md` 的 Remaining Open Issues、`gpu_worker_mvp_operations.md` 的依赖恢复边界、`MIGRATION_PLAN.md` 的后续闸门。

### 13. Pre-Handoff Release Remediation 本地候选

**归档日期：** 2026-09-29。**任务类型：** 文档整合、Landing 导入、GPU 依赖与部署来源机制、发布安全审计。

**分支 / Worktree / 开发前 HEAD：** 内部隔离 Handoff Worktree 从 `f80d4cf406689cd031f993090783e281db93c4ef` 构建，审计候选提交为 `d498f0465f6b7d0e4d999562658356a734211bfa`。公开的 `handoff/pre-b-transfer-20260929` 由该候选文件树建立独立 Git root，不继承内部提交历史。

**目标与改动：** 从固定 Phase 5 事故后提交建立可交接候选，整合 Engineering Docs `c312d393`、Consolidation `f5438fe`、Backend API Docs 当前 `4ae2e59` 的有效 Markdown；从研究分支逐路径导入 Landing 至 `apps/landing/`，把按钮指向 `/mvp/`；添加 GPU Worker runtime 固定版本清单、准备固定 Git Commit release 的脚本和 `SOURCE_COMMIT` 标记要求；对三份 Word 制作元数据清理副本；删除候选顶端的原病例关联 JSON 并简化事故叙述。

**问题与原因：** 内部候选的历史包含受限证据。仅删除候选顶端文件，普通 Git push 仍会传送祖先 blob。经授权，从已审计文件树建立独立 sanitized Git root；完整内部历史保留在本地，未改写或推送。

**验证结果：** Landing `npm ci && npm run build` 通过；Vue `npm ci && npm test && VITE_PUBLIC_BASE=/mvp/ npm run build` 通过（36 tests）；本机隔离依赖环境执行 Backend、Gateway、Worker 与文档测试得到 51 passed、2 skipped。Word 元数据和内容结构审计通过；使用原生 Word 导出逐页复核进行中。GPU 新节点依赖重建与线上 E2E 尚未执行。

**状态与下一步：** 公开快照在本地完成逐文件核对；待 Word 全页复核、全可达 Git objects 的 Secret / PHI 扫描及文档检查通过后，仅普通 push 指定 Handoff 分支，再从全新 clone 验证与执行固定提交部署。未动 FrozenBaseline、checkpoint、容差、生产服务或 `develop`。

**证据：** `docs/handoff/HANDOFF_STATUS.md`、`RELEASE_SECURITY_AUDIT.md`、本候选 Git diff 与本次测试命令输出。

### 14. Sanitized Git root 与 Welcome 浏览器修复

**归档日期：** 2026-09-29。**任务类型：** 公开交接快照、固定提交回归与 Welcome CSP 修复。

**分支 / 来源：** 独立 `handoff/pre-b-transfer-20260929` Git root；内部候选 SHA 为 `d498f0465f6b7d0e4d999562658356a734211bfa`，不是公开 Git 祖先。公开首个候选提交 `39440e05c99562a7a01805dd09a4955ba4933a55`。

**完成与证据：** 候选文件逐字节对照后，排除含影像对象定位符的下载清单，完成三份 Word 全页复核，并扫描公开 root 全部可达 Git objects。仅普通 push Handoff ref。全新 GitHub clone 的 Landing、Vue、Backend/Gateway/Worker、文档链接与 `SOURCE_COMMIT` 导出验证通过。ECS 从 GitHub SHA 建立独立候选 release，服务器本机构建 Landing/Vue；初次 Welcome HTTP 200，原 `/mvp/` 与 Review 健康检查保持 200。

**问题与修复：** 浏览器控制台记录三张缩略图经外部图片服务重定向后触发 CSP `img-src` 拦截。将最终媒体域名纳入 `deploy/mvp/nginx-welcome.conf` 并普通推送提交 `649b0c665971cfefcc67509849947b2d3f7e49c7`。ECS 从该 GitHub SHA 重新导出与构建；Nginx 检查、桌面和移动浏览器视觉复核通过，浏览器控制台无错误。`/welcome/`、`/mvp/`、Review root 和健康端点保持可达；Backend/Gateway/Sweeper 运行目录与 `SOURCE_COMMIT` 指向同一固定 release。运行时 Python 虚拟环境复用上一 release，未宣称依赖从零重建。未修改模型、FrozenBaseline、容差或生产数据。

### 15. GPU 主动释放与非 GPU 交接继续推进

**日期：** 2026-09-29。**负责人说明：** GPU AI Node 已主动暂时释放，状态为 **TEMPORARILY OFFLINE / INTENTIONALLY RELEASED**；不是新系统故障。旧 SSH 不再重试。GPU architecture 为 **PREVIOUSLY VALIDATED**，历史 GPU 功能 E2E PASS 不改写；Final Git-based GPU E2E 为 **PENDING GPU RE-PROVISION**。

**继续工作：** Word 全页 QA、公开 root 全可达 Git objects 扫描、GitHub sanitized branch、全新 clone 回归、ECS Git-based candidate release、Landing/Welcome 浏览器复核和交接文档均独立于 GPU。下一文档提交仍需对象重扫、普通 push、全新 clone 与 ECS `SOURCE_COMMIT` 对齐。Frontend redesign branch 可从最终 sanitized Handoff SHA 在本地准备；远端分支推送等待最终 GPU 门槛。

**暂停工作：** GPU Worker deployment、GPU `SOURCE_COMMIT` validation、synthetic GPU E2E、CUDA runtime revalidation。获得新 SSH host/port 后，从最终 Handoff Git SHA 重建 RTX 3090-class CUDA Worker；保留 PyTorch `2.4.0+cu121`、固定 Worker 依赖、`pylibjpeg==2.1.0`、`pylibjpeg-libjpeg==2.4.0` 和已核验 FrozenBaseline checkpoint hash。不得用 ECS CPU Worker 替代最终 GPU 验收，也不修改 FrozenBaseline 或 CPU/GPU tolerance。

## 未来记录模板

后续 Codex 在完成实际工程迭代时，追加以下结构，不覆盖已有历史：

```markdown
### YYYY-MM-DD｜任务名称

**任务类型：** Backend / Frontend / Worker / QA / 集成 / 部署 / 文档
**任务负责人：** 仅在会话或报告明确时填写
**分支 / Worktree：** 完整路径和分支名
**开发前 HEAD：** 完整 SHA
**关联 Commit：** 完整 SHA
**今日工作目标：**
**今天完成了什么：**
**为什么需要做这些工作：**
**遇到了什么问题：**
**问题原因：** 已确认原因；否则写“尚未确认”
**最终如何解决：**
**验证结果：** 命令、数量、环境和证据路径
**今天留下的问题：**
**下一步计划：**
**关联文档或验收报告：**
```

### 2026-10-01｜前端稳定性第一轮与根工程记录收敛

**任务类型：** Frontend / QA / 文档。
**任务负责人：** Codex 执行，用户授权；未推断其他人员的实际操作。
**分支 / Worktree：** `feature/frontend-redesign-phase5`；独立本机 `work/EpiLocate` checkout。
**开发前 HEAD：** `008c81e8d0545c32f59d16890ea987f59614c87c`；本次后续审查起点 `9dbdf6372c4b33571a47a0a99adbaa6ff2ce9d14`。
**关联 Commit：** `0a93c7dfcb2c22070337ed20264467e4e0079716`、`8447f7b5246d8e146e176b09f872f9bd958f7a32`、`9dbdf6372c4b33571a47a0a99adbaa6ff2ce9d14`。
**目标与完成：** 按第一轮计划修复会话隔离、异步响应与影像资源清理、安全错误归一化、任务失败/查询恢复、影像及图层局部重试；增加 36 项回归测试、本地合成 DICOM 浏览器工具、页面审计及下一轮草图。
**问题与原因：** 单纯清空缓存不能阻止旧请求重新写回；旧401/退出响应可能清理新账号。用 session epoch、认证 request generation、病例/页面版本与 AbortController 联合保护，并在消费响应及执行清理前校验。错误 envelope 与 Job failure_reason 差异用安全稳定码归一化；不呈现原始异常，不自动重跑推理。
**环境问题：** 系统 Node 20.16.0 与锁定 jsdom ESM 兼容失败；改用已验证 Node 24.19.0，不变更依赖锁。基线及修改版均有 Cornerstone codec 外部化和 bundle 大小警告，未宣称已修复。
**验证结果：** `npm ci` 安装 314 个锁定依赖；基线 36/36 和 build，通过；修改后 `npm run test` 72/72（13 spec）及 `npm run build` 通过。本地 Edge 13 场景、13 截图、0 page error；6 组 5-marker 几何测量最大 0.3031 CSS px。全部 auth/业务 API 拦截为合成数据；实际 Cornerstone 解码和渲染，非线上/GPU E2E。
**门禁收敛：** 首次执行 `scripts/check_project_documentation.py --base 008c81e8d0545c32f59d16890ea987f59614c87c --working-tree` 为 FAIL，因为原授权仅限 frontend，根两份日志未改。用户随后扩大必要目录审查授权，故追加根记录；复验结果随交付报告更新，不改检查器或历史日志。
**留下的问题：** 真实账号及恢复后的 GPU 推理未验收，CPU/GPU 固定数值门槛仍 OPEN；尚未 push、merge、部署。下一步完成合并前审查，真实账号验证，再由负责人决定发布与 GPU E2E。
**关联报告：** `frontend/docs/FIRST_ROUND_AUDIT.md`、`frontend/docs/first-round-visual-sketch.html`；本机交付 `outputs/frontend-qa/browser-acceptance.json`。本轮代码范围仍为 frontend；新增根日志属于本次必要文档收敛。

**扩大审查后的修复与复验：** 核对 Gateway 共享 Cookie 与依赖实现发现跨tab身份不同步、core/dataset/NATURALIZED缓存未随renderer销毁释放；采用无凭证storage失效通知和窗口恢复校验、按imageId资源清理并处理迟到解码。检查期间阻止业务请求，通知接收/校验失败不循环广播，登录跳转目标在请求前固定。原APIclient测试补齐明确会话前置状态。最终 81/81 tests（14 spec）及 build PASS；15 个本地浏览器场景 PASS、0 page error，真实 Cornerstone 两种影像卸载后 image/metadata cache 为空。第一次双tab脚本错误假设主动退出后返回病例页，已按实际首页跳转修正并重新完整通过。文档检查与 diff 检查 PASS；没有改变后端或部署。

### 2026-10-01｜第一轮前端推送与独立服务器发布

**任务类型：** 前端发布 / QA / 文档。**授权：** 用户明确指示上传服务器并推送。
**分支 / 开始HEAD：** `feature/frontend-redesign-phase5` @ `3ad9fbc0d8dba4b16585c94dd16f5375be276f98`；本机独立checkout。**关联应用提交：** 同一完整SHA。
**完成：** 解除浅克隆并扫描完整Git closure（636 objects/488 blobs），普通push指定分支，SSH核对远端SHA；从固定提交导出frontend并以SHA256核对传输，服务器Node24.21.0执行npm ci（314packages）、81/81测试（14spec）及/mvp/构建。原线上package/lock/vite/API types与Git blob哈希相同，契约未换。
**问题与处理：** 服务器访问GitHub HTTPS超时，改为从已推送提交导出源码传输，不传私钥/环境。第一次Nginx重载后即时请求读到旧首页，自动回滚成功；核对其哈希属于旧版后增加最长10秒重复内容校验，第二次激活PASS。本机浏览器默认DNS导航超时；按已核实IP映射域名且保持TLS验证后检查通过。
**验证：** 实际/mvp/首页及2个入口JS/CSS字节一致；mvp200、无Cookie/auth/session和/api/v2/cases401、Welcome200、Review303；Backend/Gateway/Sweeper/MinIO active且current仍为原4e38fd...release。真实未登录桌面/移动登录UI、受保护route跳转、键盘焦点、无水平溢出通过，0page error/资源失败。
**回滚：** 旧release保留，新frontend目录nginx-before.conf保留原root配置；仅恢复前端配置并检查/reload即可，不改控制平面current。新目录保留旧hashed assets用于已开标签页兼容。
**剩余：** 授权真实账号操作与GPU恢复后的真实推理未验收；视觉重构属于下一轮。CPU/GPU数值/临床有效性仍非此次前端发布证据。
**报告：** `frontend/docs/DEPLOYMENT_20261001.md`；本机交付 `publication-scan.json`、`server-frontend-activation.json`、`live-frontend-acceptance.json`及登录截图。记录提交只补文档，不更换线上应用SHA。

### 2026-10-02｜第二轮医学影像工作台视觉重构

**类型：** Frontend/QA；用户授权实施并完成后发布。**分支/起点：** feature/frontend-redesign-phase5，`a97a34688d5e5057681ecdcc38340adf1be3cd05`，本机独立work/EpiLocate checkout。
**完成：** Login叙事/表单双栏、可访问导航、真实病例首页、中文输入状态、Case/Job流程上下文、CT优先Result工作台、折叠来源、响应式字号和44px控件。首页用既有Case API limit6不改分页store，generation/epoch/abort隔离。
**发现和处理：** 手机菜单开着进入桌面会残留inert，增加断点监听清理/焦点返回/测试；200%放大双栏挤压画布，增加容器查询。jsdom无matchMedia及inert布尔反射与浏览器不同，补明确测试环境与使用true/undefined属性；没有移除安全检查来让测试通过。
**验证：** 85/85测试15spec、TypeScript/build PASS，本地Edge合成API18场景19截图0page error；五宽度/200%CSS放大/键盘/Escape/断点恢复；六组新尺寸画布几何最大0.3222CSSpx，真实core/NATURALIZED清理PASS。保留原构建警告。
**边界：** 无新增接口/部署模板/后端/算法变更；真实账号和GPU E2E仍未实测。发布结果将在操作完成后补录。报告frontend/docs/SECOND_ROUND_REPORT.md。

**本轮实际发布：** 2026-10-02，应用 `988328f53c44a1542e95707951163a14d7b9eb05` GitHub普通push并核对。扫描673objects/507blobs无阻断；固定frontend归档SHA256核对，服务器Node24.21.0锁定安装、85/85测试15spec及/mvp/构建PASS。准备脚本初次CRLF在开始时退出，转LF后重跑通过，失败时未切换线上。Nginx配置备份/检查/reload与资源字节核对PASS，仅改前端root，控制平面current保持4e38fd，四项服务active。外部Edge新版登录桌面/手机、保护跳转、键盘、无横向溢出PASS，0page error/资源失败。mvp200、无Cookie身份/病例401、Welcome200；Review斜杠307/无斜杠401与上一轮303证据不同，仅记录，不改此应用。真实账号/GPU未验收。旧目录/hashed assets与nginx-before.conf保留；报告及本机发布JSON补录，文档提交不改变应用SHA。

### 2026-10-03｜Clinical Canvas 全站前端候选

**负责人：** 钟佳桦。**类型：** Frontend / UI / QA。**分支：** `feature/clinical-canvas-v1`。
**起点：** `2be89143a8abccb3c3896a8f53633e490cf79b28`（远端前端最新HEAD，实际fetch确认）；独立worktree `/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai`，原研究checkout与其他人工作未改。
**阶段提交：** Phase 0–7 完整SHA及每阶段测试/截图见 `docs/frontend/CLINICAL_CANVAS_IMPLEMENTATION_REPORT_V1.md`；阶段7 `a05f8e6abf8fc422ef23ccfe444f9cf330433bf9`。最终提交补录见下一条。
**完成：** Clinical Board 概览、病例表/局部筛选、CT优先Case/Result、统一Shell、真实范围Jobs/System、Login/Preferences/404、明暗和密度tokens。保持API/auth/Viewer/geometry/lockfile不变，来源哈希存证。
**发现与修复：** 创建成功但路由失败可触发重复Case，改为保留acceptedId；密度控件值变化但内容撑高行，改为密度控制cell padding，实测47.14/52/60px。未知状态继承属性用own-property检查。旧浏览器断言改为当前中文标签及可访问ID，不移除几何门断言。
**验证：** 121/121 tests、18spec，独立vue-tsc、/mvp/ build PASS；本机Chrome合成API+实际Cornerstone共26场景PASS、143张最终截图、0page error/0外部请求。6组五标记几何最大0.6121 CSS px；10次尺度切换renderer/cache不增，30秒空闲无持续重绘，离页释放至0；五页两主题对比度抽样PASS。不是完整WCAG认证。
**边界：** 无push/merge/deploy，无Backend/Worker/训练/数据/D10/冻结基线变更。真实账号/Backend/GPU链路未运行，当前GPU状态未知；全局统计/RBAC/遥测缺口输出独立Backend能力请求。建议进入授权部署验收准备，不能直接视为生产/临床可用。
**证据：** `docs/frontend/clinical-canvas-evidence/final/browser-acceptance.json`、tests/typecheck/build日志；`frontend/geometry-qa/clinical-canvas-browser.mjs` 可复跑。

**Clinical Canvas 交付补录：** 最终受测应用提交 `e8eec4241d2a33ff8995461ed2cc920840962b4a`（Phase 8）。其后仅补齐本交付记录、报告和完整变更清单，无应用源码变更；测试/build/浏览器结论绑定该应用提交，最终文档提交编号见负责人交付消息。未推送、合并或部署。


### 2026-10-04｜Clinical Canvas 本地 production preview 与独立集成验收

**执行者：** 本轮Codex；用户授权附件03任务。**分支 / Worktree：** `feature/clinical-canvas-v1`；`/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai`。**开发前HEAD：** `7ada03b76142e6f45fea9c531f634e36a44cebf8`。**源码提交：** `273e76aa3e540cdf14a600452e4980167c158e35`。
**完成：** 现有/mvp/production构建和Vite preview；AcceptedJob路由失败恢复修复；14真实本地、10Mock场景及23本轮截图。真实Gateway/Backend HTTP链路使用新SQLite库、显式测试文件存储；正常浏览器输入验证Session/CSRF、去标识、上传/Cornerstone、Job深链/刷新、跨tab/账户所有权、过期410与实际停Backend后的503。
**发现与原因：** AcceptedJob后删除幂等键会在导航失败重试时重复POST；Chrome失败动态import缓存使普通SPA重试仍失败。保留accepted ID并提供原Job普通恢复链接，生产故障注入确认一次POST。早期harness权限、类型注解、就绪等待、短ID/异步登录/选定图层及请求归属断言错误均修正，失败材料保留于ignored任务目录；最终完整重跑通过。
**验证：** 开始源码121 tests，最终126 tests/18spec及vue-tsc/Vite构建PASS。production六组几何最大0.45566673285130727CSSpx；34静态文件与preview逐字节一致。构建包SHA256 `42321d170b168702fb8edbdd4ca697416749c5418d9b14113bc4660515712727`。最终本地库1CREATED Job、0attempt、0Worker、0Result，两类浏览器0page error/0外部请求。
**限制：** SQLite/TEST_STORAGE非PostgreSQL/MinIO；正向Result是预定义Mock契约夹具，非新推理。无Worker可观测字段；显示未接入。未来operator/search版本仅DRAFT，现有真实版本字段与几何白名单保留。没有Backend/Worker/算法/GT/冻结证据变更、push/merge/deploy。
**交付：** `docs/frontend/CLINICAL_CANVAS_LOCAL_INTEGRATION_REPORT_V1.md`、`CLINICAL_CANVAS_RELEASE_MANIFEST_V1.json`、`clinical-canvas-integration-evidence-v1/`。本轮服务和浏览器已停止。唯一下一步Release只读固定candidate，在真实依赖与GPU条件具备且另获授权后补验。具体状态 `CLINICAL_CANVAS_LOCAL_INTEGRATION_PARTIAL_PASS`。

### 2026-10-07｜公开主线整合候选与隔离回归

**任务类型：** 应用/研究文件整合、Git 治理、QA。**执行者：** 本轮 Codex；用户明确要求执行主线整合与分支整理。
**分支 / Worktree：** `codex/epilocate-main-consolidation`；`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/main-consolidation`。**开发前 HEAD：** `14c114ab26226561615315f7d3d25e42fcec64cc`。
**实际改动：** 从独立 Clinical Canvas `117ce7a61c6bd8ba6893ecb83445d8647c9965a1` 按文件导入，迁移 `8a5928fcdabfb0326e1f76182f6f54f4278eb022` 的会话、超时、任务幂等及焦点行为和 `f548a624588deb922131c0c07b83336e2bc0ff15` 的 Worker 诊断；加入冻结 D10 四个离线工具、Stage 1 合成测试与 `pyarrow` 依赖。没有新增接口版本、数据库迁移或修改冻结实验结果。
**问题与处理：** 既有 5197-5200 端口正被其他演示占用，测试服务增加 `--port-base` 并使用 5297-5300。首次浏览器运行因构建缺少 `/mvp/` 基址使资源 404，按 `VITE_PUBLIC_BASE=/mvp/` 重建后完整重跑通过。导入的历史日志保留原字节及其行尾空格，产品 Vue 文件的空白问题已修复。原 `main` 历史含已公开对象定位文件，当前树已删除；发布审计必须分别报告原有和新增可达对象。
**验证：** 前端 155/155 测试、18 文件，TypeScript 和 Vite `/mvp/` 构建通过；Backend/Gateway 51 项、Worker 协议 28 项、D10 53 项及 25 个子测试、Stage 1 8 项通过。真实本地 HTTPS/Gateway/Backend 使用 SQLite/TEST_STORAGE 通过 14 场景，Mock API 正向 Result 与六组实际 Cornerstone 几何通过 10 场景；两类均零 page error/外部请求。最终真实测试库 1 个 CREATED Job、0 attempt、0 Worker、0 Result。浏览器证据在 ignored `frontend/.local/consolidation-20261007/`。
**公开对象审计：** 候选 `4a6af279fc6fca82f5b447d27cab4e66efd803d9` 的完整可达 closure 有 6 commits、120 trees、809 blobs；新增 710 blobs 仅命中合成 DICOM 与两份无凭证值的示例环境模板。旧公开 `main` 历史仍可达 `MIDRC-RICORD-01.s5cmd` 的 S3 对象定位信息，已在本次 tip 删除但不重写历史。最终文档提交须再扫；私有审计 JSON 留在 `EpiLocate-private/manifests/`。
**剩余：** 最终提交审计、PR、合并、远端/本地主线核验、归档标签与分支逐条去向仍须按实际执行记录收尾。未做服务器部署、GPU 操作、PostgreSQL/MinIO 或真实正向推理验收。见 `docs/consolidation/MAINLINE_INTEGRATION_20261007.md`。


### 2026-10-09｜EPI-NEXT 本机算法与评价开发

**负责人：** 钟佳桦。**执行者：** 本轮 Codex 主控与 DATA-EVAL、ENCODER、LOCALIZATION 子代理。**分支 / Worktree：** `codex/epi-next-integration-20261009`；`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`。**开发前 HEAD：** `169bb42b94365ae0eeccae10e425fa1e167f3ce1`。最终受测源码提交和产物 SHA 在本阶段后续交付补录记录。

新增 `research/next-hospital-20261014/` 隔离模块，包含固定 target margin、HSPI 全 logits 连续 Mask/CPF/PSMI 独立变体、冻结编码器/患者级线性头/CAM/cache、共同支持域评价与 DICOM LPS 几何、研究接口和本地不可覆盖收据。用户明确本轮不启动 GPU；保留原 A/B/C、GT-v1、测试集和应用。未 push/merge/deploy。

实查 split 186=130/28/28，开发 GT 61/811 字节哈希匹配；仅技术 QA、临床未裁定。baseline 原路径失效，经归档索引定位并现场复算 SHA `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`。首次合并后115测试及六步骤单命令均exit0；真实权重+合成图像 E1/E2 25 forward，E1 OK、E2 NO_FEASIBLE_MASK，未调松约束。后续最终合并验收单独补录。

交叉审查修复预测图误标专家GT、无logits失败序列化、重算前对账、坏收据类型和真实输入membership检查。当前本地收据不是远端receiver/GPU队列验收。真实CTFM三例、F0训练、GT-vNext真实overlay、患者定位比较、医院冻结与临床有效性均未完成。详见 `research/next-hospital-20261014/reports/PREFLIGHT.md` 和三线报告。


**EPI-NEXT 最终本机交付补录（2026-10-09）：** 固定受测源码提交 `8aa5138a2b51b292eb5b8762f4d908ceb493d29d`，单命令在 clean source 上运行，137 tests PASS，8步骤exit0。新增实际CT-FM适配器小试：官方权重SHA `b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215`，CPU 32³合成输入→[1,512,2,2,2]；推理0.079812s、整进程峰RSS1285603328bytes，非全病例/非GPU性能。E1/E2真实旧权重合成对照219calls，E2两个尺度CPF可行但PSMI无支持，NO_RELIABLE_RESPONSE且零候选。残余输入F1刷新baseline/粗图，8calls（7extra含2probe）到stage上限PARTIAL_BUDGET。最终receipt SHA `e83ba9e260721bc8246f3f4c183dea60c9169db9733c8860e0318b82495e05a4`。公开原始合成数值及哈希位于 `research/next-hospital-20261014/reports/final/` 和 `DELIVERY_RECEIPT.json`；完整实跑命令保留本地ignored收据。首次下载超时、一次测试断言不匹配记录保留；没有覆盖历史证据。GPU未启动，真实患者/GT-vNext/native overlay/临床效能仍NOT RUN。受测代码之后只补文档和数值证据。


### 2026-10-09｜INTEGRATION 医院版本接口、空间与结果保全

**负责人：** 钟佳桦；首席算法工程师通过总控协调。**执行：** 本会话唯一专项writer；子代理仅只读QA，不修改文件或真实模型。**分支 / Worktree：** `codex/epi-next-integration-20261009`，`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`。**开始 HEAD：** `2ed840ff00fcddf812150637b23f6a5a2af13435`；开始tracked干净，后核对总控在途两个untracked文件并接管，不reset/clean。

**范围：** 接管 `epi_next/volume_io.py`、`tests/test_volume_io.py`；新增hospital_contract/runtime/release，版本接口、LPS八角点/SOP/transform ledger、共享设备租约、调用计数及协作预算、全球intent与不可覆盖收据、版本flag/原handler回退和真实证据准入。建立独立 `hospital-release/20261009-integration-v1/`，含manifest、接口说明、八项验收与流程回退；前端不改。

**审查修正：** 失败/无logits候选拒绝；响应按算法限定有限数值；输入dtype/channel最低字节预算；intent跨设备竞争转BLOCKED；门禁拒绝未注册/未验收版本、不同参数/预算/任务身份、失败备用结果，验证资产SHA与录屏播放审阅收据。实测新接口/生成DICOM35项PASS（本机CPU、现有.venv、pytest -q -p no:cacheprovider），此前29/32项中间测试也为合成。实际HU/非对称斜位/反向normal/重采样与半像素resize验证不扩成真实病例验收。最终完整测试、SHA及命令见补录。

**依赖：** DATA唯一正式发布，proposal批准不等医院allowlist；v2开发交付SHA `42c5e2eb4ebfdb3d1d3c85a9db0095b2c24dca539750468b917ec90bd3337934`、allowlist SHA `3f2c5b5fb2b8b788c5d2f68d9b39554edd079941da58222e9292b62ba6d1ae00`由总控转交。正式空间ledger/真实GT-vNext与接收后的模型handler仍待交付；volume候选schema不能通过另造approval文件直接替代DATA schema。

**限制与状态：** 全局租约只约束采用该API的运行器；deadline为BETWEEN_FORWARDS，不保证硬中断/峰内存。INTEGRATION未启动真实CT模型、MPS或远程任务，未上传数据、推送、部署；未改历史冻结证据或应用协议。实际接入正向运行待上游，真实E2E `BLOCKED_BY_DATA_HANDOFF`，默认医院模型null，最终冻结/临床验证 `NOT RUN`。最终批准由钟佳桦审阅；本地交付包先供总控汇总。


**INTEGRATION 固定源码验收补录（2026-10-09）：** `a2f3cef899ece07b3743d4ae91f6058bd0d8419f` clean source 上全量研究包172 tests PASS（1.74s）；documentation range与diff check、只读算法对照CLI exit0。源码提交之后只补交付manifest/报告/证据和两份工程日志，无算法或应用源码修改。命令、环境、日志、源码及文件SHA在 `hospital-release/20261009-integration-v1/evidence/verification.json` 和 `DELIVERY_RECEIPT.json`。当前交付15个原始代码/文档路径，加后续证据；原应用/冻结路径无diff。真实CT模型运行0、MPS0、remote0，无遗留本会话任务；真实E2E BLOCKED_BY_DATA_HANDOFF，最终冻结与临床验证NOT RUN。未push/merge/deploy，未自行决定默认模型。正式交付由总控汇总并交钟佳桦审阅。


### 2026-10-09｜增量：DATA v3 固定三切片真实预处理

**专项与授权：** 总控转交既有3train/715SOP本地研发许可及v3 SHA；INTEGRATION唯一prepared-input writer，不建allowlist/GT，不训练、不替其他线执行定位。**开始HEAD：** `9c1dff3f47f890240c76f70364879b5961c3907c`。

新增 `epi_next/first_real_preparation.py`，消费DATA v3 native HU/ordered SOP/affine/inverse与总控每例floor((N-1)/2)锁；严格绑定原CT SHA/Study/Series/SOP，调用已冻结 `src/preprocessing.py`，不复制/修改原算法。HU窗-600/1500，224双线性antialias，无crop/pad，RGB+ImageNet normalization。调用LOCALIZATION `8ac99308a123bee468374fff68df4c4f1ec08414` Prepared2DInput.validate，不独立实现定位。支持域明确完整原模型FOV，padding未知不推成lungmask或无padding。以实际源DICOM头独立检验model→native→LPS及逆映射，原HU与DATA数组逐值、完整tensor与旧流程严格相等。

4项新增合成测试PASS；源码固定之后才执行三真实切片准备并补录实际收据。首次接收检查发现DATA manifest的HU路径相对manifest、v3入口为绝对路径；按原发布基址解析比较，无修改DATA资产。真实定位/模型forward不在本准备器中。准备成功后立即发布 `.local/phase2/first-real-e1e2/prepared_delivery.json` 供总控转交，三例数据接收收据不是新批准文件；模型2D映射阶段不再笼统记DATA_HANDOFF阻断。医院展示与最终默认模型仍未批准，临床验证NOT RUN。


**DATA v3/三切片实际交付补录：** 固定源码 `a13bbcc90140d4d8d2ba308b54fd6ad76a400f09` clean source，真实三切片111/121/123均preparation TECHNICAL_PASS；prepared_delivery SHA `b85eaf6c78d1547e2aa4b93458734f533d34be5de1ed056fd152c30b92ebaa99`，data_v3_receive_receipt SHA `22c792e26a3fce9da7ff90a27e9052d00f15a52800404268fcb89c4c08875815`，preprocessing spec SHA `0a283e01a3f4a5116abd6ea1bfa9f7640df6dea4d04d4dac573c54d93390fdfb`。18产物SHA复核PASS；原HU/旧完整tensor严格一致，真实DICOM独立world公式maxerr5.684341886080802e-14mm、逆链maxerr2.842170943040401e-14model voxel。两例padding tag存在但旧流程不mask，一例UNKNOWN；工程支持域不是肺mask。

数据/标签/GT仍由DATA唯一发布，未新造allowlist/授权收据。原生manifest含GT元数据，未打开GT mask资产或按其改选。三例native handoff已就绪，不再笼统报告DATA_HANDOFF阻断；Prepared输入READY_FOR_LOCALIZATION_CPU，准备器模型forward0，无训练/MPS/远程。私有实际命令与完整资产引用留 `.local/phase2/first-real-e1e2/`；无患者ID的增量摘要在 `hospital-release/20261009-prepared-v2/`，旧v1包不覆盖。模型结果/浏览器叠加/医院端到端与最终审批仍未完成。医院侧车阻断原因改为具体HOSPITAL_RUNTIME_HANDOFF并保留新旧算法门禁。


### 2026-10-09｜增量：已有真实 E1/E2 本地对照绑定

开始 HEAD `cb87b3699fe744d203f107cbb60d783721cc5c24`。消费总控固定的 LOCALIZATION run-2 SHA `aadd59ca4b9439387f4f439c5140720b6d2142affe77454e4888ce2b26055130` 和 DATA 独立 evaluation SHA `55dbe1c71dbb3836f28ae3a4352f2a9c0d257b403b97e6ac4a7f65929856b477`（candidate inverse mapping PASS）。新增隔离本地 HTML/PNG 资产绑定器，读取发布的 native NPZ 与全部官方部分参考 union，校验 SOP/切片/manifest/数组 SHA；不重算算法、GT或统计，不新增应用页面。E1三个margin响应尺度分别显示，E2零候选保留 NO_FEASIBLE_MASK。部分参考未标注区 UNKNOWN，非完整/共识GT。

医疗派生产物限 ignored .local，不可覆盖收据及重复读取校验；源码固定后执行一次绑定，三次读取不等三次模型或医院端到端演示。独立DATA映射PASS不自动冻结模型；医院默认null、医院展示未批准、临床验证及最终冻结NOT RUN。只读审计本树（含ignored Python）无总控状态路径/state_path引用，未定位状态回退源；未写总控state。测试与实际产物SHA在后续固定源码补录。


**真实本地对照实跑补录：** clean源码 `2701e69c8b891ea7c761f12ec14f5c28a51909a1`，构建exit0，新增forward0，三张2100×1400 PNG与HTML仅保留获准ignored目录。binding manifest SHA `24048a6a94c13ae5bbd6d60fcaadcb4154e0725b259cb239d7f384c173c0c8c9`，receipt SHA `ed04dc8186075d382a99eb2a10d703e487a4043fbc2c5a780c76c4f0e1c8517d`。180 tests PASS（1.65s），三次readback exit0、产物及上游结果/NPZ/官方mask哈希一致。源码之后仅追加 `hospital-release/20261009-real-comparison-v3/` 元数据摘要和工程日志，无医疗像素进入Git。E1三例OK（194/195/157），E2三例NO_FEASIBLE_MASK零候选；DATA独立候选映射PASS按固定evaluation引用，非临床有效性。未执行浏览器视觉审阅；重复读取不等三次医院模型流程。医院默认null、最终冻结及临床验证NOT RUN，F0/F1真实对照NOT RUN。


### 2026-10-09｜S0 增量：受控状态writer、依赖与设备slot

开始HEAD `8baec8b9260586bd6412a0656b559cbcea182a50`，沿用INTEGRATION工作树。按负责人v2.0包只交总控调用工具：同flock内CAS/递增/fsync/replace，append-only hash-chain事件、不可覆盖旧/新snapshot及未知事务门禁；权限pointer白名单、保留授权字段和唯一task_key。隔离fixture并发仅一次提交，四阶段真实子进程退出模拟中断，旧快照/权限/重复及坏快照拒绝。最小依赖源码/包版本锁和同共享device flock的PID/start/job/资源slot；registered子进程未完成不接收终态，无终态slot不自动重跑。新工具未迁移既有运行器，不声称同UID防篡改或跨会话认证。

只读生产state观察rev11 SHA `7295b62901a54ae6094263e619aad9b265a80110c43f9583f4e0e015ef26ffaf`；本树/主项目相关代码和进程未定位rev4回退根因，UNKNOWN。总控已结束update_state_v9存在锁外比较/replace但不能归因；三个私有脚本未执行。无生产policy/state写入，无新增真实forward/backward/MPS/远程。9项新增隔离测试PASS；包含既有医院/资产接缝的定向65 tests PASS（1.02s），纯fixture/合成。一次错误cwd导致0tests/exit4，随后纠正到指定工作树通过，未污染主项目。CLI/权限/恢复边界与MVP真实接入缺口见 `hospital-release/20261009-state-tools-v4/README.md`。固定源码后补证据/文件SHA，医院最终审批及真实三次流程NOT RUN。


**S0 clean源码补录：** `a0a5fdfc399454bd3dc5c7f69d49888ad031eed2` 上65定向fixture/合成测试PASS（1.03s），隔离CLI update及reconcile exit0，fixture 11→12 COMMITTED/CONSISTENT。writer文件SHA `b87111c88b5f14744c9570fb46b9f4f386e56a48e0957755e5a98c45e1fcd496`。具体模块依赖SHA、实际命令/退出码/时间见 `hospital-release/20261009-state-tools-v4/verification.json`，stdout留本树ignored `state-tools-v4`。生产policy创建0、生产state写0、真实forward/backward/MPS/remote均0。提交后只补此受测证据及日志，根因UNKNOWN，同UID绕过可能、旧运行器未迁移和MVP真实链路接续缺口保持。


### 2026-10-09｜Wave1独立共享监督器增量

开始HEAD `dc8dae673d3d8b8c8ed10ded0064a83b36a3c083`。资源修订SHA `1011506834d7e5c54c60ef7d67f89900fa9259669d6bde2fb6141c197c6481de` 已由负责人授权；本线只交共享工具，不启动真实。新模块wave1_supervisor及child guard复用execution_lock：全Wave1 serial flock、跨设备UNKNOWN及重复task预算闸门；加载计入deadline，20ms目标子进程心跳、50ms目标RSS/系统采样，5GiB预停/6GiB目标，macOS memory_pressure -Q原口径free20%、swap增1GiB；实际PID-group归属复查、stop信号/文件、有限TERM/KILL、退出与恢复未知不完成slot，保全部分资产。零forward/backward DATA可用；预留attempt与runner actual分开。MPS恢复需实际child driver/tensor及明确收尾，非父进程假0。

隔离bundle八运行模块SHA/Python/numpy锁，父子实际__file__核验，DATA无__init__loader兼容；其旧fixture仅geometry依赖锁不足，需八模块闭包接续。本轮测试含小型合成/故障注入，无内存压力实验、真实模型调用、科学参数变更、生产state写入。首次回归发现安全文件名禁止__init__，改用八运行模块闭包；早期进程退出采样race及系统free口径问题已修正，旧失败证据不覆盖。定向40项接缝测试通过，clean源码后生成固定bundle与实跑日志。医院MVP在线接缝/三次真实E2E尚NOT RUN；接口契约见reports/WAVE1_SUPERVISOR_CONTRACT_V1.md。


**Wave1固定bundle补录：** clean源码 `aca34f99ce3e642331bf82e71e6fd625f6e02409`，监督器文件SHA `5d960171e1477266e1418ef045d252c42908e000904384d363d09241c4ddff86`，bundle receipt SHA `62d7d2a87d4e8653c8fd0368cca49ee648fe22a4c9436c28e604c4aed4589ac8`。独立包名实际八模块导入路径/字节核验exit0。clean定向回归39PASS/1FAIL：系统ps超时触发fail-closed而非压力注入预期原因，保留失败日志；受影响项定向复核PASS。已有提交前40PASS不改写；新增实证见hospital-release/20261009-wave1-supervisor-v5/manifest.json。DATA八模块loader兼容，geometry-only执行依赖锁必须补齐，最终DATA入口握手由DATA负责，本线未扩读/运行真实。固定package与依赖只读字节/目录，所有真实forward/backward/MPS/production state写入0。


### 2026-10-09｜Wave1调用文档更正

开始HEAD `e146a83c129d26695ac55ea7aa7f2a0161579cb2`。总控/ENCODER接缝反馈固定版verify_loaded_bundle按完整模块名查sys.modules，直接-m入口为__main__可能KeyError。仅更正调用契约和准备文档为显式import wave1_supervisor.main()后SystemExit，固定运行源码/bundle/收据及旧日志不改、不重跑模型或fixture。总控报告DATA真实标签任务SUCCESS、槽恢复、模型calls0；不扩成本线独立验收。文档检查与diff check通过。


### 2026-10-09｜Wave1完成后心跳误判最小修复

开始HEAD `412fc560f2384c0dafd0a72d736ff99c09736f9c`。只读E1实际收据：child SUCCESS792前向，complete时间266848.783347、末心跳266848.78299175，supervisor stale触发266849.106835041、退出266849.12291325，末采样已无group活成员；固定FAILED收据SHA `f7b675db91ba1d0016b7296fc5ec66d90a1bc3ccdf4823f80d665585e8b6c757`不改。确认完成关闭heartbeat后Python teardown超过250ms，旧顺序先stale再退出导致误判。

仅对合法同job/原child完成标记停止stale检查并进入退出等待；未完成/伪标记继续保护，deadline、归属、压力和恢复持续。20项监督器fixture PASS（7.47s）；新增正常complete慢退出/真失效/其他job标记/deadline四项，无真实calls、科学参数变更或权威state写入。旧bundle保留，新固定bundle另版；clean源码后补导入/日志SHA。


**完成闭环追加：** child完成标记后check/新forward/backward均拒绝；父在合法complete后持续核对预留counts/sequence，任何变化FAIL。补完成后禁止新工作和父检测计数变更fixture；旧错误job fixture因child新保护立即退出，调整为非合作活进程以验证父stale仍有效。最终22监督fixture PASS（8.01s），无真实调用。新版固定源码以本次追加提交为准，初步0b252e8不作为最终bundle。


**v2固定bundle补录：** clean源码 `2ba7068662efc6004797ccc76144e0faa0229c22`，22监督fixture再次PASS、固定八模块实际导入exit0；bundle receipt SHA `01d659d17a116fd2e913bd853d3bf2f1f33a122aeee837f1438d542cf90c9888`，wave1_supervisor SHA `a0a6f3f17f39ed013bfa343900d3cc05be0ce9f1ed626ff7756a9c5a38c1bcf4`。本地新包wave1-supervisor-2ba7068-v2只读保全，公开无患者像素摘要hospital-release/20261009-wave1-supervisor-v6。原E1 FAILED收据保留无重分类/无真实重跑，新真实calls/state写0。


### 2026-10-10｜HSPI v3最小结果接缝与UNKNOWN恢复提案

开始HEAD `986485a517e81033dd9af36538091d8ffb0247e2`、原INTEGRATION工作树干净。读取总控v3包00/01/02/04，保持源码/已保存结果及生成fixture许可，新增e2_result_handoff独立sidecar：E2-W1/REF/CT mode、profile、全计划scale/stage、selected_iteration、partial/unrun/no-feasible、trace SHA与分别验收轴。复用persist_run不可覆盖；无LOC算法/GT重写，无新handler/UI/监督v2改动。契约文件交总控转LOC，不宣称peer已收到。38定向生成/资产测试PASS（0.08s），其中4新增验证mode、partial/unrun与trace/选择身份及不可覆盖保存。

只读原CTFM self-task身份/收据/槽、state19；槽无finished/完成标记，父66331/子66338当前ps exit1无记录，已记录旧组退出但无设备恢复。未在有界后续恢复入口发现合法恢复证据，仍UNKNOWN；不能把旧driver458752/tensor0且recovered=false补成恢复。外部恢复审查支持证据/独立批准项见hospital-release/20261010-hspi-result-v7/CTFM_EXTERNAL_RECOVERY_REVIEW.md。无解锁、伪旧child标记、GPU probe、科学参数/配额改写、真实forward/backward/训练/production state写入。MVP无需E2阳性，新增真实E2E NOT RUN。


**HSPI sidecar固定源码补录：** `265dce5923da972b5a27a08b458c034510a49a8c` clean源上38生成/资产定向测试PASS，exit0；命令/耗时/模块字节SHA见hospital-release/20261010-hspi-result-v7/verification.json。e2_result_handoff SHA `edf47a12660f3c00c27126d53bb98289b835879d05ea0079905a8c91dfdbf363`。没有真实模型、反向或checkpoint加载，旧监督v2无diff，UNKNOWN槽写0。只补交付元数据/工程日志，映射/数学/临床评价非本sidecar验收范围。


**LOC trace同步补录（文档）：** 收到LOCALIZATION消息后只读契约HSPI_TRACE_CONTRACT_V3 SHA `67feb9d41bd7ef4cb1b215a9c698b273475d7f987af93434d0f199cf102143df`，确认mode/计划分母/partial/trace身份可对应；补原索引显式转换、PARTIAL_BUDGET→OPTIMIZATION_PARTIAL及NO_MULTISCALE_SUPPORT保持原status说明。不改算法/sidecar代码、不重跑测试、不写其他树或发送未获授权消息。对方代码实现/消费本sidecar仍不冒称完成。


### 2026-10-10｜LOC实际sidecar零调用消费与恢复审阅配置

开始HEAD `d6828b80d3acbbc905c5772e6294522207181a66`。仅核验总控固定generated-run2 delivery SHA `7f491e2ba0471eab4e766f798853f7a7152ccb5fa8fd1c4703a5da529755805a`，原source_result/trace同字节SHA `1f31ee20207ab2c0a9d76044b356cda6dbd13d450538a9a71b08c9753d7055ba`；sidecar immutable receipt COMMITTED、六分支各180一基observation，selected57/51/56/53/61/56对应原history，optimizer_updates单列各180。消费收据SHA `bc5ff68fce1b33033141d2c073a8c770ddef63f52118a62a5c7531e617242cc7`，耗时0.0365s；PASS仅字节/分支身份，不重算CPF/GT、不重跑优化/测试/模型。

补CTFM独立待批准外部审阅配置：60秒目标1秒含端点61样本，memory_pressure free>=20%、sysctl swap相对新t0增长<1GiB、无缺测及原自有身份无活成员核对；允许采样偏差需另锁，即使通过也仅必要非充分。未执行采样、解锁或行政写入，无新GPU probe/reboot。38项既有fixture证据复用；没有新代码。


### 2026-10-10｜R0证据消费与独立行政恢复门禁

开始HEAD `084f8abc3a95de2e7f2d7de9b6304bff0f2a458a`，原集成树干净。总控完成唯一R0采样，本线仅核验result SHA `8e238721357f0c36f0d1922626c8a0cf8c19c5254d76d13886204636d1bd99d9`及7份raw文件，未重采。R0条件满足不构成恢复证明，行政决议仍WAIT_OWNER_EXPLICIT_DECISION，旧UNKNOWN/旧收据/finished缺失保留。

新增execution_lock只读决议消费，绑定独立钟佳桦批准、scope SHA、原started/监督receipt/R0原始SHA；在既有监督serial锁和device lease内复验，允许仅一个绑定旧槽为新批准task让行，重复task及其他UNKNOWN阻断。新started保存decision SHA；不写旧槽、不增加调度器、不改旧只读bundle。8模块新源码必须整体锁定给LOC/C1，实际dispatch仍总控所有；直接tracked_device_slot不代替run_supervised的全局串行锁。33项生成门禁/执行锁/监督回归PASS（8.55s）；初次fixture因MPS owner及旧fixture复用task_key失败后修正测试，保留一次性任务限制。新真实模型calls、采样、生产队列写入、生产解除均0。交付hospital-release/20261010-recovery-gate-v8，医院真实E2E BLOCKED_BY_DATA_HANDOFF、final freeze/clinical NOT RUN。


**恢复门禁固定包补录：** clean源码 `c9f5369b7384f4e132365616f8b6f64b624dbea2`，八模块依赖锁SHA `69bf2a28956b688a81d23f1bcfd4f6378edd50dcf5b2843d66a1ff480dfed871`、bundle receipt SHA `aba7f4444dcbd32121dab291289d0069e86e7f4d979451b4fafb92d7d89a9446`。独立命名包epinext_wave1_supervisor_recovery_v3导入及verify_loaded_bundle PASS，文件只读，本机忽略目录wave1-supervisor-c9f5369-recovery-v3。生成测试33 PASS复用，无追加模型调用/真实解除；BUNDLE_RECEIPT.json记录完整模块SHA与本地位置，旧v1/v2包不变。


### 2026-10-10｜集成交付阻塞状态更正与P1/C1消费索引（文档）

开始HEAD `65640819bda7f3b8aef1bf0ff101d1a87e1e1ad4`，干净工作树。总控指出旧BLOCKED_BY_DATA_HANDOFF过时；只读revision24 SHA `deaf3718effe5993ed4a3e9b9b143f904afc14b55c701ae2719d5931c374d392`，核验DATA v3验收收据SHA `760e71b338178e3767aa9ca99c8042c846d1d129d7d8c47c6465eef2c4995522`与首轮报告SHA `abeae3e45140052dea69456c555830616217b3a7a27c6f5a5a8fec45c11fb33b`。数据及首轮真实结果已验收，当前新真实运行等待负责人R0独立行政恢复确认及新依赖绑定；医院冻结/临床验证仍NOT RUN。新增hospital-release/20261010-recovery-readiness-v9更正/消费索引，保留旧v8原字节及历史。八模块固定包、契约、依赖锁和33测试原日志SHA复核PASS，无重采/重测/模型/生产槽写。P1工程HEAD5087c6f9由总控交付消息提供，10生成测试结论引用总控；本线不重验peer测试。P1/C1需新增readiness及完整runner依赖锁，不静默改旧记录。无代码修改。


### 2026-10-10｜负责人独立行政恢复批准只读消费（文档）

开始HEAD `e7ffcdf2c3a0b7489bc5e83c01fc5903a5f221ca`。总控发布OWNER批准SHA `867efcb499ac2d80bc467bb590ebcecee2bca6ed8187a890b3fd03ae8119ab59`及决议SHA `e58097389d1a2345e22e15c27b182dda9ca4f61876b8c39b12f6c0fdad0d7009`，核验revision25 SHA `1c58c8764d504da06735b2dc13cbd376573dde235f4875a0b989ecf5b1015967`。导入既有c9f5369固定包并核验八模块锁，只读validator对决议列明P1/C1两个任务键PASS；旧槽文件/目录成员前后不变，finished仍缺失，历史UNKNOWN保留。追加hospital-release/20261010-recovery-readiness-v9的新OWNER消费/状态更正文件，原v8/v9所有既有文件及WAIT_OWNER索引快照原字节保留。当前阻塞更正为WAIT_FINAL_READINESS_AND_SERIAL_DISPATCH，非等待负责人回复/非等待数据；行政决议不扩展科学权限或P2/P3/医院显示范围。采样、模型、dispatch、槽写均0，无代码修改/无测试重跑。


### 2026-10-10｜LOCALIZATION P1恢复v5交付只读消费（文档）

开始HEAD `697a544287388bd29b6c4bc47ecdcf900dc23d08`。LOC发布source `d678a2546830292b81bab08d22ad6549d25940d3`，核验readiness-v5 SHA `427aae7ade672943ef62a24548dde880c660f33382c44bedc2f813abe407e728`与final-delivery-v5 SHA `8ead897461ef1845cd2ac708f14d1902649cea59564d6290697cc9c141ac67e0`、8交付产物、owner/decision/R0/旧收据/原槽/八模块/dependency绑定SHA，commit存在。原test log记录14生成PASS/2.55s，本线不重跑；LOC声称隔离scalar1F/1B、生产交易0/新医学调用0，未推为真实科学验收。新增v9/LOC_P1_V5_CONSUMPTION_RECEIPT.json，旧交付不改。P1 readiness PREPARED_NOT_DISPATCH，等待总控精确dispatch/唯一准入；真实P1 NOT RUN，医院冻结与临床验证NOT RUN。本线模型、R0采样、生产队列写0；无代码改动。


### 2026-10-10｜P1监督FAILED的IO竞态复现与v4修复候选

开始HEAD `5139f12bebeba4516bd44a38fae9132a0ba1cff3`。核验P1旧job监督收据SHA `c842a949006db7eb020691030ad98b8eb0e8eb3ca6fdf20970f65de9baff8f64`：FAILED/return2/实际与预留F/B0，父确认恢复及finished；禁止重跑。原v3 atomic_json:47-50临时文件rename与LOC BoundedStore.size:19-26未同步os.walk/stat可确定性复现ENOENT；LOC runner:266将监督目录纳入输出预算。空run-1目录支持构造ensure失败，但原无traceback，实际调用栈只作推断；5/8启动期遥测缺测非父触发原因。

新IO_CONTRACT_VERSION=EPI-NEXT-SUPERVISOR-IO-LOCK-4，共用有界flock覆盖writer临时文件生命周期及supervisor_output_size快照，保留临时残留计费/软链错误/IO错误失败关闭；不放宽预算/遥测/deadline，不新增调度器。LOC必须独立接入shared size callback并锁新完整依赖，仅writer改动不能修复旧reader。43项隔离生成竞态/监督/队列回归PASS（9.74s），原writer fixture函数体经AST提取原固定包逐字核验；旧v3八模块字节不变。候选hospital-release/20261010-supervisor-io-race-v10，待LOC接入/总控审阅，不代表重试授权。真实模型、C1、P1重试、R0采样、生产槽写均0；医院冻结/临床验证NOT RUN。


**IO v4候选固定包补录：** clean源码 `11c2c6c706cf0c2e0b8d07e45217f912ce00effe`，八模块命名包epinext_wave1_supervisor_io_v4实际import/verify_loaded_bundle PASS，dependency SHA `f4fa697c31af62a93f0f28a97938e51251cd4f2c34c56b1a76076a085d7a10ab`、原bundle receipt SHA `2d0a6ceccd6bc4e0e1897c107bf14e07134af202b9f976dde7e18cbc742c0386`。本地只读新包wave1-supervisor-11c2c6c-io-v4-candidate，旧v3未覆盖；完整路径/模块SHA见v10/BUNDLE_RECEIPT.json。43生成测试证据复用；LOC reader adoption待完成，P1无重试、C1未运行。


**总控最新方向及复现栈补录：** 新REPRODUCTION_TRACE.json保存隔离原v3 writer与旧size语义的os.walk→rename→stat事件和生成FileNotFound栈；不伪称原P1 traceback。总控优先LOC-only size有界完整重扫：仅识别监督tmp ENOENT时从零重扫，次数/时间内未完成即安全停止，不跳过tmp或返回部分总量、不放宽cap/reserve；本线未实施LOC-only修复。已保存v4共同锁仅备选，不强制升级、未部署；P1/C1均未运行。

### 2026-10-11｜医院MVP生成应用闭环与真实流程最小提案

INTEGRATION，原指定工作树epi-next-integration、分支codex/epi-next-integration-20261009，开始HEAD `0e13a1f9167be9d6f2bf815b49cf3ff9e16650b1`。按总控10/11增量指令，新增qa/hospital_mvp_generated.py，以现有生产前端构建、真实loopback Gateway/Backend/WorkerAgent、SQLite/TestStore和精确生成DICOM完成三次上传→分类/遮挡→保存→原生叠加/16/32/64→刷新。FakeRunner与显式Torch/inference doubles无权重加载；wire LIVE_CASE/frozen SHA仅fixture兼容值，固定非医学banner。attempt6 exit0、总50.272s，7jobs/6completed/1failed/6results/27assets；FAILED刷新无完成链接，最大单切片overlay误差0.39894CSSpx，四个自有服务退出。此前依赖/去标识/路径属性遮蔽/模块注册顺序失败分别保留；attempt4发现静态Torch导入后核对本线身份终止，未执行医学模型。没有杀未知进程、患者资产读取或部署。只读复用前端依赖，测试依赖放本线ignored目录，不改正式Torch环境。

只读消费LOC新v7 manifest SHA `ec18420e2a1196c51964ff59c88c559f59bb28896bfdee4edff935727a1f8831`、生成同入口acceptance SHA `ea40b9e902872159771e9012e56c5d2301d81f21d447852014e1cafa384174fc`；源码/CT bridge/v3八模块绑定PASS、不重跑peer测试。P1真实重试仍NOT RUN/无3540秒批准。消费ENC新C1 binding `604b5d…`与实际result SHA `7a2f1149a0d82fbed3c23f5e15b9b91c772f3ab3c0435df287cb7be00300644b`，源执行提交 `b37f85e86dddfe08065fef54a99aba09e6a6b6ed`；真实CPU1/MPS1数值PASS但cleanupFAIL，监督BLOCKED/slot_completed=false；本线无重跑/采样/probe/解除。权威revision36只读快照，不写状态；R1集中归总控。v4共同IO锁未接入，继续LOC-only修复+固定v3。

交付hospital-release/20261011-mvp-v11一份manifest及增量报告、生成截图/日志/哈希。复用旧接口/空间/选择门禁和验证收据；产品E1/E2/F0/F1尚未注册，不冒称真实应用接入。医院真实E2E/预计算/录屏/冻结/临床NOT RUN；开发DATA已交付，不能再以旧BLOCKED_BY_DATA_HANDOFF概括当前阻塞。最小真实MVP申请3固定SOP、历史FrozenBaseline Occlusion3jobs、96模型batch前向（含3基准，2802扰动/总2805图像评估）、B0/update0、无预热/重试；数据和计算独立待批，展示精确资产/受众待锁定故NOT_REQUESTED。旧模型/协议/历史资产/前端源码无改动。实际源码提交与最终文档检查在本条后补录。


**生成MVP固定源码补录：** 源码提交 `65651041800f05d464df3d0fa589f9c5b09e820a`，qa入口字节与attempt6受测源码一致；无追加浏览器/模型/peer测试。生产构建、三次生成闭环及失败持久化证据保存在v11；显式base文档检查/暂存diff检查PASS，只读算法对照拒绝未验收新算法。元数据将source_git_sha锁此提交，医院冻结/真实E2E仍NOT RUN、展示NOT_REQUESTED；真实共享计算暂停，R1归总控。


### 2026-10-11｜固定v3恢复链与R1最小消费适配

开始HEAD `fe36b2076edfb9b8a1ff351ea72850a93f31f2b5`，原INTEGRATION树。总控唯一委托恢复消费适配，保留c9f5369固定v3及v4 IO候选不动；runtime/recovery_chain_v1只从原v3派生execution_lock和wave1_supervisor两文件，逐一绑定旧CTFM128/R0及新C1/R1的start/receipt/review/raw/owner。前序决议按其当时允许的已消费C1键验证，并核对新槽started.administrative_recovery四个原字段；节点上限2、循环/过深/漂移/缺证据拒绝。两个既有串行/设备门禁仅对完整old_job_ids集合让行；旧单槽字段保持兼容，已消费任务/第三未知槽继续阻断。无新IO锁/调度器/finished伪造。20生成隔离fixtures PASS0.33s；只读实际新决议SHA `ceb164cbca27c0e547da8c09b65fc8c10d78f0544e62bf4b9ead0920ab4eece4` 对P1重试/MVP两键PASS。实际queue写/GPUprobe/观察/医学F/B/update0。源/差分/收据在hospital-release/20261011-recovery-chain-v12，固定bundle待提交后补录；MVP接入紧随，真实dispatch仍总控。


**恢复链唯一固定bundle补录：** 两变化源码提交 `14bf16ebe05f4652204148a0faf0fc455cfb8667`；八模块命名包epinext_wave1_recovery_chain_v1导入/verify_loaded_bundle PASS，dependency SHA `093e0a7fd137ae9772dd30595fe39de845a7babe9de1617d633782a02707a192`，bundle receipt SHA `9ad2257237f859adad2267d33353cf87df6433270923ec2975385d617fe9ce48`。六模块逐字保持原v3，只有两门禁/恢复validator变化；没有共同IO锁v4。bundle/索引完整绝对路径见v12/manifest.json；20测试复用不重跑。本补录仅版本元数据，原始diff上下文空格导致diff-check失败，现改为零上下文diff，源码不变。医学F/B/update、真实队列写0。

### 2026-10-11｜受保护MVP执行入口与真实上传阻断

负责人INTEGRATION；原工作树epi-next-integration/分支codex/epi-next-integration-20261009，开始HEAD `05a4279177e5d09b80ce3c634fae65c714abca89`。qa/hospital_mvp_protected.py接现有FrozenRunner/WorkerAgent、三个自有loopback服务与原生产前端dist；fake helper和metadata binding独立，未修改前端/Backend/Gateway/Worker/FrozenBaseline核心源码。owner申请SHA `2dcc61df10fb2be0964dc4e0e0797e8f2d2c874367026b9a909e66fdc4f35e12`、批准SHA `4a4e9cb141a689533498acdb1d2c77b83222a9a1bad15f9c210b15c7698af9a3`、新C1决议SHA `ceb164cbca27c0e547da8c09b65fc8c10d78f0544e62bf4b9ead0920ab4eece4`与v12固定index绑定；scope仍只原3 SOP/96旧Occlusion批，不是医院展示许可。

模型pre-hook先持久预约，post-hook保存全部原logits；935评估/32批每例、96批总量，无额外分类/预热/重算。case预算包括哈希/应用启动/模型加载，global540秒、输出256MiB。原生partial目录与资产独立保存；一次submit丢失响应核对本地Job/Attempt/Result/完整digest及对象字节，不盲目重发。非daemon Worker及心跳存活时complete不得标恢复。dispatch精确绑定源/包/运行命令/路径，外部发布SHA避免自引用循环。29项轻量fixtures PASS0.03s，命令及范围见v13/tests.log；覆预算、未完成前向、事务漂移、partial、隔离、dispatch和BurnedIn UNKNOWN门。

按总控当前通知P1正占唯一模型槽，本轮无Torch/患者像素/权重/医学调用/真实队列读写/GPU probe/浏览器/重型构建。v11旧生成闭环及v12恢复20测试复用，不归为新入口浏览器PASS。DATA原3 SOP缺BurnedInAnnotation，真实上传BLOCKED，需负责人逐图本机复核证据经DATA/总控交接；不静默填NO、不代签。metadata工具只生成NOT READY源/包fragment，不碰队列或建立第二allowlist。新版生成浏览器、真实MVP、医院八项验收、预计算/录屏/冻结/临床均NOT RUN；新算法医院注册未完成，默认医院模型null。v13报告/回退/manifest本地交总控汇总，未自动消息/上传/push/部署。源提交和metadata收据提交后补录。

**固定源码及metadata补录：** 源码提交 baedeb240d2df51b75be0c8d41bd09a98d3fd6c8；metadata fragment SHA 4cfa24cec74596cfd2a055e6d77c60e7693f35a25d8b8842d932c236b4151e2a，绝对路径见manifest.metadata_fragment。metadata receipt记录98个源码/构建文件、Torch未导入、像素/权重/队列读取0，status固定NOT READY；包版本仅metadata查询，无模型执行。本轮原前端/Backend/Gateway/Worker/algorithm/src/occlusion_runner差分为空。显式base文档及staged diff检查PASS；不追加旧测试、浏览器或模型运行。

**P1退出后生成差分补录：** 总控通知唯一P1实际退出/队列恢复后，INTEGRATION运行受保护入口生成浏览器闭环。attempt6 exit0：3旧Occlusion jobs/3 Result/27资产，96假模型边界回调/2805生成评估、医学F/B/update0；Job/Result身份与SQLite逐项MATCH，截图包含非医学banner、原生CT与叠加及刷新64选项，实际Torch未导入。29轻量fixtures仍PASS0.03s。attempt1–4的Backend启动/登录/图层异步等待竞态修正；attempt5发现URL提前记录Case，修正后仅attempt6作为验收，所有六次自有线程/服务退出收据保全。该补录替代上文新入口浏览器NOT RUN；真实MVP仍需原3 SOP人工像素复核、DATA正式字段映射和总控单次dispatch，医院/临床/冻结仍NOT RUN。最终受测源和新metadata绑定提交后补录，旧baedeb2 fragment保持历史NOT READY不覆盖。

**最终受测源码固定：** source Git SHA `9dad72a5ad3e5931340dc91444072c57d5f74d2c`；原3流程生成验收及29项fixtures均对应当前代码字节。98源码/构建绑定与生成receipt逐项一致，最终engineering-readiness fragment SHA `3b4bb987df4f66b707a73f0ad298de6d05d6ee9eb09abd4b99a022c4af71dde2`，绝对路径见manifest。其status仍NOT READY、data_delivery=null；仅附生成工程证据，剩余人工像素复核/DATA映射/总控MVP dispatch。原baedeb2 fragment不覆盖；v12唯一index SHA保持12e808bcf23f80571886fa0e8c68efa88a11fb833a51db002ab1820d20fc1a6d。未追加模型、GPU、队列观察或构建；医院最终冻结与临床NOT RUN。

### 2026-10-11｜三图人工确认收据只读消费

负责人INTEGRATION，原工作树/分支，开始HEAD `2ee9ab18c950d2d5c5a12dbccb777f9455205d2e`。中央OWNER_DECISION_V1 SHA `437158c573e126152f134eaf61789f010b6629cd27e47212808861fe0988e133`、OWNER_PIXEL_VISUAL_REVIEW_V1 SHA `6f97bb99f983869f214709b2cd98a0d62b16360fc6b57a0ffe8f283072c57a19`均MATCH；三case_index/原CT SHA与prepared b85eaf6一致，三条NO、完整预览与边缘检查及钟佳桦确认字段符合总控交接。未读取受保护PNG/像素；只核对记录，不声称本线重新人工复核。旧记录OWNER_RECORD_PENDING_DATA_AUDIT保持，等DATA正式v2新派生ledger；没有改BIA、GT、allowlist或执行六成员meta probe。v14 manifest/README更新当前缺口，v13及原98源码/构建、29测试/三次生成流程保留并复用，无新测试/模型/队列读写/图形构建。scope批准不变，实际医学F/B/update0；最终READY和实际argv须正式DATA交接后由集成出包、总控单槽调度，展示和医院/临床冻结NOT RUN。

### 2026-10-11｜DATA v2只读消费与final readiness工具

INTEGRATION在原工作树/分支，开发接续v14提交。正式v2 SHA `bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1`metadata gate PASS：DATA审计、三例source/UID/原native索引、原/派生解码像素SHA、header/encoded/geometry/window保全及LOCAL_MVP范围，与中央decision/review/旧ledger/原派生/预览hash链精确一致。没有读取CT/PNG/GT/权重，或修改DATA头/批准记录。qa/hospital_mvp_protected.py只接受实际v2，保留owner_PENDING记录而要求DATA审计PASS；绑定已有pylibjpeg2.1.0/libjpeg2.4.0，未安装组件。qa/hospital_mvp_finalize.py metadata-only组装READY和chief command SPEC，只读receipt并临时检查既有serial/cpu锁，未建新锁/队列记录/槽或调度器，不查杀进程；实际采样将在固定source后执行并补录。48轻量生成/隔离锁测试PASS0.06s，新生成浏览器attempt1 exit0、3jobs/3results/27资产、96假回调/2805评估、99源码/构建hash MATCH、Job/Result数据库身份MATCH、全部自有线程/服务退出。原protocol/CPU1/96批/540秒/256MiB及前端不改，无医学F/B/update。v15 finalready/argv等固定源码后发布给总控，不自行执行真实模型；医院展示、冻结、临床NOT RUN。

**固定源及最终READY补录：** 受测source `54ff1565f6c11a6deea873feab0a011e879528fb`；metadata-only finalizer exit0，readiness SHA `2d484b1915cd952b5a06d635272a01d5bfc8ccc0226eb18ba442011db1b8ab58`、command-request SHA `6d1ba3b8d804cf25a72412e1b6980e38ee6d36ae031d524146ccea1ebc9f6aa0`，完整绝对路径见manifest。99源/构建及19包版本（含已有JPEG decoder）逐项绑定，正式DATA v2与中央owner链通过。既有两锁/slot/finished/receipt在采样时PASS，旧两UNKNOWN按原ceb164例外保留；未创建或修改队列文件，未预留槽，未初始化设备或导入实际Torch，患者像素/权重读取及医学F/B/update0。READY只供chief dispatch，不是运行或医院展示许可；command SPEC发布后追加chief实际dispatch SHA。启动时supervisor再次准入；DATA最终执行交付hash由总控汇总核验。真实MVP、医院/临床/最终冻结仍NOT RUN。


### 2026-10-11｜真实本机三 SOP 旧版 MVP 离线验收

INTEGRATION 原工作树/分支，整理前 HEAD `1057b03b9072029d1d3deba53801fd099fa128d1`，受测 source `54ff1565f6c11a6deea873feab0a011e879528fb`。总控唯一 dispatch SHA `934a55fa2d0f51f3198281befa8dab2d40a262a26e757ceaaa7622cd5f9597de`，原 v15 READY SHA `2d484b1915cd952b5a06d635272a01d5bfc8ccc0226eb18ba442011db1b8ab58`。实际历史 FrozenBaseline CPU 三例单 SOP 3 jobs/3 results/3 accepted attempts/27 assets；96前向批/2805评估、B0/update0、retry0。逐批 logits/输入/JobAttempt/SQLite/对象SHA、99源码及19既有包版本核验一致；528项离线断言不等于测试套件或临床病例数。新增 hospital-release/20261011-real-mvp-acceptance-v16，不改原 READY、源/环境或历史包。

浏览器真实三流程 PASS（36.0121/34.4746/34.2931s），父收据 elapsed111.958330s/exit0；supervisor SUCCESS/slot_completed true，收据 SHA `84508fb7d89e26b8a529e108a642dcfb424da7b2f7f9f110a4f2ede9769dbd20`；8实际module和10监督文件SHA一致，owned线程及服务停止、finished绑定正确。RSS组采样峰1705672704B、首样本swap增长0、一个启动TELEMETRY缺测保留、无预停；swap范围24MiB是最大减最小，未归为任务增长。旧两UNKNOWN started原字节不变/finished缺失。离线核验模型/浏览器重跑/像素查看/队列写均0，原患者产物只留获准忽略目录。

单切片64px像素badge与保存刷新断言有证据；16/32/64选择通过不代表逐尺度独立空间审阅，224响应/候选与14比较网格明确分开。完整Series左右/顺序/world/crop/resize/resample真实验收未完成；本次三开发流程不替代医院冻结配置三展示。医院default null、展示未批准、冻结/临床NOT RUN；E1/E2/F0/F1医院注册未验收，旧版回退保留。实际开发预计算产物未升级为医院备份，备用录屏未完成。当前本地交付包由总控汇总给钟佳桦，无自动消息、push、外传影像或部署。


### 2026-10-11｜负责人接收后的本地 MVP 快照索引增补

原 INTEGRATION 唯一工作树/分支，开始 HEAD `510d387ef02d55c22f01f9cbd282137ea1274934`。总控通知钟佳桦已接收 revision47 三条本地真实流程；只读状态 SHA `25294bed343786a56dccf5c1df0231f36c0229785a6e79667669ffa81b3d3a0a`，MVP PASS、v16交付/受测source `54ff1565f6c11a6deea873feab0a011e879528fb`/执行收据绑定一致。v16已完整验收，本轮只追加 RECEPTION_AND_SNAPSHOT_INDEX.json 和 LOCAL_REUSE.md；16个原v15/v16跟踪文件逐字匹配原提交，manifest SHA保持 `c8bcb4cc795cdafd36c93588b6d826ef8de69764e9b086618eb5b0fa038051c8`。接收明确为总控通知，不新造OWNER签署/医院批准；当前MVP不是READY未运行。

快照指向既有受保护结果、资产/SQLite/监督/截图的原路径SHA及private-audit，无复制私有数据或凭据。提供metadata与SQLite mode=ro数量读取说明，但本轮未重执行查询、模型、浏览器、服务、录屏或重跑528项验收；队列/DB写和外传0。原服务已退出，快照不宣称在线恢复已完成；需要服务复用时总控明确新增计算关闭的启动范围，不能重放已消耗命令。E2收益/F0/F1头/医院授权不作为本地MVP新阻断。医院展示未批准/冻结及临床NOT RUN，六项完整Series真实空间检查和医院备份范围保留。仅本地提交，未修改权威状态/READY/代码/环境，未push/部署。


### 2026-10-11｜E2/CTFM独立应用接缝 v17（仅生成与开发）

INTEGRATION 原工作树epi-next-integration/分支codex/epi-next-integration-20261009，开始HEAD `cad49f20d7f5d77027ca955e4a609abebb6fe58e`。追加ALGORITHM/next-1独立接口，不改旧2.0/FrozenRunner计算/16/32/64/GT-v1/A-B-C；复用Job/Attempt/lease/store/认证，默认关闭。完整request派生单一Job，未知提交一次发送后查receipt，新旧Worker类型隔离，max_attempts1。输出6终态、原logits/数值/空间SHA和真实runtime；native overlay只SUCCESS且映射验证。连续Q Mask、CPF gap、PSMI整patch及valid支持图层区分，CTFM保留有符号贡献、完整3D/head接口。

正式LOC source `9ae67d74ca695bac12bf3f2e2f0007438f72c79f`和dependency-lock逐项MATCH；薄adapter调用实际core，6/4/4生成函数F/B/update、NO_RELIABLE_RESPONSE如实保全，未降低阈值。合成原结果PRECOMPUTED回放0/0/0保存/刷新；原证据和成本保留，不称LIVE医学M1/M2。78项Backend/Worker/旧API/认证/幂等/SQLite生成迁移PASS4.49s，164项前端PASS1.83s、typecheck/build exit0（独立dist424ms）、34项生成空间/医院gatePASS0.24s。之后仅新增加载边界3项定向PASS2.72s，和78项有重叠，不累加。真实浏览器/模型/患者像素/权重/GT/队列/设备probe/录屏0；未安装依赖。既有Alembic pure-Python路径供生成迁移，原M0 DB没有迁移。

补齐e2_launch.run_existing_e2_job及独立run_existing_selected_fidelity：复用LOC consume_inputs、既有hash验证ResNet loader、原DifferentiablePreparedModel与ChildGuard单一预算；5F仅case3/F5/B0/update0/120秒，不重做P1或偷偷合并Q预算。所有加载器测试使用注入double，5次逻辑guard不是医学前向。trace/stage/checkpoint/native原值有界压缩保全。已有RICORD DATA v3/Prepared2DInput已经交付，不等待DATA重交；真实新scope/具体应用Job/输入/监督argv绑定与E2-Q科学结果仍缺，CTFM缺真实新head/volume resolver/handler，真实launcher完整argvNOT_READY。医院展示授权不阻断纯开发，但医院allowlist/新算法真实空间三展示/备份录屏/最终冻结及临床NOT RUN，医院default null。原M0已完成3条旧真实开发流程，不倒退为NOT RUN；16原v15/v16文件SHA保持。只交本地hospital-release/20261011-next-application-v17供chief汇总，未写权威state、未消息其他线/上传/push/部署。受测源码完整SHA提交后补录。

**5F绑定修正及工程状态补录：** 固定独立case3/F5/B0/update0/CPU120秒/64MiB的唯一task-key/Job/output目录，私有科学binding与外置chief dispatch分离；dispatch单向绑定binding及包含CLI的18源SHA，消除完整文件哈希自引用，不创建owner或新准入收据。6项生成chain定向测试PASS0.02s（完整链/四种篡改/无dispatch和已有输出），metadata argv exit0、输出目录未建/队列观察0。E2-Q只有单Job加载/执行函数，缺三例共享全局计数/时间启动封装，准确标ENGINEERING_NOT_READY；5F代码/参数绑定可交chief，实际新批准/准入/派发仍缺，医学NOT RUN。不重跑已有后端/前端整套。

**受测源码固定：** 应用接缝source Git SHA `6f1a1f1df87a4a9c4b9f1b58c358702c601aed54`；v17 manifest、申请片段和source-freeze metadata已绑定。5F私有binding SHA `cb5468820ab76aa0de5736ef1a6bac7ea630dc438743afe7c9428274ab48dc73`、18个源码字节逐项MATCH；metadata检查仅读取源码/JSON，未读取CT/权重/准备数组/旧Mask，唯一输出目录仍不存在。56个source提交文件审计不含私有影像/模型/数据库/凭据；显式base文档检查和staged diff PASS。该提交不是医院冻结批准，5F未派发，E2-Q三例封装ENGINEERING_NOT_READY，CTFM真实head/handler未交付。仅本地commit，无push/部署/第三方上传。

### 2026-10-12｜独立5F外置dispatch草稿与父监督入口

INTEGRATION原epi-next-integration工作树/codex/epi-next-integration-20261009，开始HEAD `22f2fa78e5e99e43214e8ad2ada3892592ae51ee`。总控交接真实分项请求SHA9900e1211e768ec20a4c688a7021e28e93335e8f8f82c279a4891ed15e33c5dd、owner SHA1856097dc8c161cd3d0cdbad150fd358198d09a1947a42a582b897bd7de50443、新准入SHA51ff321e8517088516fc9d713f001ba1e78414572bd174051930e3f7e0160bbb，metadata逐项匹配E2-FIDELITY-5F及精确task-key。新增最小父入口/生成测试/v18审核包，原v17全部文件和固定binding cb5468820ab76aa0de5736ef1a6bac7ea630dc438743afe7c9428274ab48dc73、18个绑定源码逐字保留。实际dispatch/唯一UTC窗口未发布，草稿不可执行，不假造owner/receipt或占用时段。

父入口复用原v12八模块/十依赖snapshot和run_supervised，独立120秒从子进程前覆盖导入/加载/校验/5F；CPU1环境明确OMP/MKL/OPENBLAS及实际intra/inter线程收据代码，线程测量无额外模型前向。持久计数5F/0B/0update、64MiB科学结果、原身份校验/采样预停/退出恢复路径保持，不新增锁/队列或重试。8项生成定向测试PASS0.03s（使用监督和Torch double）；实际metadata CLI exit0，原source/package/bundle验证PASS、真实Torch未导入，进程启动/队列读取写入/数组权重旧Mask读取/医学调用均0。不重跑应用或浏览器套件。E2-Q/新应用/医院展示不在本次批准范围，医院最终冻结/临床NOT RUN；受测父源SHA提交后仅补metadata。

### 2026-10-12｜独立E2真实selected fidelity 5F一次执行

总控最终dispatch SHA bf4c0d9fddcaf5287973f858a6bc64a9a2fce20c6b233c6298afb4832d0a7b14，唯一UTC01:31:10–01:46:10时段；原INTEGRATION工作树/分支，父source `bc5e32feca002303318703f1ddc6ba73f1d8b913`，原应用6f1a1f1/LOC9ae67d7及固定binding不变。原v12父监督器+新精确准入实际一次执行SUCCESS/exit0：F5、B0、optimizer0、extra_autograd0、retry0，五份原始logits/响应保存在获准私有结果。case3/已选epoch3604/cell43，固定模型类1，不进行新优化或GT选择。科学内层0.294360秒，父至退出3.427181秒、恢复3.434278秒；不得以内层时间替代真实全流程。

实际Torch2.14.0 intra/inter线程1/1，OMP/MKL/OPENBLAS1；线程记录无额外模型前向、无budget reset。监督SUCCESS、OWN_GROUP_EXITED/DEVICE_RECOVERED、slot completed true，新started/finished与receipt SHA对账；所有监督asset hash和18原source MATCH。9个启动TELEMETRY缺测保留，RSS是自有组采样峰非绝对上限，详见v19 manifest。实际科学结果SHA98aeba6d0a6a88b5b2ef2c5b928d62ed5406856129c7796a107975ae655a8e1b，supervisor SHA8e08ff8d98e22ba940ce1b27c5727a6bb0b6c4f1658096ed7e0eb26dbdb083dd；只记录本地路径/SHA/统计，不复制患者影像/权重/Mask/logits私有正文。无重试或额外warmup/模型检查；退出后只读对账，不启动其他阶段。此为一次开发样本忠实性测试，不是E2-Q、新MVP、医院展示或临床有效性；医院默认null/最终冻结NOT RUN，原M0/v17/v18保全。

**目标元数据差异补录：** 总控发现并要求保留：固定ApplicationRequest.task.target_class=0，实际五响应fixed_target=1。只读核对LOC科学配置scope.fixed_target与selected_fidelity源码，profile明确原图logits argmax固定用于每项响应；本次原图argmax1，函数不接收应用target字段。科学profile符合实际，应用元数据未同步，因此执行/监督SUCCESS保留，完整应用契约NOT_FULL_PASS_TARGET_CLASS_METADATA_MISMATCH，不得标完全PASS。原binding/结果均不改、不重跑；完整Mask remove为valid内x*(1-M)、外部保持原图，peak patch remove另行区分，不写full-mask-remove-peak。只完成INT元数据对账，不重复LOC离线算法解释。

### 2026-10-12｜HU v5监督接缝只读增量审查

原INTEGRATION工作树/分支，开始HEAD620014f3e1fd7a94b7b5a25df242ac2ed90bfb55。消费总控HU v5执行准备包01/03（各SHA匹配），仅审查DATA既有v4/v3/phase/Budget代码；当前四文件与a28a9bc受测字节相同。指出durable参数/调用计数、returned后raw诊断保全、4MiB含进度/残留及错误账本预留的本地接入缺口；已有primary/reporting分离、锁和phase可复用，不修改共享保护框架。phase末参数4GiB是磁盘reserve；RSS512MiB协作检查不能冒充native codec内连续监测。

发现条件性新接缝：a0.phase独立setsid worker不被Wave1按PGID的owned_group采样。仅新增无患者进程表fixture，直接执行锁定函数（fake getsid/table），同组纳入/独立组排除，exit0；不spawn、不ps、不取锁，真实病例/codec/model/队列读写均0。建议DATA本地接缝确保worker RSS/自身身份停止/reap再完成，外parent强杀时不得以finally或外finished证明独立组退出。只读查找失败是不存在路径/glob，无真实任务失败。正式简短兼容性审查在hospital-release/20261012-hu-v5-seam-review-v20，供总控传DATA；DATA唯一实现新入口和T12控制，ENC审核数值，本线不重跑已完成监督测试、不改DATA或UNKNOWN、不制造实际验收。

**实际调用链澄清：** 总控补充后只读核对已允许v4最终执行JSON（SHAe8b3fb…）内thin_wrapper_source，与其wrapper SHA18da6b9b0b9184187d972b7c5ecb93b0bb75ee7888265839d7c45098ecd0e364一致。v4是双原锁/单次Popen CLI/communicate90秒/CLI内phase，无Wave1嵌套；不要求新架构。初始条件性Wave1进程表检查被实际wrapper超时块生成注入取代：假两次Timeout、fake killpg只处理CLI组100，独立phase组101未证明回收，exit0；无实际process/native调用。补充DATA局部建议：新v5 exact entry/task/request重复检测（原regex仍v3）、phase握手PID/PGID/start与合作stop/reap/未知阻断、bounded stdout/stderr及final reporting失败不覆盖durable primary/counters。没有假造历史孤儿进程或真实验收，原DATA/共享源码不改。

### 2026-10-12｜10月14日基础演示清单与计算关闭的本机恢复

INTEGRATION唯一负责演示清单，原工作树/codex/epi-next-integration-20261009，开始HEAD `98c494d721b108ad97cfbf0ed61b642eec5925d8`。总控管理补充将HU v5/新分类头/E2正收益移出基础关键路径；先发布v16目录DEMO_CHECKLIST_OCT14_20261012.md，复用原54ff源/510d交付的3/3真实MVP，不重跑，不修改原16个已绑定v15/v16文件。DATA唯一v2 ledger bc919838…保持，清单三文件用途候选仅引用原case_index及派生SHA，原权限LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION；医院用途/受众/场地/设备/录屏仍待负责人批准，无新allowlist。

总控进一步授权最小非医学只读恢复开发，新增qa/local_mvp_readonly.py：仅loopback，原SQLite/对象/dist保全；新私有运行目录和DB副本签发8小时新认证，必要时仅续副本的原三源读取期限，撤销旧凭据/Worker副本准入；所有新任务/上传/变更和Worker接口403，无Worker/model/queue导入或启动。原Result2.0/source身份不改，页面只读提示，bound source/旧dist和对象SHA防漂移；三自有服务ready后才发布URL，正常单次停止记录退出/sourceDB不变。恢复接口复用原Backend/Gateway/Vue，不重构UI/算法/调度/工作树。

4项定向生成验收PASS2.09s：3生成Case/Result、27 PNG，新认证/刷新/过期读取副本/对象SHA/禁止写和Worker/无覆盖及范围拒绝，实际loopback HTTPS登录/静态提示/保存结果查询及三服务退出；无真实模型/DICOM解码/浏览器/截图/真实DB复制或像素读取。初期生成fixture漏accepted attempt补齐；HTTPS首次暴露backend冷启动竞态，后一次正常停止冒泡KeyboardInterrupt，均修正并留生成目录，不算医学重试。原业务测试不全量重跑；2项依赖deprecation提示保留。

生成验收与原3/3真实MVP分开：恢复真实启动/viewport复核NOT RUN。私有绑定SHA b03d88d251eb658d285d66462f550f4d2c392798c930c13bf7dd4e0ce1c0d1e4，66源/旧构建文件闭合，旧dist34文件SHA与受测readiness MATCH；实际metadata-only exit0、不读真实DB或影像。当前E2只有默认关闭的接缝/合成链，独立5F不等于真实应用集成，target差异保留；CTFM真实新头/volume handler未装入基础包。医院默认null/展示NOT_APPROVED/冻结与临床NOT RUN；无push、真实显示/录屏/模型或新数据职责扩展。受测恢复源完整SHA提交后补入唯一命令索引与清单。

**只读恢复受测源固定：** 新恢复source Git SHA `76d032edbd270a1e52b29750e3afbbbda6d7f508`，唯一清单/命令索引补录；binding及66源码/构建SHA不变，原34构建文件和16历史包文件MATCH。新恢复4项生成验收与旧54ff三真实流程分别引用；本轮没有执行真实恢复/新增医学调用或展示。

### 2026-10-12｜R71一次有界真实只读恢复验收准备

原INTEGRATION工作树/分支，开始HEAD8364b4d42695b2375ca0e84aa058ab80675284f2。消费R71第3节；总控已核定既有MVP_LOCAL批准4a4e9c…/2dcc61…、同三DATA v2 bc919838…及人工复核437158…，明确此次原结果/对象只读、私有DB副本、新本机认证及localhost浏览器检查覆盖于原本地用途，不是重用96F、医院或外传许可。保留原恢复source76d032及binding b03d88d…，不重设计、不改target计算。新增只读验收封装沿旧browse只读选择/叠加/刷新部分，禁止创建/上传/Worker/模型，网络仅同本机origin、无截图/视频/trace/HAR/像素导出。

固定plan SHA5776dafca76e1016a5c807e118890218ee6fe4b75050e030c5f371332c9b5446、entry SHA42c730b9ccc9465770d66d5468a025dcefa1edc0189eb556c5a1be846a1f1b63、输出.local/mvp-readonly-r71-20261013-01，总180秒，browser140秒；失败退出自有服务不重启。原绑定check-only与新plan check-only均exit0；准备阶段不读真实DB/影像/旧凭据、不启动服务/浏览器。第6项数值/canvas叠加及渲染技术检查与人工目视独立，未经目视不得扩写医生/负责人视觉PASS；真实运行后另记录十项结果、0调用依据和原DB/资产不变。

### 2026-10-12｜R71真实只读恢复一次技术验收

原工作树/分支，恢复source76d032/验收source482215cecdb133e2edcb271d226cd9c2b32ee546，按总控已核定原LOCAL_MVP_ONLY范围，单次plan5776daf…执行exit0/7.979043秒（上限180）。三原Result与单SOP SHA/Slice/尺寸、9次16/32/64选择、每例64刷新相同JSON实际通过；新登录正常，旧凭据私密本机读取后仅记录401。browser page errors0/external requests0。第6項为渲染/图层224/非退化变换/canvas边界/pixel gate技术PASS，人工目视NOT_RUN，无截图/视频/trace/HAR或影像导出，不扩写医生/负责人目视PASS或医院临床验收。

三个自有服务受控TERM退出（-15），父exit0；原SQLite SHA808881…不变，原30存储对象和5业务表内容/source vs shadow逐项匹配，3case/3job/3result/3attempt/27assets不增。副本认证/期限更新独立记录；原数据/旧模型结果不写，所有POST变更/上传/Job/Worker403，未启动Worker/模型，F/B/update0，不消费旧96F，不源ZIP，不自动重试。结果与路径/SHA在v16新增READONLY_R71_REAL_ACCEPTANCE_20261012.json及唯一演示清单；影像/账户/DB正文不进Git。医院显示NOT_APPROVED/冻结与临床NOT_RUN；只读恢复能力可用于14日基础限定冻结决策，不依赖HU/head/E2收益。

**管理网络修订收口：** 负责人允许正常联网/Wi-Fi/热点/HTTPS/投屏及既有合法控制面，网络本身不再是阻断或“只能完全离线/localhost”的制度要求；当前仍复用已实际PASS的本机只读恢复，不因放宽切换部署、重测无变更功能或增加CPU/MPS实时推理。全部独立GPU AI Node明确排除。原三图LOCAL_MVP_ONLY不自动升级医院展示/外传/截图/录屏许可；只由总控合并素材用途决定，无复杂场地/人员审批体系。清单旧真实恢复NOT_RUN已替换为R71实际技术PASS，人工目视/医院用途/临床状态保留。本轮只完成必要收据/文档提交，无新测试或恢复，收口后停止新增工作等待负责人用途决定。

### 2026-10-13｜R76 E2/F0 版本化结果接缝

**任务类型：** EPI-NEXT 应用接缝与生成验收。**任务负责人：** INTEGRATION。工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`，分支 `codex/epi-next-integration-20261009`，开始 HEAD `8e8b202a00ea4bc4c407e206d08b630a6dbfd566`；接缝源码提交 `fca57445fe6f82c9e9bc501b053b889928832d1f`。

根据已交付的 LOC 目标契约 v5（SHA `d852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c`）和 ENC 接口 v4（SHA `2b2e2d0ebb6e56094451baab09e969782258155bbc6cae31ee769dcac92e0467`），新增 E2 目标绑定/保存结果 facade、F0 已保存证据消费、研究结果后端拒绝门与条件式证据面板。F0 仅从绑定的 evaluation/head/cache 文件核验 SHA、模型/预处理/配置/manifest/病例结果身份、FP64 GAP 和分类 logits 重建、signed contribution 与 effective bias，以及名义 native/LPS 正逆坐标变换；不调用 encoder/head 模型。没有接入真实 Worker 注册、真实模型装载或新设备队列。独立研究 app 工厂不替换基础 app；默认旧入口继续保留。

问题及修正：首次生成 F0 fixture 未包含 ENC 交付行中的 `source_group_id` 和 split 字段，导致在输入绑定检查之前进入失败路径；补齐合成 fixture 字段后，完整 15 项后端测试通过。前端刷新测试曾在 Vue mounted 更新完成前同步读取选择器；测试等待一个 `nextTick` 后 3 项均通过，组件使用 sessionStorage 保存结果级别选择。没有重试任何医学执行；本轮没有医学执行。

验证：后端 `backend_v2/tests/test_research_seams_r76.py` 15 passed / 3.15 s（依赖产生一条 Starlette/AnyIO deprecation warning）；前端 `frontend/src/tests/research-evidence.spec.ts` 3 passed / 0.47 s；`vue-tsc -b` exit 0；Vite production build exit 0，输出到独立 `/tmp/epi-next-integration-r76-build-20261013`，未改旧 dist。构建记录既有 DICOM codec 的 Node core externalization 提示和大 chunk 提示。验收报告位于 `hospital-release/20261013-r76-research-seam/ACCEPTANCE_REPORT.md`。

范围限制：所有新测试为生成数据，测试 Worker 通过进程内 TestClient/transport，不是真实服务。没有读真实 CT、保护资产或模型权重，没有启动服务、MPS/GPU、实时算法前向或医院浏览器。R71 既有只读技术 PASS 保留但不替代真实新算法空间验收。LOC E2 实际 handler/医院 Job 与 ENC F0 实际 head/cache/logits handoff仍 `NOT RUN` / `BLOCKED_BY_DATA_HANDOFF`；完整 DICOM 方向、切片、世界坐标与几何链、六种状态 UI、连续三次医院演示、医院素材用途批准和临床验证均未完成。E1 未在本接缝注册，旧 Occlusion16/32/64 未重命名 E1，F1 未完成。当前不改变 FrozenBaseline/v16 展示候选，不宣布医院冻结通过。

**交付与回退：** `hospital-release/20261013-r76-research-seam/manifest.json` 指向实现 commit 和准确契约；`ALGORITHM_COMPARISON.md` 列出 default/experimental/incomplete 状态；`DEMO_AND_ROLLBACK.md` 保留 v16 操作入口和切回方法。负责人尚未决定原本地影像/结果医院用途；只提供本地版本化交付材料，无上传、截图、录屏、部署或推送。

### 2026-10-13｜R77 E2-R 科研实际加载入口准备

**任务负责人：** INTEGRATION。原工作树/codex/epi-next-integration-20261009，开始HEAD `75d2ef118ea717e8c3cbcb413e247f25d964eb55`，最终运行源码 `e303595099b31d7ab6f66652feda1b7fdffc1fa5`。按总控委派只闭合 E2-R 科研入口，不进行重复MVP联调或医学调用。复用 `build_existing_e2_runner`、同一 `predict_numpy`/可微模型和共享ChildGuard，调用LOC固定 `run_readout`；新增task `EPI-NEXT-E2-R-CASE3-CPU-20261013-V5-INT-1`，原5F/P1任务不可复用。旧数据/模型引用保留私有binding中，不复制数组/权重或结果正文。

初版工程暴露两个缺口：64MiB只覆盖科学文件，不能证明包含监督输出；异常完成把已知部分计数写成null。已按总控审阅修正：既有IO锁与BoundedStore复用，父子共享累计写入账本，atomic替换/append/失败均预先记账、无退款，每次账本写保守512字节；另外扫描保留文件、临时和失败残留。8MiB终态额度替换原16KiB假定，native父子日志各限1MiB，超额排空并记录丢弃/失败。共享监督框架/队列锁源码不改，只在本task进程内安装IO回调；模型计数与身份停止仍由原监督负责。已知context计数随ReadoutFailure传递到完成记录；确实未知保留null。账本未提交临时事务阻断为UNKNOWN，不能读旧值继续。

验证只覆盖受影响接缝：25项生成PASS2.74秒，正常14F/4复用、2F适配失败、旧logits不符0F未加载模型、加载时间不重置、批准/新task/同队列/slot篡改拒绝，以及累计替换、父子同账本、失败不退款、native日志限制、真实共享guard生成完成记录和已知/未知失败计数。测试只使用合成数组/toy模型；启动一个普通Python日志fixture，无医学资产/队列/slot。随后只修正执行摘要及父异常的账本外输出，不扩大验证；最终源metadata check exit0，Torch未导入，数组/权重读取0、医学调用0、队列观察0。

最终私有binding `.local/e2-r-readout-v5-20261013/execution-binding-r77-final-v4.json` SHA `92fb6d542b69d094f0e3fb65474f16827bc75d5f81b2632d584f225f0bf8f928`，item `approval-item-r77-final-v4.json` SHA `0f330e7ef460f3e00811583f3e4ea93aa5a4f8232d8800fef806ebe2e97aa53a`；只v4可合并最终申请，此前草稿未派发。24项INT/IO源与16项LOC源、原8共享模块/8依赖条目及包版本闭合；README/manifest给定一次实际argv，尚缺总控真实dispatch SHA。累计字节以保守写入预留报告，不冒充保留大小或实测性能；终态超过剩余额度会拒绝，不承诺报告一定成功。

旧MVP binding b03d88d…的66源/构建逐项MATCH；本轮没有读原DB/CT/对象，未启动服务/MPS/GPU、新展示或重跑旧验收。FrozenBaseline/A-B-C/GT-v1/旧Occlusion/5F收据不改。R76 `DECLARED_FIXED` 文档已更正为允许解释类与预测类不同；原代码/生成测试正确，不据此回写科学历史。状态 **GENERATED_ENGINEERING_PASS / PREPARED_NOT_EXECUTED / BLOCKED_BY_APPROVAL**，真实研究结果和E2/F0应用消费均NOT_RUN。CT-FM已有科学批准维持，新增申请仅E2-R；交总控合并待批，不自行批准或占槽。

### 2026-10-13｜R77 执行入口故障与最小修复

唯一 R77 真实执行已退出 `FAILED`，监督原因 `MONITOR_FAILURE_ValueError`，根因 `LIVE_TASK_OWNED_CHILD_REQUIRED`。父监督已完成 slot 收尾，但计数为 0F/0B/0 sequence、无 cases，未进入 child admission、模型或医学前向。原收据与失败目录保全；未知事务不重试、不把监督故障解释为科学结果。

INTEGRATION 仅修改新接缝 `qa/e2_readout_output.py`：保留真实 `subprocess.Popen` 对象以满足共享 `DeviceSlot.track_child()` 身份检查，并将 drain 线程纳入实例 `poll()` 的退出观察，继续执行有界日志排空。共享 `execution_lock.py`、`wave1_supervisor.py`、队列和历史协议未修改。生成测试使用普通 Python child 和共享 `DeviceSlot`，25 项窄测试全部通过；无真实 CT、权重、模型调用、GPU 或队列占用。

新 readiness binding 为 `execution-binding-r77-fixed-v1.json`，SHA `c62d7d98d00b3d132e14652307044381161145bc9fbe5107a53eafd2ea648cfa`，使用独立 `...INT-2` task/job。原 `final-v4` binding 和原 `...INT-1` 输出继续作为不可重跑的历史记录。修复结果只达到 `PREPARED_NOT_EXECUTED / BLOCKED_BY_NEW_DISPATCH`，须由总控重新发布 owner/admission/dispatch 后才可考虑接续；本轮未执行新真实任务。

### 2026-10-13｜R79 E2-R drain 生命周期与精确申请

新接缝继续返回真实 `subprocess.Popen`，并修复 `poll_after_drain()` 无超时等待：poll 立即观察原生退出；drain 使用 select/停止事件，退出后最多 0.25 秒，超时进入受保护失败记录。实际生成父子生命周期测试覆盖成功、提前退出、deadline、未知身份、ProcessLookupError 早退和继承管道；33 项通过。未知 actual 保持 `null`，原 R77 收据未改。

新 R79 申请固定原 case3、原保存 Mask、v5 science 配置，14F 计划/18F 上限/0B/0updates/CPU1/120秒/64MiB/无重试。binding SHA `f16169a035add8a8a022f1ccb5fa5add32229dc57905e332f8acd064e9cc2daf`，申请 SHA `058a1e929bb4c235d4a6b420821dae7fa3a31e9ec076256f0204dca603acf1a6`。未修改 ENC、监督 bundle、MVP 或历史研究资产；新执行等待总控集中审批，不自动派发。


### 迁移接续最终收口｜2026-10-13

在原INTEGRATION分支 `codex/epi-next-integration-20261009`、工作树 `EpiLocate-worktrees/epi-next-integration` 完成有限申请元数据和文档收口，开发前及执行源码HEAD `ae39a6b6fe0c4c46fac98b4d2e086dacf980f982`。新外层E2-R请求 `hospital-release/20261013-r79-e2-r-seam/approval-item-r79-v2.json` SHA `9ae5d0e90663934ed4962edec83dd2942584209ba6c2e7d2d91b64581d2b776b`，追加INT/LOC真实提交、21项runtime引用和既有输入/Mask/权重索引。原binding、V1、manifest、33项生成测试、科学配置和预算均未改。最终提交可由本节所在提交解析，不用自引用占位commit。

metadata入口PASS，Torch未导入、model_calls0、arrays_weights_read=false；新runtime及生成测试源码SHA独立核对通过。复用33项生成测试，日志实际7.54秒，旧7.43秒摘要在README增量更正。23个INT源与16个LOC锁定源分别对应上述INT commit和LOC `11ac87b91ea863a0f394aa53a9e3db6571691bc6`。测试/工程核验不等于真实E2-R，历史actual=null保持。

现有展示清单只补三历史Result/64层的保存索引与候选状态，数据仍LOCAL_MVP_ONLY。保留原会话中断留下的未跟踪 `frontend/demo-candidate/` 与 `qa/demo64_build.py`，不提交、不运行。64-only冻结dist/API限制验收、独立空间/目视、医院用途、三次演练与录屏仍缺。没有新会话、模型、恢复服务、队列事务、权限写入或push。已有R18 V2直接复用ENC交付，不改其源码/申请。


### 2026-10-13｜64-only候选工程收口（静态与生成资产）

总控接续原INT中断候选；分支codex/epi-next-integration-20261009，工作树EpiLocate-worktrees/epi-next-integration，起点f591c0e3d4bfe099792d9a803443ff7b653377d3。本节所在源码提交固定本轮实现，后续冻结清单另记该完整提交。没有push、科研admission/slot/dispatch、模型调用或真实影像显示。

新增独立qa/demo64_policy.py、qa/local_mvp_demo64.py；接续qa/demo64_build.py及frontend/demo-candidate。唯一DATA ledger和旧offline audit只作元数据投影，不建立第二份数据资格。旧reader、v16、DB、对象和旧dist保持；启动时只允许新私有副本，严格匹配三Result/单SOP/模型身份，限制12个对象（3输入+9个64图层），所有其他对象与写/Worker路由拒绝。返回JSON剔除16/32、cross-scale及非必要附加字段。新入口默认只核验元数据/源码/runtime/dist，不启动服务。

登录测试首次503：原gateway用病例列表作为token探针，与新限制冲突。候选gateway内部只把该探针映射到固定Result认证，外部病例列表入口仍拒绝；未改原gateway代码。合成测试经过初始依赖路径错误与该503失败，修正后8 passed/2.26s；覆盖三Result、身份/模型/资产漂移、16/32和其他对象、路径/查询/方法旁路、HTTPS登录/退出、原DB不变及三个自有服务回收。生成服务未启动Worker或模型；并非真实医院演练。

隔离前端候选增加3项生成回归，加原11项几何测试，共14 passed/590ms；验证旧16偏好不能恢复其他尺度、只请求64图层、非绑定Result不读取CT或图层、无病例/任务/Series/3D/研究路由。显示历史结果、RICORD来源代理类1A/1B与非病灶概率边界。vue-tsc + Vite8.3.1 production build通过；已有codec fs/path外置及大chunk警告保留，不宣称真实浏览器验收。

工程环境：既有Python3.11.15主仓库venv + frontend/.local/mvp-20261011-browser-deps，无安装；已有Node/npm和node_modules。测试命令：PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 <main>/.venv/bin/python -m pytest backend_v2/tests/test_demo64.py -q；隔离候选内npm exec vitest -- run src/tests/demo64.spec.ts src/tests/geometry.spec.ts；VITE_PUBLIC_BASE=/mvp/ npm run build。

仅完成工程候选；真实FrozenBaseline/64空间链、人工目视、医院用途、最终三次演练和录屏播放仍未完成。DATA E1/E2 prepared expected不等于生产空间验收，旧开发3/3和R71技术PASS不抵扣。原R18/E2-R最终申请字节不变，E2 V2外层21项runtime引用显式校验一致，Torch未导入；真实科研NOT_RUN，历史actual=null保留。


64-only源码提交已固定为`c3ddad7064c79ba6afd24884c5ec3abed1bcf8ce`；私有frozen-candidate-v1.json SHA `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917`，190源码/旧恢复文件、21dist、23runtime引用。默认metadata检查PASS，无payload/模型/真实服务；原展示清单新增逐项工程和未完成验收记录。原科学申请SHA、旧失败与actual=null保留。
