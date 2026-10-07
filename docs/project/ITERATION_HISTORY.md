# EpiLocate 项目完整迭代史

> 文档基线：`p0/integration` / `b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5`（2026-09-28）
>
> 本文记录可以由 Git、仓库文档、测试报告和验收材料追溯的项目演进。提交时间只在无法确认实际开发日期时作为归档日期；提交信息本身不被当作完整开发过程。

## 阅读说明

本文使用四种状态：

- **已实现**：代码或配置已经存在于对应分支。
- **已通过测试**：有明确的测试、构建、HTTP、浏览器或 E2E 证据。
- **已完成集成**：能力进入指定集成提交，并且本文会给出该提交。
- **已部署**：有独立部署记录和运行证据。Local、loopback、临时容器不等于生产部署。
- **尚未完成**：报告明确指出未实现、未运行或仍需验收的内容。

`FROZEN_VALIDATION`、`LIVE_CASE`、`MOCK` 是不同来源。科研冻结结果、真实在线推理和旧 PNG/JPG Mock 不在本文中混为一种结果。

## 时间线索引

| 归档日期 | 阶段 | 主要证据 | 集成状态 |
| --- | --- | --- | --- |
| 2026-09-22 | 项目初始化与 DICOM/训练 Baseline | `3bd03853c5123dab8f40e145c7b42aa05a3a15bb`、初始 `README.md` | 已进入后续历史；部分运行细节只有 README 证据 |
| 2026-09-22 | Rule B 系列筛选协议冻结 | `db100c250d13f8cc3c53b315ca39c6d9f8d80c98` | 已进入主线祖先 |
| 2026-09-23 | Gradio Mock 原型 | `f153b9b5c15ffb8de86415fdbf38ac5cf0386248` | 原型分支未直接并入 `p0/integration` |
| 2026-09-25 | 人工复核服务与展示站 | `65d1861d8776c06038472c576f453a7b90256fa2`、`14c114ab26226561615315f7d3d25e42fcec64cc` | 进入 `p0/integration` 祖先，但不是在线推理闭环 |
| 2026-09-25/26 | Stage 1 FrozenBaseline 科研验证 | `e81480d5e186905870e8e60cd5db7993706720ae`、`f59738a606d15ff7062bbc64fc316ba276035ce4` | 并行研究分支，不是 `p0/integration` 祖先 |
| 2026-09-26 | P0 真实单切片算法接入 | `34edd02637fd4d5a54fed37dd926229e43c5b69a`、`3b3c270869663293769f99ab3cbc180904185a1f` | 后续并入 P0 集成线 |
| 2026-09-26 | P0 前后端分支与 QA | `93d2e8f013d64979972bc88e7cbdba71007ca6b7`、`3b400c39437ec6685b5f056fb039f9dcfe0bedb6`、`7366dd3cf4dbc030864c230817ba52604e348cdf` | 通过合并提交进入 P0 集成 |
| 2026-09-26 | P0 统一集成与发布 | `021e4f56103e53c82b5abf76465f62fb4f1bc6c3`、`v0.1.0-p0-release` | 已集成；另有独立 QA 分支复验 |
| 2026-09-26/27 | Backend v2、Worker v1、Vue Frontend v1 | `385cab52389a58f1c8493b452f663487ca2e7c0a`、`24d4fbf8674ce4f34070daebe006ea31ab13f647`、`8a7952a1b0819e3db1630c3c486cf5544ef6a99a` | 经过 Phase 2 合并进入 `p0/integration` |
| 2026-09-27 | P1 Phase 2.5 认证与安全 | `df50656237e2ed63f7b6f7612dc290fdd395bde0`、`c9a5cc6373ffc889725971e3cae5bc09252790bd` | 已完成该阶段集成 QA |
| 2026-09-27 | P1 Phase 3/3.5 Worker 设备与 CPU 回归 | `396d188b6184ec08ce6b71e5f5b1dab7206dc00b`、`02c8ef9c86d2b4aa338a38142bee25ee2234dc34` | CPU 验证完成；GPU 未验证 |
| 2026-09-27/28 | P1 Phase 4/4.5 Heatmap–CT Integration | `77ef944ec88db6992a16b395a13434d7065f4186`、`580b58ed2b5933c32198165e71be91198e2224de`、`b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5` | 当前历史基线 |
| 2026-09-28 | Phase 5 多人入口、本地 CPU 链路与远程节点准备 | `639bfec38283728b54b0b6ce7961df10ea9ec535`、`e74f98432019eb46691e085b957fecb8e23ca1a3`、`15d7b67b019df0dbf16afa93e447bde7b6d58b29` | 仅 Phase 5 开发分支；未进入 `p0/integration` |
| 2026-09-28 | Phase 5 GPU-only 全链路工程 MVP | `4d717a3753ef307ab370adeafaf5a00da4dc7af9` | 分支级实现及测试入口部署；数值一致性失败，未集成、未达到生产就绪 |
| 2026-09-28 | Backend API / Frontend Integration 文档 | `ab36dea60e518ae86d8b9749d876d94d2102511d` | 独立接口文档分支；未作为集成实现基线 |
| 2026-09-28 | Phase 5 GPU MVP 最终交接验收 | `352152ce95fc26eb2dc0a4c309521d50486472ba` | Phase 5 分支验收记录；功能 PASS、数值门 FAIL/OPEN |
| 2026-09-29 | Repository Consolidation Phase 0 | `718d3220a2191aba0dd8fbfe1d673546997d1c04` | 独立规划分支；仅目录说明、Source Map 与迁移计划，未迁移业务源码 |
| 2026-09-29 | JPEG Lossless GPU Worker 事故与恢复 | `f80d4cf406689cd031f993090783e281db93c4ef` | Phase 5 分支事故报告；原病例关联证据只留受控本地环境，历史失败保留 |

以上日期是 Git 提交或报告归档日期；有报告执行日期时另行说明。Phase 5 从 `b069a8ce...` 分叉，其开发分支成果不自动成为 Phase 4.5 集成基线能力。

## 阶段一：项目初始化与离线 Baseline

**时间：** 2026-09-22；初始提交时间作为归档依据。

**对应分支：** 内部初始 `main` 历史；内部历史根提交为 `3bd03853c5123dab8f40e145c7b42aa05a3a15bb`。本公开快照不继承该历史。

**关键 Commit：** `3bd03853c5123dab8f40e145c7b42aa05a3a15bb`

**当时项目处于什么状态：**

项目还是一个以离线实验为中心的医学影像 Baseline 工作区，主要工作是整理 DICOM、建立患者级数据划分、统一预处理、训练和检查脚本。还没有在线 API、Worker、Web Viewer 或多用户任务系统。

**本阶段为什么要做：**

先固定数据和模型输入方式，避免把切片随机拆分造成患者泄漏，并为后续算法服务提供可重复的预处理入口。

**本阶段完成了什么：**

- DICOM 整理、序列汇总和元数据检查脚本。
- 患者级 train/validation/test 划分脚本。
- HU 转换、肺窗、归一化和 224×224 缩放预处理。
- Dataset/DataLoader、ResNet-18 初始化、tiny overfit 和训练入口。
- README 记录了 Baseline Step 1–12 的目标、边界和开发用途限制。

**主要技术变化：**

从原始 DICOM 文件和手工检查，形成了可重复的 `src/`、`scripts/`、`configs/`、`tests/` 结构。患者级划分成为后续验证的基本边界。

**过程中遇到的问题：**

初始 README 记录了序列筛选、元数据审计和 Baseline 训练结果，但这些运行过程的完整命令日志和每次问题排查记录没有全部进入 Git。

**如何解决：**

仓库保留了对应脚本、配置、测试和 README 中的结果说明。无法由现有证据确认的开发过程不在本文补写。

**验收结果：**

初始 README 声明已完成 DICOM 整理、患者级划分、预处理、抽样 QC、DataLoader、模型初始化、tiny overfit、1-epoch smoke 和 10-epoch Baseline。这里属于 README 记录的历史事实，未将其扩展为当前集成服务能力。

**本阶段留下的技术债和后续问题：**

当时没有在线推理、任务状态、对象存储、访问控制、浏览器 Viewer 或正式的临床有效性验证。Baseline 的开发用途限制仍然有效。

**阶段总结：**

这一阶段建立了可重复的离线数据和模型基础，但项目还不是一个可供用户上传病例并查看结果的系统。

**证据来源：**

- `3bd03853c5123dab8f40e145c7b42aa05a3a15bb`
- 该提交中的 `README.md`、`src/`、`scripts/`、`configs/` 和 `tests/`

## 阶段二：Rule B 系列筛选协议冻结

**时间：** 2026-09-22；使用 Commit 时间归档。

**对应分支：** `main` 祖先。

