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

### 2026-10-02｜云端工作区恢复：UI阶段

**负责人/分支/起点：** dot；独立`EpiLocate-mvp-recovery`，`dot/mvp-recovery-20261002`，固定`2be89143a8abccb3c3896a8f53633e490cf79b28`。原`EpiLocate-mvp-design`与旧Git对象在环境替换后确认为空，不是git reset或产品代码故障；此前未备份，无法恢复原SHA。
**完成：** 根据会话保留的完整文件创建/修改脚本恢复CaseCollection、Dashboard/Cases/Result、workspace.css与7项UI回归。不声称逐字节复原旧提交。代码、模型、患者资料、GPU与冻结边界不扩展。
**新验证：** Node24.19.0锁定安装；92/92 tests（16spec），TypeScript+/mvp build通过；旧warning保留，无独立lint配置。新环境证据日志将与自包含bundle/format-patch一起持久化。文档/差异检查按固定base执行。
**边界：** 未push/部署；接口与后端恢复独立进行并需要重新集成/审核/测试。遵循用户先不截图，不操作Mac或另行发布预览；实际视觉与真实E2E仍未验。

**恢复轮前端接口集成：** UI新提交`16998839301cc83e296f2d583cdd4dd782004d6b`；auth/client新提交`989485d2605d47c257482eb1bb99f8dc36f8e2a6`汇入为`572ccd376ec9660dd4aabb4cfcb81d87b8348165`。新环境111/111 tests（16spec）和TypeScript+/mvp build PASS。恢复本地合成浏览器QA模式/筛选/refresh/Back脚本并仅验语法，实际渲染仍未跑。前端阶段完整bundle（含祖先history）verify成功，连同patch/测试日志/HEAD/校验清单已持久化用户私有Library。旧未发布对象仍不可读取，不把此次新提交写成旧提交复原。

### 2026-10-02｜Backend 幂等 Job 重放修复重建与重新验证

**类型 / 执行者：** Backend / QA / 文档；Codex 按本轮修复及恢复授权实施。
**来源 / 工作树：** GitHub `skyfrostz/EpiLocate` 的固定基线 `2be89143a8abccb3c3896a8f53633e490cf79b28`；独立 `/workspace/scratch/83af3b968556/EpiLocate-job-replay-recovery`，分支 `fix/job-replay-recovery`，开始时 tracked/untracked/ignored 均为空。
**新实现提交：** `657a758fc5084343e43f7f2421b0f9dde1ba6cd4`。云端工作区替换导致此前未发布 Git 对象不可用，本轮依据可见实现及审查记录重新构建，不宣称与丢失对象逐字节相同，不沿用旧提交作为新验证证据。
**发现与实现：** 原 `create_job` 在检索幂等键前先检查输入有效期及当前 ACTIVE 模型，已接受但响应丢失的请求在输入到期/清理、模型退役/替换后无法取回原 Job。现在保持 owner、非 DELETING Case、Slice 归属校验，按同用户旧键使用 Job 的固定模型版本及原请求协议核对参数、输入 SHA 和模型完整摘要，再返回原 Job，不改状态或重新派单；新键仍需有效输入及 ACTIVE 模型，变更请求返回 409，不可见资源保持 404。包含此前独立审查指出的空协议边界：仅 Prediction 的省略协议允许默认值，Occlusion 显式空协议为变更内容，必须拒绝。
**新测试证据：** Python 3.12，隔离 `/tmp/epilocate-replay-recovery-venv`，仅安装 `backend_v2/requirements.txt` 的常规 CPU 依赖。原基线加新增重放测试：8 failed / 38 deselected；恢复修复版，`/tmp/epilocate-replay-recovery-venv/bin/python -m pytest -q -ra backend_v2/tests tests/test_project_documentation.py` 得到 **63 passed / 2 skipped**（后端 60 passed，其中新增 46 项；文档 3 passed）。新增范围含 Prediction/Occlusion、输入到期与清理函数、模型退役与替换、七类 payload 变更、跨用户键隔离、DELETING/错误 Slice、输入/模型摘要变化、非法新参数；一项 Starlette TestClient/httpx 弃用 warning 保留。
**边界：** 两个跳过分别需要 PostgreSQL/MinIO 配置与固定 Worker/冻结模型运行环境；无 Python 缺依赖阻断。SQLite HTTP 回归不是 PostgreSQL 并发、真实账号、生产、GPU 或临床验收。未改研究、GPU、冻结、Worker、frontend、部署；未 push/merge。CPU/GPU 数值门槛仍 OPEN。新提交交主任务集成，并生成完整补丁及增量 Git bundle 的私有恢复包；包的持久保存状态需以实际上传结果为准。

### 2026-10-02｜恢复版前后端集成与重新验收