**关键 Commit：** `db100c250d13f8cc3c53b315ca39c6d9f8d80c98`

**当时项目处于什么状态：**

离线数据准备已经存在，但序列选择需要一套可复核的规则和人工复核输入输出格式。

**本阶段为什么要做：**

为了把系列选择从临时判断变成可记录、可复核的协议，并避免在后续数据处理时静默替换选择结果。

**本阶段完成了什么：**

- 增加 `configs/formal_series_selection_rule_b_v1.json`。
- 增加系列人工复核准备和决定校验脚本。
- 增加对应测试。
- 更新 `.gitignore` 和 README 的协议说明。

**主要技术变化：**

数据整理开始具有明确的协议版本和人工审查边界，为后续 FrozenBaseline 研究结果提供输入治理基础。

**过程中遇到的问题：**

Git 中没有保留一份完整的逐项人工讨论记录，因此不能还原每个系列选择决定的实际讨论过程。

**如何解决：**

以协议文件、脚本和测试作为可追溯证据；缺失的讨论过程标记为历史资料不足。

**验收结果：**

提交中包含对应测试文件，但本阶段没有独立在线系统验收。

**本阶段留下的技术债和后续问题：**

协议冻结不等于科研结果或临床有效性通过。后续仍需独立数据、结果冻结和审计。

**阶段总结：**

项目开始把“选择哪些影像进入实验”变成有版本、有输入输出的工程协议。

**证据来源：**

- `db100c250d13f8cc3c53b315ca39c6d9f8d80c98`
- `configs/formal_series_selection_rule_b_v1.json`
- `scripts/prepare_series_manual_review.py`
- `scripts/validate_manual_series_decisions.py`
- `tests/test_manual_series_decisions.py`

## 阶段三：Gradio Mock 原型

**时间：** 2026-09-23；使用 Commit 时间归档。

**对应分支：** `origin/feat/gradio-demo-p0`。

**关键 Commit：** `f153b9b5c15ffb8de86415fdbf38ac5cf0386248`

**当时项目处于什么状态：**

项目已有离线算法工作区，但还没有一个能让团队快速查看任务状态和结果格式的轻量服务。

**本阶段为什么要做：**

先用 Mock 推理建立 API、Job、存储和 Gradio 页面形态，为后续真实 DICOM 接入提供可替换的服务外壳。

**本阶段完成了什么：**

- FastAPI/Gradio 本地服务。
- PNG/JPG Mock 分类入口。
- SQLite Job 和结果存储。
- 合同、任务、存储和 Mock inference 测试。

**主要技术变化：**

算法调用与界面、任务状态、结果存储开始分层。此时结果来源是 `MOCK`，不能视为真实冻结模型推理。

**过程中遇到的问题：**

该分支不是 `p0/integration` 的祖先，后续集成提交采用了其服务思路并重新引入相关文件。因此不能把该分支直接描述成已合并的历史提交。

**如何解决：**

后续 P0 真实接入在新的集成线上重新实现和验证，并保留 `MOCK` 与 `LIVE_CASE` 的来源区分。

**验收结果：**

该分支有本地服务和测试文件；没有证据表明它已经完成真实 DICOM 或临床部署验收。

**本阶段留下的技术债和后续问题：**

真实算法、DICOM 几何、对象权限、用户认证、生产存储和多切片能力均未解决。

**阶段总结：**

Mock 原型让团队先验证了服务交互，但它只是工程外壳，不是算法结果验证。

**证据来源：**

- `f153b9b5c15ffb8de86415fdbf38ac5cf0386248`
- `gradio_service/README_WINDOWS.md`
- `gradio_service/gradio_debug/`
- `gradio_service/tests/`

## 阶段四：人工复核服务与展示站

**时间：** 2026-09-25；使用 Commit 时间归档。

**对应分支：** `main` 及其后续祖先。

**关键 Commit：**

- `65d1861d8776c06038472c576f453a7b90256fa2`：人工复核服务。
- `14c114ab26226561615315f7d3d25e42fcec64cc`：独立项目展示站。

**当时项目处于什么状态：**

项目需要人工系列复核、项目说明和后续受控入口，但这些能力与在线 FrozenBaseline 推理不是同一条服务链。

**本阶段为什么要做：**

为已有人工审查流程和对外项目介绍提供独立服务边界，避免把展示站或复核工具直接当作算法 API。

**本阶段完成了什么：**

- `epilocate_review_server/`：账户、复核页面、SQLite、导出和部署配置。
- `aid_site/`：项目概览、进度、系统说明和展示页面。

**主要技术变化：**

项目出现了人工复核、项目展示和算法服务三个不同用途的组件。

**过程中遇到的问题：**

现有记录没有提供完整的部署操作时间线和所有运营过程，因此只记录代码和部署文档中能确认的内容。

**如何解决：**

后续 P0 集成保留这些组件的独立目录和职责，不让展示站代理真实影像推理。

**验收结果：**

人工复核服务有独立测试和部署 README；这些证据不等于 P0/P1 在线推理验收。

**本阶段留下的技术债和后续问题：**

展示站、人工复核服务和 Backend v2 的身份、数据和部署边界仍需分别维护。

**阶段总结：**

这一阶段补齐了项目周边工具，但没有改变核心算法或在线推理架构。

**证据来源：**

- `65d1861d8776c06038472c576f453a7b90256fa2`
- `14c114ab26226561615315f7d3d25e42fcec64cc`
- `epilocate_review_server/README_DEPLOY.md`
- `aid_site/README.md`

## 阶段五：Stage 1 FrozenBaseline 科研验证（并行研究分支）

**时间：** 2026-09-25/26；提交时间作为归档依据。

**对应分支：** `research/stage1-validation-backup`，当前 HEAD 为 `f59738a606d15ff7062bbc64fc316ba276035ce4`。

**关键 Commit：**

- `e81480d5e186905870e8e60cd5db7993706720ae`
- `f59738a606d15ff7062bbc64fc316ba276035ce4`

**当时项目处于什么状态：**

科研验证产物已经形成冻结交付，但这些产物位于从 `65d1861d...` 分出的并行研究分支，不是 `p0/integration` 的祖先。

**本阶段为什么要做：**

为 FrozenBaseline、Stage 1 遮挡协议和正式 validation 结果建立可复核的冻结边界，并把科研结果与在线服务输入分开。

**本阶段完成了什么：**

- `FORMAL-BL-R18-V1` 结果冻结材料。
- `result_freeze.json`、`independent_qa_report.json`、运行清单和 provenance。
- 28 名患者、5,637 个切片的独立 QA 证据。
- 探索性跨尺度分析报告。

**主要技术变化：**

科研产物开始具有冻结状态、哈希和 sealed-test 边界。在线服务后来只读取必要的冻结模型和协议，不把 validation 统计当成在线病例结果。

**过程中遇到的问题：**

并行研究分支没有合并进入当前 P1 集成线，且完整运行会话日志没有全部保存在仓库中。

**如何解决：**

通过分支、冻结 JSON、独立 QA 报告和哈希清单保留可审计证据；本文不把它改写成 `p0/integration` 已有文件。

**验收结果：**

- `result_freeze.json`：`source_freeze_status=FROZEN`。
- `independent_qa_report.json`：`status=PASS`。
- `test_pixels_read=false`。
- `patient_identifiers_sanitized=true`。

**本阶段留下的技术债和后续问题：**

候选区域仍是遮挡响应假设，不是病灶真值。探索性统计不构成临床定位准确性结论。

**阶段总结：**

该阶段建立了科研结果的冻结和可追溯边界，但它和工程集成分支是并行关系，不能混写。

**证据来源：**

- `analysis/stage1_validation_exploratory_v1/report.md`
- `deliverables/stage1_materials_2026-09-25/result_freeze.json`
- `deliverables/stage1_materials_2026-09-25/independent_qa_report.json`
- `docs/formal_baseline_protocol_rule_b_v1.md`

## 阶段六：P0 真实单切片算法接入

**时间：** 2026-09-26；使用 Commit 时间归档。

**对应分支：** `codex/p0-real-algorithm`。

**关键 Commit：**

- `34edd02637fd4d5a54fed37dd926229e43c5b69a`
- `3b3c270869663293769f99ab3cbc180904185a1f`

**当时项目处于什么状态：**

Gradio Mock 服务已经提供任务和结果外壳，但真实 DICOM、冻结模型和遮挡协议尚未接入在线 API。

**本阶段为什么要做：**

让真实单切片 DICOM 经过 HTTP 和 Gradio 调用同一个 FrozenBaseline，同时保留旧 Mock 入口的兼容性。

**本阶段完成了什么：**

- `algorithm/service.py` 适配 FrozenBaseline。
- `/api/v1/cases`、预测、遮挡、Job、Result、位置分页和资产读取。
- 16/32/64 px 遮挡和 224×224 响应图。
- 合成 DICOM fixture、HTTP 向量和真实集成测试。
- checkpoint、协议和配置哈希核验。

**主要技术变化：**

系统从 PNG/JPG Mock 扩展到单切片 DICOM 真实流程，但仍是 loopback 本机原型。算法服务读取冻结内容，不修改训练代码或科研冻结产物。

**过程中遇到的问题：**

报告记录了本机代理变量导致的 `httpx.InvalidURL: Invalid port ':1'`，以及真实 API、Gradio、空间仿射和冻结目录写入保护等联调边界。

**如何解决：**

本机测试清理代理变量并设置 `NO_PROXY/no_proxy=127.0.0.1,localhost`；以独立数据目录运行服务；加入真实 API、空间、幂等和冻结保护测试。

**验收结果：**

`docs/interfaces/p0_verification_record.md` 记录 21 passed；真实 HTTP 与 Gradio 均返回 `LIVE_CASE`，概率 `0.025618407875299454`，遮挡位置为 729/169/36，原图预览 112×80，热图 224×224。

**本阶段留下的技术债和后续问题：**

只支持单切片；NIfTI、多切片、患者级汇总、Robust、LIME、医生反馈、外网授权和完整 DICOM 去标识尚未完成。

**阶段总结：**

P0 首次形成了“上传匿名单切片 → FrozenBaseline 预测/遮挡 → 查询结果”的真实工程闭环，但仍不是生产系统。

**证据来源：**

- `docs/interfaces/p0_real_integration.md`
- `docs/interfaces/p0_verification_record.md`
- `docs/interfaces/algorithm_api_contract.yaml`
- 上述两个关键 Commit

## 阶段七：P0 Frontend、Backend 和独立 QA

**时间：** 2026-09-26；提交时间作为归档依据。

**对应分支：** `feat/p0-frontend-real`、`feat/p0-backend-real`、`test/p0-real-qa`。

**关键 Commit：**

- Frontend：`93d2e8f013d64979972bc88e7cbdba71007ca6b7`
- Backend：`3b400c39437ec6685b5f056fb039f9dcfe0bedb6`
- Backend 报告：`3aabb79803b318229740ec899c1eca524b1c1184`
- QA：`7366dd3cf4dbc030864c230817ba52604e348cdf`

**当时项目处于什么状态：**

P0 真实 API 已存在，但前端展示、任务边界、资产授权和独立回归还需要分角色完成。

**本阶段为什么要做：**

把真实 API 接入 DICOM 页面，补齐 Job/资产边界，并让独立 QA 检查错误、权限、刷新和冻结保护。

**本阶段完成了什么：**

- Gradio 真实 DICOM 页面和服务端 API client。
- 真实分类、遮挡、位置分页、刷新恢复和 `MOCK`/`LIVE_CASE` 分离。
- Job 取消、幂等、失败脱敏和资产归属校验。
- HTTP 探针、浏览器 QA、冻结产物前后哈希检查。

**主要技术变化：**

P0 从单纯 API 接入变成了前端、后端、算法和 QA 分工的集成流程。真实页面仍然是单用户、本机原型。

**过程中遇到的问题：**

统一集成报告记录了 Token 模式下普通浏览器无法直接给后端 Gradio 导航附加 Bearer、文件路由不能泄露结果目录以及无 Token loopback 边界等问题。

**如何解决：**

新增独立本机 `ui_server.py`，由服务端保存 Bearer 并调用 API；限制 Gradio `allowed_paths`；保留失败不自动 Mock 回退的语义。

**验收结果：**

- 固定 P0 集成提交：`021e4f56103e53c82b5abf76465f62fb4f1bc6c3`。
- 标签：`v0.1.0-p0-release`。
- 统一测试：82 passed，7 warnings。
- 独立 QA 分支在该固定提交上报告 `EPILOCATE P0 REAL INTEGRATION QA PASSED`。

**本阶段留下的技术债和后续问题：**

无对象级多用户授权、无公网部署、只支持单切片，服务重启恢复、正式 validation inference、Robust、LIME、Grad-CAM 和临床有效性仍未完成。

**阶段总结：**

P0 形成了可独立复验的本机真实单切片闭环，并把 Mock、真实病例和冻结科研结果分开。

**证据来源：**

- `docs/interfaces/p0_frontend_integration_report.md`
- `docs/interfaces/p0_backend_integration_report.md`
- `docs/interfaces/p0_unified_integration_report.md`
- 独立 QA 分支中的 `qa/final_p0_integration_qa_report.md`

## 阶段八：Backend v2、Worker v1 和 Vue Frontend v1

**时间：** 2026-09-26/27；使用提交时间归档。

**对应分支：** `feature/backend-v2`、`feature/worker-v1`、`feature/frontend-v1`。

**关键 Commit：**

- Backend Phase 1：`385cab52389a58f1c8493b452f663487ca2e7c0a`
- Worker 初版：`24d4fbf8674ce4f34070daebe006ea31ab13f647`
- Backend/Worker 接入：`5df1e05635bccbc872e7b697baf73957e96b4842`
- Vue Phase 1：`8a7952a1b0819e3db1630c3c486cf5544ef6a99a`
- Worker 恢复：`1f90321b7b6af9e2a69992c4259fd2dcf32944ed`
- Vue Phase 2：`345b336e8ed9698b79369451a39cecd2842913fe`
- 三个 Phase 2 合并：`281c51195033986c708855f7e385a96fde6f11e4`、`9b0d9b21c75fbe6f2d731b5d9dc9c5e2f915ba57`、`50be7235e516495bf56b250f429f73162e831272`

**当时项目处于什么状态：**

P0 可以在本机完成真实单切片流程，但 API、任务执行和前端仍在同一个原型边界内，缺少云端任务编排、Worker 租约和结构化 Viewer。

**本阶段为什么要做：**

为后续多组件部署建立 Backend v2、Worker v1 和 Vue 前端的职责边界，同时保留 P0 兼容入口。

**本阶段完成了什么：**

- Backend v2 FastAPI、Alembic schema、Case/Job/Result 服务。
- Worker v1 注册、heartbeat、claim、lease、结果提交和恢复逻辑。
- Vue Dashboard、Case/Job/Result 页面和 Cornerstone 单切片 Viewer。
- Backend/Worker 结果资产保留和前端 API 集成。

**主要技术变化：**

任务执行从 P0 本地线程扩展到 Backend 控制面与 Worker 执行面；结果从本地 SQLite/文件边界转向结构化 PostgreSQL/对象存储契约；前端从 Gradio 页面扩展为 Vue 路由和 Viewer。

**过程中遇到的问题：**

报告记录了 Worker 结果协议、Job 状态、Case/Slice 归属、刷新恢复和 P0/P1 契约兼容问题。仅凭 Commit message 无法补出完整排查过程。

**如何解决：**

通过冻结的 Backend API、数据库和 Worker protocol 文档，增加集成测试，并在 Phase 2 合并后重新验证真实 CPU 流程。

**验收结果：**

这些分支分别有单元、集成和浏览器证据；进入 `p0/integration` 的能力以对应合并提交和后续 QA 为准，不能把分支早期状态写成基线能力。

**本阶段留下的技术债和后续问题：**

生产部署、认证、真实 PostgreSQL/MinIO、GPU、普适空间变换和公网运维尚未完成。

**阶段总结：**

项目从单体本机原型开始变成了 Backend、Worker 和 Vue 前端协作的系统骨架。

**证据来源：**

- `backend_v2/README.md`
- `worker/README.md`
- `frontend/README.md`
- `docs/backend/backend_api_contract_v2_freeze.md`
- `docs/backend/worker_protocol_v1_freeze.md`
- `docs/backend/database_schema_freeze_v1.md`
- 上述关键 Commit

## 阶段九：Backend 生产型存储与 P1 Phase 2.5 安全

**时间：** 2026-09-27；使用提交时间归档。

**对应分支：** `feature/backend-v2`、`feature/p1-auth-security`、`codex/p1-phase25-integration-qa`。

**关键 Commit：**

- 生产型基础：`addec90d221c426bb9d22bae47b067295af8ec17`
- Backend 兼容修正：`fbd3c5802fef23df2d1ef66257c323910d383518`
- Backend 合并：`91528fc07617d753d3582ab7d93ad617dbc7ad94`
- Auth：`df50656237e2ed63f7b6f7612dc290fdd395bde0`
- Phase 2.5 QA：`c9a5cc6373ffc889725971e3cae5bc09252790bd`

**当时项目处于什么状态：**

Backend v2 和 Worker v1 已有协议与本地测试，但还缺少生产型数据库/对象存储的回环验证以及用户、Worker、资产之间的认证和所有权边界。