**代码集成点：** `dot/mvp-recovery-20261002` @ `25f1cdfc38eda96af3b813ad35bcb655b0a99926`。新前端审查点`d67cc020350a6c601b206861e900da8c03554c70`与后端审查点`877573ed2e5c70294b60c662df0a527593541c95`已组合，逐路径代码diff均为空。仅双日志追加处冲突，保留双方小节；无代码冲突。
**新独立审查及集成复跑：** 前端111/111（16spec）、后端及文档63 passed/2 skipped（60+3），TypeScript+/mvp build、文档范围检查、diff-check、浏览器QA脚本语法通过。独立review重新看新实现和测试，不沿用旧批准。外部PostgreSQL/MinIO和冻结Worker两环境测试未配；实际浏览器/真实GPU E2E仍未跑。
**交付与差异：** UI/业务行为没有有意偏离旧方案，但旧对象不可读，没有字节相等证明；本轮新写恢复报告并保存完整bundle/patch/新日志/校验清单到用户私有Library。前端阶段已验证bundle离线clone SHA与base上patch重放tree一致；最终整包再次验证。新SHA未push、未主线merge、未部署，需新审核后再决定发布。详见`frontend/docs/RECOVERY_20261002.md`。

### 2026-10-02｜Result 原始影像错误优先级修复

**分支/起点：** `dot/result-input-error-priority-20261002`，独立补丁，起点`d6e2690b501b645d5be8b323e107c90c703654ab`。原恢复仓库仍可读，未进行重建。
**问题与原因：** Mac Chrome合成API验收发现DICOM 410时既显示到期原因，又因caseDetail尚为空而出现“病例与结果不一致”。几何函数按缺失数据保守拒绝叠加没有错误；问题是输入尚不可用时把派生拒绝原因当作独立错误呈现。
**最小修复：** 仅在CT输入状态ready时显示几何拒绝原因；loading/expired/error优先保留实际输入状态和原因。未修改几何函数、像素坐标/版本/来源门控、叠加控制禁用、独立图层加载、API或模型。真实输入成功但case不匹配时仍显示几何错误。
**验证：** 新增4项回归在修改前全部失败，修改后全量115/115（16spec）、TypeScript+/mvp build通过。覆盖410、网络错误、加载后真实case mismatch、过期后成功重新读取，并断言独立热图DOM保留和不可用叠加禁用。使用jsdom和viewer stub，不代替浏览器解码/几何验收。原codec/bundle警告保留；无独立lint配置。
**边界：** 焦点闪屏、loader初始化与性能问题本提交不处理，待固定viewport正常硬件测量；不猜测根因。未push/merge主线/部署；补丁与完整bundle将私有持久化，再交新审核/浏览器复验。

### 2026-10-02｜被动会话核验保留布局与隐私遮蔽

**分支/基线：** `dot/passive-session-layout-20261002`，`c565b7f3a323fc583faac13dac8aeb497c11f24b`。Mac正常硬件固定viewport的合成focus及受控延迟证实旧display:none对应stage/overlay归零；主CT canvas保持，不能扩大为camera重置、原生focus已复现或通用性能根因。
**实现：** App被动核验改为保留DOM/布局，祖先立即opacity0+inert+aria-hidden+pointer-events:none，fixed不透明核验层不占文档流；初始未知/明确失效仍硬加载。增加AppShell全局导航键verifying guard，避免inert外的window监听器修改隐藏菜单。session/API/CSRF/epoch/网络频率、viewer/module init/RO/几何/模型均不改。
**验证：** 4项呈现期望先在旧代码失败；隐藏菜单Escape回归也先失败。修复后120/120 tests16spec、TypeScript+/mvp build、QA脚本语法通过；独立源码安全review无阻断。detached jsdom曾返回过时computed opacity，改正常body附着fixture复验。没有把DOM测试称真实布局测量；新脚本供Mac测量至少5秒synthetic核验中/恢复后的尺寸、隐私与手机键盘行为。
**边界/交付：** 保留严格身份未知时的即时遮蔽，不承诺完全无视觉切换。此新提交仍需真实浏览器复验；未push/部署。独立补丁、完整bundle、测试和恢复日志私有备份；详见`frontend/docs/PASSIVE_VERIFICATION_LAYOUT_20261002.md`。

### 2026-10-02｜移动导航恢复焦点最小修复
**执行：** dot；worktree `EpiLocate-mvp-recovery`，分支 `dot/mobile-navigation-focus-20261002`，起点 `eb8f6f85152861e673efd8816f1e5f198e01477c`。提交SHA由交付包HEAD及Git记录定位。
**原因/变更：** 原watch仅监听菜单开关，核验解除后没有焦点锚点；Tab trap只判断首/尾，BODY等外部焦点没有兜底。改watch open/verifying并在nextTick后检查当前身份、epoch、节点连接和document.hasFocus；已在有效菜单项上的焦点保留，外部焦点恢复首项。Tab外部双向兜底，禁用按钮及显式tabindex=-1不参与。后台页面不强行focus，正常页面焦点触发核验完成后再恢复。
**回归：** 新4项在旧AppShell全部失败；修复后全量124/124（16spec）及VITE_PUBLIC_BASE=/mvp/ TypeScript/Vite构建通过。覆盖核验后BODY恢复、已有效焦点保留、后台不抢焦点及再次聚焦核验、双向外部Tab与首尾wrap。现有隐藏期间禁键、401/换号/CSRF及其他业务测试继续通过。没有独立lint配置，保留既有codec与bundle警告。
**边界：** 本次只改AppShell及测试/双日志；auth、API、App布局、viewer/RO/初始化及后端不变。Mac反馈用作问题线索，本次云端未运行真实浏览器。待独立审查、完整bundle/patch恢复验证与私有Library保存后，交Mac复验；尚未push或部署。