**本阶段为什么要做：**

使 Case、Job、Result、Asset 和凭据拥有持久化约束，并验证真实 Worker 不会越权读取其他用户的资源。

**本阶段完成了什么：**

- PostgreSQL Alembic migration 和 Result/Asset metadata。
- 私有 MinIO round-trip、对象哈希、删除和签名 URL 验证。
- 用户 Bearer credential、过期/撤销和 Worker credential 分离。
- 所有权、匿名访问和跨用户访问矩阵。
- TLS Backend + PostgreSQL + MinIO + Worker E2E。

**主要技术变化：**

系统从 P0 本地 SQLite/文件原型进入生产型本地栈，但这是 local production-like evidence，不是公网生产部署。

**过程中遇到的问题：**

Phase 2.5 报告记录了迁移兼容、权限边界、TLS Worker、私有 MinIO 和前端代理之间的联调要求。

**如何解决：**

通过独立数据库、私有 bucket、服务端凭据代理和资源归属校验完成本地验证。

**验收结果：**

`docs/backend/p1_phase25_integration_qa.md` 记录完整 Python suite 119 passed，Backend/Worker suite 37 passed，Frontend 21 passed，生产型 PostgreSQL/MinIO 和真实 Worker 证据通过。

**本阶段留下的技术债和后续问题：**

没有公网生产部署、临床有效性、GPU 验收或普适的 Heatmap–CT 空间合同。

**阶段总结：**

项目获得了受控用户、Worker、数据库和私有对象存储的工程边界，但仍停留在隔离本地验证。

**证据来源：**

- `docs/backend/p1_phase25_integration_qa.md`
- `docs/backend/auth_security_foundation_v1.md`
- `docs/backend/security_gap_report_p1_phase2.md`
- `qa/evidence/p1_phase25/`

## 阶段十：P1 Phase 3/3.5 Worker 设备与 CPU 回归

**时间：** 2026-09-27；使用提交时间归档。

**对应分支：** `feature/p1-gpu-worker`、`codex/p1-phase35-integration`。

**关键 Commit：**

- `396d188b6184ec08ce6b71e5f5b1dab7206dc00b`
- `fd0e55ff52c20b58858e7ad26ff850e54bcd8a6d`
- `02c8ef9c86d2b4aa338a38142bee25ee2234dc34`

**当时项目处于什么状态：**

Worker 已能在 CPU 上完成真实冻结模型任务，但设备选择、CUDA 不可用行为、数值一致性门槛和 OOM/租约恢复还没有统一记录。

**本阶段为什么要做：**

建立 CPU/CUDA/AUTO 设备门控和未来 CPU/GPU 比较标准，同时确保没有 CUDA 时不静默回退或虚报 GPU 成功。

**本阶段完成了什么：**

- 显式 CPU/CUDA/AUTO 设备选择。
- CUDA 不可用和 OOM 的明确失败路径。
- CPU reference、benchmark 和数值比较工具。
- Worker heartbeat、重连、租约、结果上传回归。
- P1 Phase 3.5 本地 CPU stack QA。

**主要技术变化：**

设备能力成为 Worker 的显式运行时状态；CPU reference 成为未来 GPU 验收的固定比较基准。

**过程中遇到的问题：**

当前 Apple Silicon 主机没有 NVIDIA GPU，PyTorch CUDA runtime 为 `None`，因此无法运行实际 CUDA inference、GPU benchmark 或 GPU E2E。

**如何解决：**

在代码中显式拒绝不可用 CUDA，在报告中分开记录 Implemented、CPU validated、GPU validated 和 Production validated。

**验收结果：**

- Worker：29 passed。
- Backend：16 passed。
- Frontend：21 passed，并通过生产构建。
- PostgreSQL/MinIO：通过隔离验证。
- CPU Prediction/Occlusion E2E：`COMPLETED`、`LIVE_CASE`、9 个资产、729/169/36。
- GPU numerical validation、GPU benchmark、GPU E2E：未执行。

**本阶段留下的技术债和后续问题：**

需要实际 NVIDIA/CUDA 主机完成 GPU 数值、性能、长任务 heartbeat、OOM、重连和部署验收。

**阶段总结：**

本阶段证明了 CPU Worker 的集成回归和 GPU 失败边界，但没有证明 GPU 已经验收。

**证据来源：**

- `docs/worker/p1_gpu_worker_phase3_report.md`
- `docs/worker/p1_gpu_capability_compatibility_report.md`
- `docs/worker/p1_phase35_integration_qa.md`
- `docs/worker/p1_phase35_cpu_reference_regression.json`
- `docs/worker/p1_phase35_cpu_stack_e2e.json`

## 阶段十一：P1 Phase 4/4.5 Heatmap–CT Integration

**时间：** 2026-09-27 至 2026-09-28；最终报告提交时间作为归档依据。

**对应分支：** `feature/p1-heatmap-ct-fusion`、`integration/p1-phase45-heatmap-ct`、`p0/integration`。

**关键 Commit：**

- Frontend fusion：`77ef944ec88db6992a16b395a13434d7065f4186`
- Integration merge：`580b58ed2b5933c32198165e71be91198e2224de`
- Final acceptance report：`b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5`

**当时项目处于什么状态：**

P1 Phase 3.5 已能在本地 CPU stack 生成真实结果和热图，但前端需要把热图安全地显示在 Cornerstone CT 上，并在刷新、缩放、平移和不同尺度之间保持状态。

**本阶段为什么要做：**

解决当前冻结预处理下的 2D 像素空间显示对齐问题，同时拒绝缺少来源、尺寸、哈希或坐标信息的结果进入 overlay。

**本阶段完成了什么：**

- Cornerstone CT 与独立 overlay canvas。
- 16/32/64 px 响应、候选和 14×14 comparison layer。
- raw-to-model edge mapping 和 viewport transform 校验。
- 缩放、平移、resize、刷新恢复。
- 真实 CPU Worker、PostgreSQL、MinIO、Backend、Vue 浏览器联调。

**主要技术变化：**

前端从独立热图显示发展为受合同门控的 CT overlay。当前 API 没有通用 immutable `spatial_transform`，因此只允许审计过的精确版本和输入 SHA 通过 overlay gate。

**过程中遇到的问题：**

浏览器检查发现 Cornerstone 独立 `imageToWorldCoords` 在不等 PixelSpacing 和旋转 fixture 下与实际 StackViewport 渲染不一致。

**如何解决：**

改用渲染 viewport 的 `imageData.indexToWorld` 和 `worldToCanvas`，并在 camera/resize 事件后重新计算四角 affine；不满足合同则保留独立热图但关闭 overlay。

**验收结果：**

- Frontend：32 tests passed，build passed。
- Backend：16 tests passed。
- Worker：29 tests passed。
- PostgreSQL/MinIO round-trip passed。
- Real CPU Prediction/Occlusion：`COMPLETED`、`LIVE_CASE`。
- 9 个 Heatmap assets；位置 729/169/36。
- 浏览器显示、刷新恢复、所有权和匿名访问检查通过。

**本阶段留下的技术债和后续问题：**

- 未完成 GPU/CUDA 验收。
- 未完成公网生产部署。
- 未建立通用 immutable raw-to-model transform contract。
- 只验证当前单切片 2D 像素空间，不代表 3D 配准。
- 不构成临床有效性、病灶定位或诊断效果证明。

**阶段总结：**

截至 `b069a8ce...`，EpiLocate 已形成经过本地真实 CPU 闭环验证的 Backend、Worker、Vue、PostgreSQL、MinIO 和 CT overlay 集成基线，但仍有明确的 GPU、生产、3D 和临床边界。

**证据来源：**

- `docs/frontend/heatmap_ct_geometry_contract.md`
- `docs/frontend/p1_phase4_fusion_report.md`
- `docs/frontend/p1_phase45_integration_acceptance.md`
- `docs/worker/p1_phase35_cpu_stack_e2e.json`
- `docs/backend/p1_phase25_integration_qa.md`

## 阶段十二：Phase 5 多人入口、本地 CPU 链路与远程 GPU 准备

**时间：** 2026-09-28；Git/报告归档日期，不能据此还原完整开发日程。

**对应分支 / Worktree：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`。该分支从 `p0/integration` 的 `b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5` 开始，未并入该集成分支。

**关键 Commit：**

- `639bfec38283728b54b0b6ce7961df10ea9ec535`：Session Gateway，多用户浏览器会话入口。
- `b07cfaefdeec4b382f530a8a22751b0ad8bafcfa`、`e74f98432019eb46691e085b957fecb8e23ca1a3`：独立 CPU Worker 本地真实链路及 Stage 2 验收报告。
- `e3418783f669be0dc69060b55b42d4e7bad27365`、`7babd923c1d40d67c7abe4c0a0d957c60b8d4d0b`：ECS 部署准备与只读审计。
- `15d7b67b019df0dbf16afa93e447bde7b6d58b29`：远程 GPU 节点配置模板、预检和候选传输设计；是后续 GPU MVP 的直接父提交。

**架构决策与实现：** 浏览器经 Session Gateway 获取服务端会话；Gateway 在服务端管理各用户 Backend 凭据，Backend 继续处理 Case、Job、Result 和 Asset，独立 Worker 执行模型。Stage 2 在 macOS 本地以真实 CPU Worker、PostgreSQL、MinIO、HTTPS 与 Vue 浏览器完成双账户、Prediction/Occlusion 和刷新流程。Worker 的 `CPU`、`CUDA`、`AUTO` 选择及 Register/Heartbeat/Claim/Submit 协议继续保留。长期方向仍是 Cloud Control Plane + Worker Agent / AI Node，而非把模型搬入 Backend 请求处理器。

**验证与边界：** Stage 2 报告记录 Gateway/Backend 21 passed、Worker 29 passed、Frontend 36 passed 及构建通过；CPU `LIVE_CASE` 生成 729/169/36 个位置和 9 个热图。Stage 3B 在负责人授权下只读确认 ECS 系统、约 2 vCPU/3.5 GiB 内存、旧 Review Server 与 TLS/Nginx 等现场状态；当时未部署新 Control Plane。GPU 准备报告记录负责人提供的矩池云 RTX 3090、驱动及 PyTorch CUDA 基础能力核验，但 `15d7b67...` 时尚未运行 FrozenBaseline CUDA、跨云 Worker E2E 或 ECS 部署。该报告的 SSH 本地转发仅是候选拓扑，不能写成最终已部署方式。

**后续问题：** ECS 与 GPU 的真实部署、数值比较、持久化和浏览器远程验收需另行执行。原本计划的本地 RTX 4050 AI Node 与矩池云替代关系来自负责人本轮说明；仓库在此阶段独立验证的是矩池云 RTX 3090，未提供 RTX 4050 本机验收证据。

**证据来源：** 上述完整 Commit；`docs/phase5/stage1_browser_entry_report.md`、`docs/phase5/stage2_cpu_worker_e2e_report.md`、`docs/phase5/stage3_ecs_readiness_report.md`、`docs/phase5/remote_gpu_node_preparation.md`（均以 Phase 5 分支对应提交为准）。

## 阶段十三：Phase 5 GPU-only Full-Chain MVP

**时间：** 报告执行日期及 Git 归档日期均为 2026-09-28。

**对应分支 / Worktree：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`。直接父提交为 `15d7b67b019df0dbf16afa93e447bde7b6d58b29`。

**关键 Commit：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9`

**架构决策：** 为验证真实远程 GPU 链路，本轮在 ECS 只运行 Vue 静态站、Session Gateway、Backend v2、PostgreSQL、MinIO 和 Sweeper；没有启动 ECS CPU Worker。矩池云 RTX 3090 上的独立 Worker 通过公网 HTTPS Worker API 领取任务，通过签名 HTTPS GET 读取 DICOM，再将结果交回 Backend。新界面隔离在 `https://project.xbstu.com/mvp/` 测试入口，旧 Review Server 根入口及 `/healthz` 保留。此部署选择是**本轮 GPU-only 工程 MVP**，Worker 代码仍支持 CPU/CUDA/AUTO，不改变长期 Cloud Control Plane + Worker Agent / AI Node 架构；报告中的实际路径也不是此前候选 SSH 隧道。

**已实现、已通过测试、已部署：** RTX 3090、PyTorch `2.4.0+cu121` 上的 Worker 实际记录 `CUDA`。FrozenBaseline CUDA Prediction 与 16/32/64 px Occlusion 功能验证通过，产出 729/169/36 个位置与 9 个 Heatmap assets。指定 GPU Worker 经 ECS Backend 完成两个 `LIVE_CASE` Job（attempt 1），PostgreSQL Result/Asset 行、MinIO 中合成 DICOM 和 9/9 PNG 经重新读取及 SHA-256 核对。Playwright Chromium 通过公网 TLS 的 `/mvp/` 完成合成单切片上传、Prediction、Occlusion、三尺度与图层、CT overlay、70% 透明度、刷新恢复及登出。Frontend 36 passed、Worker 29 passed、远程预检 4 passed、Gateway/Backend 19 passed/2 skipped；`/mvp/` 构建、ShellCheck、`git diff --check` 通过。ECS 服务、Nginx 检查及旧服务健康检查由报告单独记录。该入口是工程测试部署，**不是医院正式环境或生产就绪验收**。

**明确未通过：** 固定 CPU/GPU 数值一致性门为 **FAILED / OPEN**。`comparison.passed=false`；派生数值最大绝对偏差 `0.0010498762130737305`，超过冻结容差 `0.0001`，502 个派生路径在 224 个位置上失败。基础概率差和解码 PNG 像素分别满足其对应容差，但 9 个 PNG 字节哈希不同；功能 E2E 通过不能替代数值等价。模型、checkpoint、CPU reference、算法和容差未为通过测试而修改。差异原因尚未由报告确认。

**尚未完成：** MinIO 静态加密未启用，Backend 仍使用 MinIO root 凭据；GPU Worker 运行于 `tmux`，缺少自动崩溃重启；异地独立备份与隔离恢复演练未完成。还未证明多用户吞吐、GPU 实例释放后的持久性、峰值资源或临床有效性。只验证合成单切片，未证明病灶真值、3D 配准或正式生产可用。`4d717a...` 未并入 `p0/integration`；“已部署”仅指该分支代码对应的本轮 ECS/GPU 测试栈，不代表集成基线已部署。

**证据来源：** `4d717a3753ef307ab370adeafaf5a00da4dc7af9` 的 `docs/phase5/gpu_full_chain_mvp_report.md`、`docs/phase5/evidence/gpu_mvp/gpu-benchmark-summary.json`、Vue 与 `deploy/mvp/` 变更、报告列出的服务/持久化/浏览器核验。

## 架构演变总览

### 1. 离线研究基础

`src/` 和 `scripts/` 负责 DICOM、患者划分、预处理、训练和离线遮挡。科研冻结材料保留自己的哈希和 sealed-test 边界。

### 2. P0 本机算法服务

Gradio/FastAPI 先以 `MOCK` 建立交互，再通过 `algorithm/service.py` 接入 FrozenBaseline。P0 的真实入口只支持匿名单切片和 loopback，本机 UI 与 API 的凭据边界后来单独加固。

### 3. Backend v2 与 Worker

Backend v2 负责用户、Case、Job、Result、Asset 和调度；Worker v1 负责领取任务、读取临时输入、运行冻结模型、提交结果和清理缓存。两者通过冻结的 API/Worker protocol 连接。

### 4. PostgreSQL 与 MinIO

PostgreSQL 提供结构化实体、外键、状态和幂等约束；MinIO 保存私有结果对象。当前证据是隔离本地 production-like stack，不是生产部署证明。

### 5. Vue 与 Cornerstone Viewer

Vue Frontend 负责 Case/Job/Result 工作流，Cornerstone 负责 CT 渲染，overlay canvas 负责模型响应显示。overlay 只在来源、输入哈希、尺寸、图层语义和 viewport 变换全部满足条件时启用。

### 6. Phase 5 分支的 Cloud Control Plane 与 AI Node

Session Gateway 在浏览器与 Backend v2 之间提供服务端会话；Backend、PostgreSQL、MinIO 和 Sweeper 构成 ECS Control Plane，独立 Worker 运行冻结模型。Phase 5 开发分支先用本地 CPU Worker 验证双账户完整链路，随后以矩池云 RTX 3090 Worker 验证远程 GPU-only MVP。CPU/CUDA/AUTO Worker 选择仍在代码中；ECS 没有运行 CPU Worker 是本轮部署选择。数值一致性、生产加固及并入 `p0/integration` 仍是独立门槛。

## 截至 Phase 4.5 基线的能力边界矩阵

| 能力 | Phase 4.5 基线状态 | 证据边界 |
| --- | --- | --- |
| FrozenBaseline 单切片 CPU 推理 | 已实现、已测试、已完成本地集成 | synthetic/匿名输入和冻结 hash；不是临床验证 |
| 16/32/64 px 遮挡 | 已实现、已测试、已完成本地集成 | 位置 729/169/36；候选是响应假设 |
| Backend v2 Job/Result/Asset | 已实现、已测试、已完成本地集成 | 本地 PostgreSQL/MinIO；非公网生产 |
| Worker v1 轮询、租约、结果上传 | 已实现、已测试 | CPU stack 真实 E2E；长时生产行为仍需部署验证 |
| 用户认证和对象所有权 | 已实现、已测试 | 本地凭据、TLS 和 HTTP 矩阵；非完整生产身份系统 |
| Vue CT overlay | 已实现、已测试、已完成 Phase 4.5 集成 | 当前 2D 像素合同；非 3D registration |
| GPU/CUDA inference | 尚未完成 | 当前主机无 NVIDIA/CUDA，未执行 GPU 验收 |
| 公网生产部署 | 尚未完成 | 临时本地容器和自签名 TLS 不构成生产证据 |
| 临床有效性和病灶定位 | 尚未建立 | 候选响应不是病灶真值；无临床结论 |
| 通用 spatial transform | 尚未完成 | 当前使用精确版本 allowlist 和输入 SHA gate |
| 多切片、NIfTI、患者级汇总、Robust、LIME、医生反馈 | 尚未完成 | 报告明确列为 planned/unavailable |

## 历史资料不足与更正规则

### 已确认的资料不足

- Git 提交时间不能证明完整实际开发日期。
- Commit message 不能证明执行者、问题排查过程或测试过程。
- 并行研究分支的结果没有自动成为 `p0/integration` 能力。
- 可达历史之外发现了重复的早期根 Commit 和混合资料根 Commit，但没有分支引用，不能作为当前项目正式阶段依据。

### 后续更正

发现历史错误时追加“更正记录”，注明原记录、修改依据、涉及 Commit/报告和日期；不悄悄改写已确认事实。

## Phase 5 状态及后续记录

截至 Phase 5 开发分支 `4d717a3753ef307ab370adeafaf5a00da4dc7af9`：多人入口、本地 CPU E2E 与远程 GPU 功能链路均有分支级实现及指定测试；GPU-only MVP 测试栈已部署在 ECS 和矩池云节点，CPU/GPU 固定数值一致性仍为 **FAILED / OPEN**。这些成果尚未完成 `p0/integration` 集成，也未完成生产加固或临床验收。上方 Phase 4.5 矩阵保留其原始基线含义，不因后续分支验证而回写。未来阶段仍需依据真实分支、完整 Commit、报告和实现增量追加，并同步更新工程日志。

## 阶段十四：Phase 5 GPU MVP 最终交接与复验

**时间：** 最终交接报告执行时间为 2026-09-28 22:50–23:05（Asia/Shanghai）；Git 归档提交为 `352152ce95fc26eb2dc0a4c309521d50486472ba`。

**分支 / Worktree：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`。交接报告从 `4d717a3753ef307ab370adeafaf5a00da4dc7af9` 开始，未合并或推送。

**阶段结论：** GPU-only Full-Chain Engineering MVP 功能 **PASS**：Vue 浏览器、Session Gateway、Backend v2、PostgreSQL、MinIO、Sweeper 与矩池云 RTX 3090 Worker 完成一次新的合成 DICOM 浏览器及远程 GPU Worker 验收。Prediction、16/32/64 Occlusion、9 个 Heatmap assets、729/169/36 positions、结果展示和刷新恢复通过；PostgreSQL/MinIO 对象重读和哈希核对通过。ECS CPU Worker 本轮未启动，代码仍保留 CPU/CUDA/AUTO 设备路径。

**状态边界：** 这是该次测试的 Engineering MVP 验收，不是 Production Ready、Clinical Ready 或正式医疗系统验收。固定 CPU/GPU 数值一致性继续 **FAIL / OPEN**，派生数值最大偏差 `0.0010498762130737305` 超出 `0.0001`。报告中的 HTTP 200 和服务 active 是 2026-09-28 某次复核结果，不能证明之后持续在线。

**证据：** `352152ce95fc26eb2dc0a4c309521d50486472ba` 的 `docs/phase5/gpu_final_handoff_report.md`、`docs/phase5/gpu_worker_mvp_operations.md`、`docs/phase5/evidence/gpu_final/browser-e2e-summary.json` 与 `persistence-audit.json`。Phase 5 开发分支，非 `p0/integration`。

## 阶段十五：GPU JPEG Lossless Job 事故与恢复

**时间：** 报告记录审计/恢复时间为 2026-09-29 09:50–10:08（Asia/Shanghai）；报告提交 `f80d4cf406689cd031f993090783e281db93c4ef`。

**分支 / Worktree：** `codex/p1-phase5-dual-mode-server-demo`；`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`；起点 HEAD `352152ce95fc26eb2dc0a4c309521d50486472ba`。该提交仅添加事故报告、脱敏证据和运维文档更新，没有应用源码变更。

**事故与根因：** JPEG Lossless Transfer Syntax `1.2.840.10008.1.2.4.70` 的 PixelData 在 GPU Worker Python 环境无法解码。原 MinIO 对象的签名 HTTPS 下载和 SHA-256 一致；GPU 环境的 pydicom `pixel_array` 明确报告缺少 JPEG Lossless 解码插件。分类为 E（DICOM 像素解析）+ J（GPU 运行环境依赖缺失）。`requirements.txt` 已列出对应解码依赖，但实际 GPU 环境未安装。Backend READY 仅检查 DICOM header，并不能证明 Worker 能解码 PixelData。

**历史与修复后状态：** 两笔历史 Prediction/Occlusion Job 保持 **FAILED**、无 Result；未由新任务改写。GPU 节点补装 `pylibjpeg==2.1.0` 与 `pylibjpeg-libjpeg==2.4.0` 后重启同一 RTX 3090 CUDA Worker。FrozenBaseline、checkpoint、PyTorch、NumPy、Worker/API 协议和容差均未修改；ECS CPU Worker 未启动。受限调查证据不包含在本快照中。

**修复后验收：** 当时的新建 Prediction/Occlusion Job 与合成 fixture 任务均 `COMPLETED`。两轮使用 RTX 3090 / CUDA，重读 PostgreSQL/MinIO 并核对 9/9 Heatmap assets 与 729/169/36 positions；浏览器结果与刷新恢复通过。以上是该次复验结果，不代表当前线上持续可用。

**证据与后续：** 本快照中的 `docs/phase5/gpu_failed_job_incident_20260929.md` 仅保留机制说明。受限调查证据留在内部历史；本快照有独立 Git root。继续开放：Frontend 失败态 UX、Worker 错误上下文/traceback、安全的解码预检和可复现 GPU runtime 环境。CPU/GPU 数值一致性仍为 FAIL / OPEN。

## 阶段十七：交接候选本地收束

**时间：** 2026-09-29；**内部候选：** `d498f0465f6b7d0e4d999562658356a734211bfa`，由 `f80d4cf406689cd031f993090783e281db93c4ef` 派生；**公开交接分支：** `handoff/pre-b-transfer-20260929`，从审计文件树建立独立 Git root。两者用途及历史不同，见 `docs/handoff/SOURCE_PROVENANCE.md`。

**实际修改：** 合入 Engineering/Consolidation/Backend API 文档；逐路径导入 Landing 至 `apps/landing/` 并把入口指向同源 `/mvp/`；加入 GPU Worker 固定依赖清单、Git 固定提交导出与 `SOURCE_COMMIT` 机制；清理候选顶端的原病例事故 JSON 与报告细节；生成三份单独审计、清元数据的 Word 副本。

**验证边界：** Landing 与 Vue 前端本地构建和测试通过；Backend、Gateway、Worker 相关 Python 测试在本机隔离依赖环境执行。公开快照仍须通过全可达 Git objects 的 Secret / PHI 扫描、Word 全页复核、GitHub clone 回归和部署后线上验收；见 `docs/handoff/RELEASE_SECURITY_AUDIT.md`。

## 阶段十八：Sanitized Handoff 固定提交候选与 Welcome 浏览器修复

**时间：** 2026-09-29；**分支：** `handoff/pre-b-transfer-20260929`，独立 sanitized Git root；**首个公开候选：** `39440e05c99562a7a01805dd09a4955ba4933a55`。

**实际验证：** 从 GitHub 全新 clone 通过 Landing 构建、Vue 36 项测试与构建、Backend/Gateway/Worker/文档 51 passed、2 skipped、148 个本地链接检查和 `SOURCE_COMMIT` 导出匹配。ECS 从该 SHA 直接导出候选源码并在服务器构建 Landing/Vue。Welcome 首次上线后 HTTP 与静态资源为 200，Review 与 `/mvp/` 保持可达。

**发现与修复：** Playwright 浏览器发现三张缩略图经图片服务跳转至 CloudFront 后被 Welcome CSP 拦截。`deploy/mvp/nginx-welcome.conf` 的 `img-src` 加入实际跳转域名。修复提交 `649b0c665971cfefcc67509849947b2d3f7e49c7` 从 GitHub 重新导出至 ECS，服务器构建与 Nginx 检查通过；桌面、移动浏览器复核通过且控制台无错误。ECS `/welcome/`、`/mvp/`、Review root、健康端点可达，Backend/Gateway/Sweeper 运行目录和 `SOURCE_COMMIT` 指向该固定 release。最终文档提交仍需 GitHub clone 和 ECS 来源标记对齐。

## 阶段十九：GPU 节点主动释放与交接门槛分流

**时间：** 2026-09-29。负责人主动暂时释放 GPU AI Node；状态 **TEMPORARILY OFFLINE / INTENTIONALLY RELEASED**，不是新的系统故障。GPU architecture **PREVIOUSLY VALIDATED**；历史 GPU 功能 E2E PASS 保留。Final Git-based GPU E2E **PENDING GPU RE-PROVISION**。

**继续：** Sanitized Clean Snapshot、Word 全页 QA、Secret / PHI 与全可达 Git objects 扫描、指定 GitHub branch、全新 clone、Landing/Welcome、ECS Git-based candidate release、Handoff 文档，以及最终 SHA 的本地 Frontend redesign branch 准备。

**暂停：** GPU Worker deployment、GPU `SOURCE_COMMIT` validation、synthetic GPU E2E、CUDA runtime revalidation。待负责人提供新 SSH host/port，再由最终 Handoff SHA 重建 RTX 3090-class CUDA 节点并执行最终 synthetic E2E。保留 PyTorch `2.4.0+cu121`、固定 Worker 依赖、`pylibjpeg==2.1.0`、`pylibjpeg-libjpeg==2.4.0` 和核验的 FrozenBaseline checkpoint hash。ECS 不启用 CPU Worker 替代 GPU 验收；FrozenBaseline、历史 GPU PASS 和 CPU/GPU tolerance 均不改动。

## 阶段十六：工程边界确认与 Repository Consolidation Phase 0

**时间：** Git 归档日期 2026-09-29。**分支 / Worktree：** `codex/repository-consolidation-v1`；`LOCAL_WORKTREE/EpiLocate-consolidation-v1`。基线为 Phase 5 验收/文档 HEAD `352152ce95fc26eb2dc0a4c309521d50486472ba`。

**工程边界 / Canonical Source Map：** Phase 0 清单把 Landing 指向研究备份分支 `research/stage1-validation-backup` 的 `flow-fluidity/`；AI Web 指向 Phase 5 的 `frontend/`；Showcase 为 `aid_site/`；Review 为 `epilocate_review_server/`；Backend 为 `backend_v2/`；Gateway 为 `session_gateway/`；Worker 为 `worker/`；Deployment templates 为 `deploy/mvp/`。映射为迁移规划快照，不表示这些目录已合并、搬动或取代其他路径。

**Phase 0 实际完成：** `718d3220a2191aba0dd8fbfe1d673546997d1c04` 新增 `apps/README.md`、`services/README.md`、`docs/consolidation/README.md`、`SOURCE_MAP.md`、`MIGRATION_PLAN.md` 与 `archive/README.md`。仅建立规划目录说明、来源映射、迁移计划和归档清单；没有移动业务源码、修改 imports 或运行路径、改变部署/服务器或删除 Worktree。状态为 **Consolidation Preparation Completed**，不是 Repository Migration Completed。

**冻结边界和已批准后续决策：** `algorithm/`、`src/`、`scripts/`、`configs/` 的 Frozen research runtime 本阶段保留原位。负责人已确定未来 `develop` 应代表 Engineering MVP 主线，但当前仍需收敛验收后才可推进；本轮只读核验时 `develop` Worktree HEAD 仍是 `021e4f56103e53c82b5abf76465f62fb4f1bc6c3`。历史 Worktree 先归档、再分批移除，不使用 force remove；Welcome Landing 本阶段只做代码接入规划，不修改生产域名、Nginx 或 Review 根入口。这些是批准的决策，不是已完成迁移或生产变更。

**证据：** `718d3220a2191aba0dd8fbfe1d673546997d1c04` 的六个新增 Markdown 文件及 `docs/consolidation/SOURCE_MAP.md`、`MIGRATION_PLAN.md`；Phase 5 来源锁定于 `352152ce95fc26eb2dc0a4c309521d50486472ba`。收敛分支是独立规划分支，尚非当前 `develop` 集成基线。

## 接口文档版本与 Frontend 交接边界

Backend API Contract 与 Frontend Integration Guide 位于独立分支 `docs/backend-api-phase5-gpu-mvp`，提交 `ab36dea60e518ae86d8b9749d876d94d2102511d`；该文档提交说明其与 Phase 5 实现对齐，Consolidation Source Map 将其记录为独立文档来源。除非未来明确合并并核验，不能把这些接口文档表述成 `p0/integration` 的实现事实。

负责人安排将把 Frontend UI 重构交给陈奕冰，当前 Canonical Source 为 Phase 5 `frontend/`。交接范围是 Login、Case UI、Job UI、Viewer、Heatmap/Overlay、Router、Pinia 和 Frontend tests；不包括 Landing、Showcase、Review、Backend、Gateway、Worker、Deployment、FrozenBaseline 或核心算法。该安排是交接边界，当前提交没有证明 UI 重构已经开始或完成。

## 当前线上可用性

截至本次文档补录可取得的最新部署证据，事故报告记录了 2026-09-29 10:08 前的服务检查与修复后 E2E；没有更晚的 Live Regression Audit 结果。因此 **CURRENT LIVE AVAILABILITY: PENDING REVALIDATION**。历史 E2E PASS 只代表对应验收时点，不推出此后持续可用。

## 阶段二十：前端第一轮稳定流程与页面审计

**日期：** 2026-10-01。**分支：** `feature/frontend-redesign-phase5`。**开发起点：** `008c81e8d0545c32f59d16890ea987f59614c87c`。本阶段为此分支的本地实现和验收，未合并、推送或部署。

**交付提交：** `0a93c7dfcb2c22070337ed20264467e4e0079716`（会话/请求隔离、错误归一化、Case/Viewer 恢复）；`8447f7b5246d8e146e176b09f872f9bd958f7a32`（Job 失败说明、Result 图层恢复）；`9dbdf6372c4b33571a47a0a99adbaa6ff2ce9d14`（本地浏览器验收工具、审计、草图）。

**实现：** 退出、401 与账号切换清空业务缓存并阻止迟到请求写回；病例切换取消影像取回并核对上传/任务响应；统一安全中文错误提示；FAILED 独立呈现，查询失败保留最近状态；影像/热图局部重试与几何门控。保持既有 API 和本轮页面布局，没有 Backend、Gateway、Worker、部署或 FrozenBaseline 变更。

**验收：** 独立本机锁定依赖安装，Node 24.19.0。原基线 36/36 测试与 build 通过；修改后 72/72、13 个 spec 文件及 TypeScript/Vite build 通过。本地 Edge 合成 API 拦截验收 13 场景通过、0 page error；实际执行 Cornerstone 解码/渲染。非方形、旋转及不同像素间距的 6 组几何测量最大误差 0.3031 CSS px。该结果不是线上账号或 GPU 推理验收。

**范围收敛：** 初次交付因用户限定仅改 frontend，根工程记录检查实际 FAIL，记录先存于 frontend/docs。用户随后授权审查所有必要目录，本次追加根日志并重新检查。保留初次 FAIL 的历史事实，不修改检查器。

**仍开放：** 真实授权账号浏览器链路与 GPU 节点恢复后的推理 E2E；下一轮视觉重构、性能/依赖评估。历史 CPU/GPU 数值一致性 FAIL / OPEN 不变。

**证据：** `frontend/docs/FIRST_ROUND_AUDIT.md`、`frontend/geometry-qa/first-round-browser.mjs`、`frontend/src/tests/`；本机交付目录 `outputs/frontend-qa/browser-acceptance.json` 及截图。线上版本先前核实为 `4e38fd32765e7c69ae0b7389cb91fe057c938472`，本次没有切换版本。

**本阶段后续审查补录：** 扩大必要目录审查后发现跨标签页身份通知和 Cornerstone 解码/自然化数据缓存释放缺口，已补修。最终 Node 24 回归 81/81（14 spec）与 build 通过；本地浏览器 15 场景、0 page error，新增双标签页及真实 image/NATURALIZED cache 卸载断言，6 组几何继续通过。根目录文档门禁与 diff 检查现 PASS。真实账号/GPU/部署边界不变，详见前端审计报告补录。

## 阶段二十一：第一轮前端独立发布

**日期 / 授权：** 2026-10-01，用户明确要求推送 GitHub 并上传服务器。
**发布应用提交：** `feature/frontend-redesign-phase5` @ `3ad9fbc0d8dba4b16585c94dd16f5375be276f98`，普通 push 与远端 SHA 核对成功。
**范围：** 新建独立 frontend-releases 固定提交目录，服务器 Node 24.21.0 锁定安装、81/81 测试及 /mvp/ build PASS；仅切换 Nginx 前端静态 root，其他控制平面保持原 release。
**发布证据：** 完整 closure 636 objects/488 blobs 无阻断发现；归档哈希核对，HTTPS 首页/入口资源字节一致；mvp 200、无Cookie身份/病例401、Welcome200、Review303。外部Edge未登录桌面/移动检查PASS，真实账号/GPU推理未执行。
**切换记录：** 初次即时校验读到旧worker首页，自动回滚；加入重载完成等待后再次激活通过，保留旧前端及配置备份。
**报告：** `frontend/docs/DEPLOYMENT_20261001.md`。后续文档提交不改变线上应用源码 SHA；第一轮代码/审计/发布完成，完整真实业务链路验收仍待账号与GPU。

## 阶段二十二：第二轮医学影像工作台视觉重构

**日期 / 分支：** 2026-10-02，feature/frontend-redesign-phase5；起点 `a97a34688d5e5057681ecdcc38340adf1be3cd05`。用户选择医学工作台优先、全页面验收后直接发布。
**实现：** Login双栏/移动单栏、中文导航与键盘恢复、真实首页病例第一页、Case分区/状态、Job关联、Result CT主区与分析侧栏/默认折叠来源、响应式容器查询。已有安全隔离和几何门控保留；无服务端/API/算法变更。
**验证：** 本机Node24.19.0，85/85测试（15spec）、build PASS；18本地合成浏览器场景、19截图、0page error，5宽度和200% CSS放大；6组新画布几何误差最大0.3222CSSpx，cache释放PASS。移动菜单跨断点inert及放大画布挤压两问题在审查中修复并复验。
**报告 / 边界：** frontend/docs/SECOND_ROUND_REPORT.md；真实账号/GPU E2E未验收。推送/服务器发布待执行后补录，不预写通过。FrozenBaseline、CPU/GPU数值和临床边界不变。

**阶段二十二发布补录：** 应用提交 `988328f53c44a1542e95707951163a14d7b9eb05` 已普通推送并部署独立前端目录；完整 closure 673 objects / 507 blobs 无阻断发现，归档 SHA256 一致。服务器 Node24.21.0，85/85 测试、15 spec及 build PASS。仅切换 Nginx frontend root，首页/2入口资源字节一致，Backend/Gateway/Sweeper/MinIO active，控制平面仍为原4e38fd release；旧前端与回滚配置保留。真实未登录桌面/手机新登录页验收 PASS，0脚本/资源错误；mvp200、身份/病例401、Welcome200。另观测 Review带斜杠307/不带斜杠401，区别于上一轮303记录，未修改或宣称该应用通过。真实账号/GPU E2E仍开放，详见 SECOND_ROUND_REPORT.md。

## 阶段二十三：Clinical Canvas 全站前端候选

**负责人：** 钟佳桦。**类型：** Frontend / UI / QA。**分支：** `feature/clinical-canvas-v1`。
**起点：** `2be89143a8abccb3c3896a8f53633e490cf79b28`（远端前端最新HEAD，实际fetch确认）；独立worktree `/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai`，原研究checkout与其他人工作未改。
**阶段提交：** Phase 0–7 完整SHA及每阶段测试/截图见 `docs/frontend/CLINICAL_CANVAS_IMPLEMENTATION_REPORT_V1.md`；阶段7 `a05f8e6abf8fc422ef23ccfe444f9cf330433bf9`。最终提交补录见下一条。
**完成：** Clinical Board 概览、病例表/局部筛选、CT优先Case/Result、统一Shell、真实范围Jobs/System、Login/Preferences/404、明暗和密度tokens。保持API/auth/Viewer/geometry/lockfile不变，来源哈希存证。
**发现与修复：** 创建成功但路由失败可触发重复Case，改为保留acceptedId；密度控件值变化但内容撑高行，改为密度控制cell padding，实测47.14/52/60px。未知状态继承属性用own-property检查。旧浏览器断言改为当前中文标签及可访问ID，不移除几何门断言。
**验证：** 121/121 tests、18spec，独立vue-tsc、/mvp/ build PASS；本机Chrome合成API+实际Cornerstone共26场景PASS、143张最终截图、0page error/0外部请求。6组五标记几何最大0.6121 CSS px；10次尺度切换renderer/cache不增，30秒空闲无持续重绘，离页释放至0；五页两主题对比度抽样PASS。不是完整WCAG认证。
**边界：** 无push/merge/deploy，无Backend/Worker/训练/数据/D10/冻结基线变更。真实账号/Backend/GPU链路未运行，当前GPU状态未知；全局统计/RBAC/遥测缺口输出独立Backend能力请求。建议进入授权部署验收准备，不能直接视为生产/临床可用。
**证据：** `docs/frontend/clinical-canvas-evidence/final/browser-acceptance.json`、tests/typecheck/build日志；`frontend/geometry-qa/clinical-canvas-browser.mjs` 可复跑。

**Clinical Canvas 交付补录：** 最终受测应用提交 `e8eec4241d2a33ff8995461ed2cc920840962b4a`（Phase 8）。其后仅补齐本交付记录、报告和完整变更清单，无应用源码变更；测试/build/浏览器结论绑定该应用提交，最终文档提交编号见负责人交付消息。未推送、合并或部署。


## 阶段二十四：Clinical Canvas 本地 production 集成验收

**日期：** 2026-10-04，Asia/Shanghai。**类型：** Frontend / 独立 QA / 文档。**分支与 Worktree：** `feature/clinical-canvas-v1`，`/Users/skyfrost/.codex/worktrees/clinical-canvas-v1/infectious-ct-ai`。
**开始真实 HEAD：** `7ada03b76142e6f45fea9c531f634e36a44cebf8`，源码干净；未覆盖后续工作。**固定受测源码：** `273e76aa3e540cdf14a600452e4980167c158e35`。
**变更：** 修复 AcceptedJob 后导航失败的重复提交，保留原 Job 并提供普通深链恢复；添加隔离 HTTPS Gateway/Backend + SQLite/TEST_STORAGE 与 production 浏览器工具。没有 UI 重构或服务端/算法/研究改动。
**实际验收：** 开始源码121/121，最终126/126（18spec）及vue-tsc/Vite /mvp/构建PASS；真实本地14场景、Mock10场景、23截图、0page error/0外部请求。production几何六组最大0.45566673285130727CSSpx。34产物文件与preview字节一致，构建包SHA256为 `42321d170b168702fb8edbdd4ca697416749c5418d9b14113bc4660515712727`。
**证据限制：** 最终真实隔离库1个CREATED Job、attempt_no0、0Worker、0Result；正向Result/资产为Mock，不假报GPU或新任务完成。旧注册Backend分支不能替代候选内契约。状态 `CLINICAL_CANVAS_LOCAL_INTEGRATION_PARTIAL_PASS`；PostgreSQL/MinIO、正向真实推理及远端/GPU验收未完成。
**交付与停止：** 唯一合并报告 `docs/frontend/CLINICAL_CANVAS_LOCAL_INTEGRATION_REPORT_V1.md`、Release manifest及必要证据；本轮服务/浏览器停止，无push/merge/deploy。下一步Release只读固定candidate并补齐获授权的真实环境验收。

## 阶段二十五：公开主线整合候选

**日期：** 2026-10-07。**分支：** `codex/epilocate-main-consolidation`，起点为公开 `origin/main` `14c114ab26226561615315f7d3d25e42fcec64cc`。本阶段按文件导入独立 Clinical Canvas `117ce7a61c6bd8ba6893ecb83445d8647c9965a1`，再适配 `8a5928fcdabfb0326e1f76182f6f54f4278eb022` 的会话、超时、任务幂等与焦点行为和 `f548a624588deb922131c0c07b83336e2bc0ff15` 的 Worker 安全诊断；导入冻结 D10 的公开离线工具及 Stage 1 测试。保留原公开 `main` 祖先，不把内部开发、研究或交付历史作为祖先合入。

**验证与边界：** 前端 155 项、Backend/Gateway 51 项、Worker 协议 28 项、D10 53 项及 25 个子测试、Stage 1 8 项通过；`/mvp/` 构建及真实本地 14 场景、Mock 10 场景通过。真实本地库无 Worker/Result；PostgreSQL/MinIO、真实正向推理、GPU、生产与临床验收不在本阶段。研究结论以 `docs/research/REPOSITORY_STATUS_20261007.md` 为准。来源、测试和发布恢复门槛详见 `docs/consolidation/MAINLINE_INTEGRATION_20261007.md`。此记录说明候选内容，PR 合并及分支退役须以之后实际 Git 记录为准。
