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
| 2026-10-13 | EPI-NEXT R76 E2/F0 版本化结果接缝 | `fca57445fe6f82c9e9bc501b053b889928832d1f` | 分支级实现；指定合成测试通过，真实算法/医院冻结未运行 |

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


## 阶段二十六：EPI-NEXT 本机算法开发与合成验证

**日期 / 负责人：** 2026-10-09，钟佳桦。**基线：** `169bb42b94365ae0eeccae10e425fa1e167f3ce1`；四个独立 `codex/epi-next-*` 工作树，主控整合仅在 `codex/epi-next-integration-20261009`。

新增隔离研究包和单命令 CPU 验证入口。E1 固定target margin、E2 HSPI独立参考变体、F1原型、数据/几何评价、冻结encoder/head/CAM/cache与结果收据独立测试。初次整合115测试通过；真实baseline权重合成输入 E1/E2执行25次调用，E2不可行结果保留。源码/最终测试提交与产物哈希见本阶段交付补录。

现场确认186患者130/28/28划分和61患者811SOP开发GT；未访问封存影像或GT。用户暂不启动GPU，无远程/付费计算、前端重构、冻结资产改动或主线合并。合成PASS不代表CTFM可行或病灶定位改善；真实GT-vNext/患者比较/三次端到端医院验收尚待完成。详见 `research/next-hospital-20261014/reports/PREFLIGHT.md`。


**EPI-NEXT 最终本机交付补录（2026-10-09）：** 固定受测源码提交 `8aa5138a2b51b292eb5b8762f4d908ceb493d29d`，单命令在 clean source 上运行，137 tests PASS，8步骤exit0。新增实际CT-FM适配器小试：官方权重SHA `b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215`，CPU 32³合成输入→[1,512,2,2,2]；推理0.079812s、整进程峰RSS1285603328bytes，非全病例/非GPU性能。E1/E2真实旧权重合成对照219calls，E2两个尺度CPF可行但PSMI无支持，NO_RELIABLE_RESPONSE且零候选。残余输入F1刷新baseline/粗图，8calls（7extra含2probe）到stage上限PARTIAL_BUDGET。最终receipt SHA `e83ba9e260721bc8246f3f4c183dea60c9169db9733c8860e0318b82495e05a4`。公开原始合成数值及哈希位于 `research/next-hospital-20261014/reports/final/` 和 `DELIVERY_RECEIPT.json`；完整实跑命令保留本地ignored收据。首次下载超时、一次测试断言不匹配记录保留；没有覆盖历史证据。GPU未启动，真实患者/GT-vNext/native overlay/临床效能仍NOT RUN。受测代码之后只补文档和数值证据。


## 阶段二十七：医院版本接口与集成交付候选

**日期：** 2026-10-09，Asia/Shanghai。**分支 / Worktree：** `codex/epi-next-integration-20261009`，`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`。**开发前 HEAD：** `2ed840ff00fcddf812150637b23f6a5a2af13435`。

在总控唯一writer交接后接管未提交 `volume_io.py` 与生成 DICOM 测试，增加医院侧车输入输出、空间ledger消费、全生命周期设备锁/预算checkpoint、不可覆盖结果与未知事务对账、算法flag和原协议fallback接缝、验收门禁及 `hospital-release/20261009-integration-v1/`。未新增前端页面，未把新运行器安装到 Backend/Worker。Phase1资源策略保留，Phase2说明明确CPU/MPS授权、当前MPS仅ENCODER、远程付费暂停。

新接口/生成DICOM定向35项合成测试通过；全量测试和固定受测提交以交付后续补录及 `evidence/verification.json` 为准。真实数据只消费DATA经总控SHA固定发布的v2交付，不另建allowlist/GT/授权收据；正式空间资产和模型运行器未到齐。真实端到端 `BLOCKED_BY_DATA_HANDOFF`，医院默认算法待定，10月14最终冻结和临床验证 `NOT RUN`。历史A/B/C、GT-v1、FrozenBaseline及核心应用协议未修改，未push/merge/deploy。


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

### 2026-10-11｜医院MVP先完成生成应用接缝

原集成树codex/epi-next-integration-20261009，开始HEAD `0e13a1f9167be9d6f2bf815b49cf3ff9e16650b1`。新增独立生成QA入口，不改产品UI/协议/数学：现有Gateway、Backend、WorkerAgent及原生DICOM viewer通过真实HTTP和SQLite，推理及存储为明确test doubles。三次生成流程与一次失败持久化PASS（50.272s、7jobs/6results/27assets，单切片overlay误差0.39894CSSpx），无医学模型调用、部署或患者像素读取。结果包hospital-release/20261011-mvp-v11仅工程候选；成功wire LIVE_CASE为兼容fixture，非医学banner及证据范围明确。

科研不作为MVP阳性前置：E1冻结有局限，E2旧CPF零可行，F0未完成head，F1实验；产品当前保留FrozenBaseline及16/32/64。新增三次真实CPU旧版流程提案（3固定SOP、3jobs、96batch forward含3基准、2802扰动/2805总图像、B0/update0），不挪用P1/C1权限；医院展示因精确资产/受众未锁定保持NOT_REQUESTED，真实E2E/预计算/录屏/冻结/临床NOT RUN。原BLOCKED_BY_DATA_HANDOFF为历史开发状态，当前缺应用范围及共享队列准入。

只读接收LOC-only storage+固定v3同入口生成证据，未接入共同IO锁v4、未重跑P1；C1真实两前向数值PASS但清理FAIL，整体BLOCKED/slot_completed=false，不能放行共享真实计算。权威revision36归总控，不写本线状态、不probe/恢复。接口/对照/回退文档复用，完整依赖/证据SHA在manifest；源码提交和最终检查后续补录。


**生成MVP固定源码补录：** 源码提交 `65651041800f05d464df3d0fa589f9c5b09e820a`，qa入口字节与attempt6受测源码一致；无追加浏览器/模型/peer测试。生产构建、三次生成闭环及失败持久化证据保存在v11；显式base文档检查/暂存diff检查PASS，只读算法对照拒绝未验收新算法。元数据将source_git_sha锁此提交，医院冻结/真实E2E仍NOT RUN、展示NOT_REQUESTED；真实共享计算暂停，R1归总控。


### 2026-10-11｜固定v3恢复链与R1最小消费适配

开始HEAD `fe36b2076edfb9b8a1ff351ea72850a93f31f2b5`，原INTEGRATION树。总控唯一委托恢复消费适配，保留c9f5369固定v3及v4 IO候选不动；runtime/recovery_chain_v1只从原v3派生execution_lock和wave1_supervisor两文件，逐一绑定旧CTFM128/R0及新C1/R1的start/receipt/review/raw/owner。前序决议按其当时允许的已消费C1键验证，并核对新槽started.administrative_recovery四个原字段；节点上限2、循环/过深/漂移/缺证据拒绝。两个既有串行/设备门禁仅对完整old_job_ids集合让行；旧单槽字段保持兼容，已消费任务/第三未知槽继续阻断。无新IO锁/调度器/finished伪造。20生成隔离fixtures PASS0.33s；只读实际新决议SHA `ceb164cbca27c0e547da8c09b65fc8c10d78f0544e62bf4b9ead0920ab4eece4` 对P1重试/MVP两键PASS。实际queue写/GPUprobe/观察/医学F/B/update0。源/差分/收据在hospital-release/20261011-recovery-chain-v12，固定bundle待提交后补录；MVP接入紧随，真实dispatch仍总控。


**恢复链唯一固定bundle补录：** 两变化源码提交 `14bf16ebe05f4652204148a0faf0fc455cfb8667`；八模块命名包epinext_wave1_recovery_chain_v1导入/verify_loaded_bundle PASS，dependency SHA `093e0a7fd137ae9772dd30595fe39de845a7babe9de1617d633782a02707a192`，bundle receipt SHA `9ad2257237f859adad2267d33353cf87df6433270923ec2975385d617fe9ce48`。六模块逐字保持原v3，只有两门禁/恢复validator变化；没有共同IO锁v4。bundle/索引完整绝对路径见v12/manifest.json；20测试复用不重跑。本补录仅版本元数据，原始diff上下文空格导致diff-check失败，现改为零上下文diff，源码不变。医学F/B/update、真实队列写0。

### 2026-10-11｜本机受保护医院MVP接缝候选

INTEGRATION在原分支codex/epi-next-integration-20261009，开始HEAD `05a4279177e5d09b80ce3c634fae65c714abca89`。新增独立QA入口包装原FrozenRunner/WorkerAgent及应用协议，固化获批3旧Occlusion jobs、96批/2805图像评估、B0/update0、总540秒/例180秒与256MiB输出；全模型前后hook保留预约/完成计数、原logits及独立SHA产物。未知提交单次发送后只读对账原Job/Attempt/digest/对象字节，同Job换Attempt不得重算；partial原生产物保全，Worker/心跳未退出不得宣布恢复。只消费v12唯一恢复链，不改旧v3、LOC源码、共同IO锁或原前端。

29个轻量生成fixtures PASS0.03s；没有新浏览器/构建、Torch导入、权重/患者像素、医学F/B/update、真实队列读写或GPU probe。源/报告/流程在hospital-release/20261011-protected-mvp-v13。metadata工具只准备NOT READY fragment，不创建allowlist/批准/dispatch。当前P1占唯一资源窗口，新入口生成浏览器验收NOT RUN；DATA原3 SOP的BurnedInAnnotation缺失保持UNKNOWN，负责人逐图像素复核前真实上传BLOCKED。scope批准有效但真实MVP等数据真实满足门及总控串行dispatch，不能宣称医院/临床PASS。原应用默认FrozenBaseline保留，医院默认null；E1/E2/F0/F1仍未注册医院应用。源提交/metadata SHA在提交后补录。

**固定源码及metadata补录：** 源码提交 baedeb240d2df51b75be0c8d41bd09a98d3fd6c8；metadata fragment SHA 4cfa24cec74596cfd2a055e6d77c60e7693f35a25d8b8842d932c236b4151e2a，绝对路径见manifest.metadata_fragment。metadata receipt记录98个源码/构建文件、Torch未导入、像素/权重/队列读取0，status固定NOT READY；包版本仅metadata查询，无模型执行。本轮原前端/Backend/Gateway/Worker/algorithm/src/occlusion_runner差分为空。显式base文档及staged diff检查PASS；不追加旧测试、浏览器或模型运行。

**P1退出后生成差分补录：** 总控通知唯一P1实际退出/队列恢复后，INTEGRATION运行受保护入口生成浏览器闭环。attempt6 exit0：3旧Occlusion jobs/3 Result/27资产，96假模型边界回调/2805生成评估、医学F/B/update0；Job/Result身份与SQLite逐项MATCH，截图包含非医学banner、原生CT与叠加及刷新64选项，实际Torch未导入。29轻量fixtures仍PASS0.03s。attempt1–4的Backend启动/登录/图层异步等待竞态修正；attempt5发现URL提前记录Case，修正后仅attempt6作为验收，所有六次自有线程/服务退出收据保全。该补录替代上文新入口浏览器NOT RUN；真实MVP仍需原3 SOP人工像素复核、DATA正式字段映射和总控单次dispatch，医院/临床/冻结仍NOT RUN。最终受测源和新metadata绑定提交后补录，旧baedeb2 fragment保持历史NOT READY不覆盖。

**最终受测源码固定：** source Git SHA `9dad72a5ad3e5931340dc91444072c57d5f74d2c`；原3流程生成验收及29项fixtures均对应当前代码字节。98源码/构建绑定与生成receipt逐项一致，最终engineering-readiness fragment SHA `3b4bb987df4f66b707a73f0ad298de6d05d6ee9eb09abd4b99a022c4af71dde2`，绝对路径见manifest。其status仍NOT READY、data_delivery=null；仅附生成工程证据，剩余人工像素复核/DATA映射/总控MVP dispatch。原baedeb2 fragment不覆盖；v12唯一index SHA保持12e808bcf23f80571886fa0e8c68efa88a11fb833a51db002ab1820d20fc1a6d。未追加模型、GPU、队列观察或构建；医院最终冻结与临床NOT RUN。

### 2026-10-11｜负责人三图人工确认与DATA v2等待

INTEGRATION，开始HEAD `2ee9ab18c950d2d5c5a12dbccb777f9455205d2e`。总控转交负责人直接确认，中央decision SHA `437158c573e126152f134eaf61789f010b6629cd27e47212808861fe0988e133`及review SHA `6f97bb99f983869f214709b2cd98a0d62b16360fc6b57a0ffe8f283072c57a19`只读核验通过；三例原CT SHA与prepared一致，三图均NO、完整panel/边缘检查由负责人记录。人工确认缺口已解除，但记录status OWNER_RECORD_PENDING_DATA_AUDIT，正式DATA v2派生ledger尚未由总控转交。v14只保存消费摘要，不创建allowlist/GT、不改BIA、不打开9PNG或原CT、不调用模型/队列，不代替DATA审计。v13受测源码/29fixtures/生成三流程复用，不重跑；CPU96/2805/540秒授权仍有效，最终readiness/argv等DATA正式交接后发布，总控独占dispatch。医院展示、冻结、临床NOT RUN。

### 2026-10-11｜正式DATA v2适配与chief最终readiness接缝

总控交唯一DATA v2 ledger SHA `bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1`，DATA_final_evidence_audit PASS、原3 SOP逐图NO正式关联。INTEGRATION按原schema字段直接消费source/Study/Series/索引、像素SHA、保全/去标识/上传范围及中央owner复核链，不写DATA/GT/BIA/allowlist、不读CT/权重。原owner_PENDING_DATA_AUDIT不改写，由DATA v2明确完成审计。现有JPEG Lossless decoder版本加入绑定，无安装。新增metadata-only finalizer，既有两锁非阻塞采样/slot收据SHA核对，不产生队列文件或槽；旧两UNKNOWN按ceb164保留，新UNKNOWN/spent/busy/漂移拒绝，真实启动仍由总控和原supervisor再次准入。48生成轻量fixtures PASS0.06s；新生成浏览器三流程exit0、3jobs/3results/27资产、96假回调/2805评估、99源码/构建SHA闭合、医学F/B/update0，实际数据库身份及自有退出PASS。原预算/冻结/前端核心不改；finalready/argv固定源码后补录。v15本地包，真实MVP及医院/临床/最终冻结NOT RUN。

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

INTEGRATION 工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`，分支 `codex/epi-next-integration-20261009`，开始 HEAD `8e8b202a00ea4bc4c407e206d08b630a6dbfd566`。本地集成提交 `fca57445fe6f82c9e9bc501b053b889928832d1f` 增加 LOC v5 目标契约校验、E2 v5 保存结果适配、ENC v4 F0 保存结果只读消费、隔离的研究结果提交/读取校验，以及仅对带版本化研究诊断渲染的 Vue 面板。来源契约使用 LOC SHA `d852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c` 和 ENC SHA `2b2e2d0ebb6e56094451baab09e969782258155bbc6cae31ee769dcac92e0467`。

输出区分解释目标和原始预测类别、任务范围和来源标签；E2 的全 logits 优化定义与固定目标 margin 分开展示。F0 保留来源组标签范围、4×4×4 有符号来源分类贡献、effective bias、logit 恒等式及名义 native/LPS 格点，不显示为病灶概率。旧 v4 serializer 可继续处理旧格式；基础 API 未自动注册研究 app，无数据库迁移。FrozenBaseline、历史 A/B/C、GT-v1、旧 Occlusion16/32/64 与 v16 包没有改变。

15 项后端生成测试、3 项前端生成测试、`vue-tsc -b` 均通过；独立临时目录中的 Vite production build exit 0，保留既有 codec externalization 和大 chunk 警告。测试只用合成输入/数组/保存结果，不启动服务或执行模型。真实 CT、真实 E2 应用运行和 F0 数据交接仍未完成，F0 实际保存头/缓存/结果为 `BLOCKED_BY_DATA_HANDOFF`；真实左右/切片顺序/世界坐标/crop/resize/resample 验收、三次医院流程、展示审批、医院冻结和临床验证均 `NOT RUN`。本分支结果不覆盖先前 target0 与实际原始 argmax1 的 5F 记录，也不改变医院决策。

交付包：`hospital-release/20261013-r76-research-seam/`，含 manifest、算法对照入口、验收报告、演示与回退说明。现场仍指向 v16 既有操作清单；负责人对原本地影像/结果医院用途的决定尚未完成。没有服务启动、GPU/MPS、上传、截图、录屏、部署或推送。

### 更正｜2026-10-13｜R76 目标类别口径

R76 算法对照文字“两个类别不等时拒绝”存在歧义，现按 LOC v5 源码改正：`DECLARED_FIXED` 允许解释类别不同于原始预测类别；实际 resolved 必须等于 declared。`ORIGINAL_ARGMAX_FIXED` 则用原始 logits 首个 argmax，并要求声明与该 resolved 一致。原接缝代码和 target0/prediction1 生成测试已按正确规则实现，本轮仅更正文档，不改旧5F应用target0/科学target1差异或任何科学收据。

### 2026-10-13｜R77 E2-R 精确执行准备与累计输出保护

INTEGRATION 原工作树/分支，开始 HEAD `75d2ef118ea717e8c3cbcb413e247f25d964eb55`。源实现 `3e2373d2aa3371ec620cd5c8c088e1aa6a06e405`，最终运行源固定于 `e303595099b31d7ab6f66652feda1b7fdffc1fa5`。新增科研只检查/一次父子入口，复用原 E2 实际加载器、v12 共享监督和全局计数，不改旧 MVP/Frozen/5F。LOC 固定 readout 配置 SHA `1d2611e8371a3d8074441f53e2832fdc46f4f38b5011a58ffb22f37ae9b3ae52`，同 case3/epoch3604/cell43，原4 logits严格兼容复用，12读出+2适配检查=计划14F/上限18F，4F不分配，0B/0更新/CPU1/120秒。

64MiB按生命周期累计写入保守预留与保留/临时峰值双重限制，包括结果、失败残留、父子日志、监督遥测及本任务slot文件。现有IO锁内父子共享持久账本，替换和失败不返还；账本每次写入计512字节，普通56MiB/终态8MiB，终态过大拒绝而不伪造成功。native日志有界管道排空并记录丢弃，父异常和摘要不在账本外另行输出；已知部分调用数传递到监督完成，未知保持null。原调度/设备锁和身份停止规则未修改。

25项生成定向验证PASS2.74秒；包含实际共享guard的生成完成记录和一个非医学Python日志fixture，没有占用计算slot或读取医学数组/权重。最终只检查命令exit0、Torch未导入/模型调用0/队列观察0；24项INT/IO源、16项LOC源、8项共享模块与8项固定依赖条目闭合。旧MVP66源/构建全部MATCH，原DB/影像/对象未读；无服务、MPS/GPU、新展示或旧验收重跑。

最终 binding SHA `92fb6d542b69d094f0e3fb65474f16827bc75d5f81b2632d584f225f0bf8f928`，申请item SHA `0f330e7ef460f3e00811583f3e4ea93aa5a4f8232d8800fef806ebe2e97aa53a`。交付 `hospital-release/20261013-e2-r-execution-preparation/` 状态 **PREPARED_NOT_EXECUTED / BLOCKED_BY_APPROVAL**，缺新E2-R owner分项批准、原恢复队列中新task准入及独占dispatch/window。一次执行argv已固定，仅待最终dispatch及SHA；未执行。CT-FM既有科学批准保留，本线不重复申请；基础v16/E2/F0真实消费验收继续待命。

### 2026-10-13｜R77 唯一执行故障核验与新接缝修复

R77 唯一真实 dispatch 已消费，原监督返回 `FAILED / MONITOR_FAILURE_ValueError`，具体为 `LIVE_TASK_OWNED_CHILD_REQUIRED`。`slot_completed=true` 但 `forward=0`、`backward=0`、`sequence=0`、`cases={}`，没有 ADMITTED、模型加载或医学前向；这是监督入口失败，不能写成科学失败。原 STOP、supervisor receipt、finished 和父日志原样保留，未重跑原命令、未重建原输出目录。

根因限定在 INTEGRATION 的 `qa/e2_readout_output.py`：自定义进程代理不满足共享 `DeviceSlot.track_child()` 的 `isinstance(subprocess.Popen)` 身份契约。最小修复返回真实 `Popen`，为该实例保留排空完成后的 `poll()` 语义，未修改共享监督器、设备锁或历史协议。生成复现和 25 项定向测试均只使用生成 child/目录；新增测试实际调用共享 `DeviceSlot.track_child()`，确认身份、监控回调和 stdout/stderr drain 正常。

修复后生成新 binding `execution-binding-r77-fixed-v1.json`（SHA `c62d7d98d00b3d132e14652307044381161145bc9fbe5107a53eafd2ea648cfa`），改用新 `...INT-2` task/job，状态 `PREPARED_NOT_EXECUTED / BLOCKED_BY_NEW_DISPATCH`。仍需总控重新确认 owner、同恢复队列的新 task admission 和独占 dispatch；本轮不自动执行。医院默认、真实 CT、临床验证和最终冻结继续 `NOT RUN`。

### 2026-10-13｜R79 E2-R drain 生命周期与新申请准备

在现有接缝内移除无超时的 `thread.join()`：`poll()` 不再等待日志线程；child 退出后 drain 仅有 0.25 秒观察窗口，之后设置停止事件并记录 `CHILD_LOG_DRAIN_TIMEOUT`，上下文退出使用有界 join。原生 `Popen` 身份、track_child、日志上限、累计输出账本、deadline 和 fail-closed 身份信号保持，未修改冻结 v12 bundle。

33 项生成测试通过（7.43 秒）：父子成功、提前退出、GLOBAL_DEADLINE、未知身份拒绝、ProcessLookupError 早退竞争、后代持管道 drain 超时与日志上限均有证据。原 R77 明确为 durable reserved 0F/0B、`runner_actual_counts=null`，不改写为实际 0F/0B。新 R79 binding `f16169a035add8a8a022f1ccb5fa5add32229dc57905e332f8acd064e9cc2daf` 使用独立 INT-1 task/job，申请 SHA `058a1e929bb4c235d4a6b420821dae7fa3a31e9ec076256f0204dca603acf1a6`；真实执行仍 `NOT RUN`，需新 owner/admission/slot。


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


### 2026-10-13｜明确授权后三项有界执行收口

主控在原INT工作树codex/epi-next-integration-20261009，起点3b01590822b05ed31a59761d5f206632c5df4417。未修改冻结执行源码、科学配置或candidate/dist，仅记录真实执行与现有报告。本记录对应的文档提交可由Git定位；未push。

直接负责人消息01a134e5-e172-76b3-83e4-7dc09f0bc7a6确认两项科学final SHA与demo64候选。E2-R本次CLI相对binding字符串与绝对dispatch对象不匹配，入口exit2、无监督/slot/科学目录、actual=null；总控调用错误已明确，未自动重试。R18仅派生新admission引用，其他原final字段不变；新监督真实执行首组预处理处FINITE_CPU_WINDOWED_SCALAR_224_REQUIRED，actual0F/0B/0更新由runner明确报告，0完整cache；子进程3/父2，slot_completed，2.487273秒，采样RSS峰457687040字节。无成功cache，train/eval未运行，旧actual=null不改。

demo64一次真实本机核验8.908842秒，服务/登录通过，ready提示hidden触发可见性断言，FAILED_OR_PARTIAL。三例/刷新/接口拒绝/独立空间未完成；人工NOT_RUN、最终演练0；浏览器与三自有服务关闭、原DB不变、无Worker/模型/截图/录屏/外传。acceptance SHA884e5a8a971c34e70c2f5624c9c04a7d5dbd47968a41cd22eff2b7bbc58e7c89；详见原展示清单。科研无新改善证据。唯一writer更新revision84/CONSISTENT/pending0，仅记录真实结果；历史失败/UNKNOWN/原额度保留。本轮停止，不追加重试或后续实验。

## 2026-10-13 — Revision85 engineering fault isolation, no real retry

Added metadata-only E2 argv derivation from exact dispatch strings (7 production-parser/comparison generated tests). Existing E2 science, source binding, outer 21 runtime references and frozen Demo candidate remain unchanged. Added independent acceptance instrumentation: current image render event/state, decoded dimensions, visible nonzero canvas and currently drawn asset must all match; hints do not establish readiness. Generated DICOM traverses the existing Vue/Cornerstone decoder/render chain with positive and negative state tests. Atomic step evidence and separate primary/cleanup failures are covered through the actual driver failure/finally entry. Total 11 generated tests passed (including one browser test with multiple scenarios); no medical arrays, weights, models or real three-SOP services were read/started. Old hidden-element root cause remains UNKNOWN because computed styles/ancestor state were not retained. Next real technical check needs its own corrected driver confirmation.

### 2026-10-14｜Revision86 C 技术核验静态收口

原INT工作树/分支，起点246cdd1884a59bf9c0dcb1f872a26802378488de。revision86状态SHA c24ca4f03d11084cfdbafbc1542f06bb1ef4dc884417a17618f1a47e47635782及原技术请求7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf匹配；复用原候选191b47…，不新造请求。既有checked核对190源码/21dist/23runtime、新4driver/6browser runtime通过，实际check-only exit0/services0/medical_arrays0。原11生成验证复用，不重跑未变测试。原真实FAILED_OR_PARTIAL/hidden根因UNKNOWN保留；新输出未创建，当前新技术许可未确认，真实空间/目视/演练/医院/录屏NOT_RUN。仅在v16目录新增静态收口与全部NOT_RUN操作员目视清单；不改候选、旧DB/资产、状态中心或合并表。

## 2026-10-14｜revision87批准后的64-only技术核验V2｜FAILED_OR_PARTIAL

直接负责人消息01a138fa-a7da-7b60-b9d5-799e1983bda5批准原待决表1—3各一次，owner SHA `daa12ff3b21284178b6860fdb1063e898fca2cee78b58f749a9a67de99eb5d40`。总控确认ENC串行任务/资源退出后明确发出C启动指令；按原请求 `7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf`、候选 `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917`，原驱动源码246cdd1884a59bf9c0dcb1f872a26802378488de执行一次。精确confirmation SHA `738213092b93603e0bb9c11b9e768bf70401a7c932b2b969ee5b3559d5e0e651`，原V1等待索引保留；未重跑check-only/生成测试。

输出 `.local/demo64-technical-20261013-02`，验收耗时19.766909959秒，父调用20.114539208秒，均在整体180秒内。**FAILED_OR_PARTIAL**：服务/登录PASS，首例Result HTTP200、单64摘要、九资产中本例三资产ID集合、仅64选择按钮、DICOM HTTP200及输入SHA核对均有逐步PASS。等待当前影像readiness超时，renderSequence=0、overlaySequence=0；current_render/decoded/rendered_status/canvas_visible=false、location/no_error=true。asset=true在此因尚未要求assetUrl而非证明64资产已绘制。不将该观测写成已证实解码错误、应用正常或空间失配；实际根因UNKNOWN。`flows=[]`，三Result/九层、刷新、真实API直接拒绝、固定点0.5 CSS px实际空间核验均未完成/NOT_RUN。

原始acceptance SHA `19d1afe5e3aa7e70b211bf5cc61cc2b6f49fd0778d855f729d881d9612bb4d4d`；exit SHA `1ec9507d6ef2d9d05a56b9737dc93092621a47a83dc7c33dfd4afdc136b990c3`。primary_failure.message保留CURRENT_IMAGE_READINESS_TIMEOUT；原step记browser_closed，因browse finally先记录清理再传播异常，实际失败位置由assert_09后wait_ready及原源码确认，不改原receipt。cleanup_errors=[]、browser_closed=true，三个自有服务exit -15、自有恢复父/driver exit0；**driver exit0不等于技术PASS**。原DB不变、model_calls0、worker_started=false、external_requests0、page_errors0、截图/视频/trace/像素导出0；已知driver/服务/恢复父PID均未再列出，不信号任何未知进程。

实际索引 `approved-abc-execution-20261014/INT_EXECUTION_INDEX_V2.json` 位于原私有总控交付目录，记录owner/confirmation/精确argv/原始收据/日志及退出SHA；当次结果索引SHA `02bc8e23ddf046f2f0c54bd78a786e11bf0f57aa9f112ecb01b6c8134e8a7efd`。无新Job/slot/模型，原v16/DB/对象/dist保全、旧FAILED_OR_PARTIAL/hidden根因UNKNOWN不变。本次许可已消费，停止且不自动重试。人工NOT_RUN、最终演练计数0、医院用途/录屏未批准、最终冻结NOT_RUN；不抵扣最后三次演练。仅文档增量，不改总控state/合并表，不push。

### 2026-10-14｜Revision88 64-only生产路径工程修复（真实NOT_RUN）

INTEGRATION原工作树/codex/epi-next-integration-20261009，起点db3845bcf228aa283cdfaf1067c63ac0ec25b7d2。沿工程许可只读原日志/收据及源码；无患者像素、源DB/对象正文读取，无真实恢复/推理/重试。两次真实失败、旧candidate191b47…/request7398099…原字节保持，历史根因UNKNOWN。

生成生产构建确认构建器把Vue条件template改为无指令HTML template，使内容隐藏、canvas零布局；只改候选生成器为Vue v-if fragment，不改原应用源码或v16 dist。生成TLS链另复现预连接无握手阻塞旧accept loop（ConnectTimeout1.002秒），候选edge使用64 backlog/在线程IO中握手，旧readonly入口保持。验收V3复用原joint readiness/固定点/0.5CSSpx，核心namespace按命名导出或t统一解析，绑定实际chunk，不再假设minified名称；失败前保存布局/engine/静态资源诊断及primary位置、failed/cleanup failure返回2。旧V2驱动不改。

最终生成生产回归PASS：实际编译Vue、Backend/Gateway/HTTPS、3个生成SOP/Result、9个64层、刷新/直接范围拒绝/独立相机投影；JPEG Lossless SV1从零构造并实际browser解码。空间最大误差0.0000152587890625 CSSpx，仅生成。初始非空File、替换/移除、取消重挂载、清空/旧资产、坏DICOM、core初始化失败、刷新/unmount和浏览器/三自有服务退出均通过，270个持久化步骤，模型/Worker0。12项driver/API/预连接生成测试PASS2.34秒，3项候选+11项几何前端测试PASS743ms；普通候选vue-tsc/Vite build PASS，codec externalization/大chunk提示保留。夹具依赖/绝对路径、多entry core导出和TLS/生命周期失败目录保留，不计真实重试。

冻结新候选与单次请求在提交后按实际source/dist/runtime/driver/browser SHA发布，不建owner/admission/slot/dispatch；旧恢复66源/构建逐项MATCH，原DB/对象未改。真实三SOP/空间/人工/演练/医院/录屏NOT_RUN，原Ridge结果不改。完整报告及新绑定由本线交总控集中，不写state/原两表、不push。

冻结对象收口：代码0e44ac5adfc4dcc58e1eeb829b39d35e25d17de7；新candidate a7d3cc77d17d4bf44fd45b80ea44b35472faa3a1e2c31f8b93a18eeb6b818da0，新request2d3d5da57a818b2b202b5fe93db632fe8fbfd1e79cb7f2487f478565575b5934。197源码/旧恢复引用、21dist、23runtime及新driver/core/browser/config绑定，check-only实际exit0/services0/medical_arrays0。完整报告及机器索引hospital-release/20261014-demo64-repair-r88；旧66引用和两失败/candidate/request字节对账保留。等待新精确一次批准，不执行真实任务。


## 2026-10-14｜revision89精确批准后的64-only技术核验V3｜PASS_TECHNICAL_ONLY

本节补充R88工程准备的真实运行结果，保留此前两次FAILED_OR_PARTIAL及其根因UNKNOWN。INTEGRATION原工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`、分支 `codex/epi-next-integration-20261009`，执行前HEAD `eeda34d76a5f302830beaa1fcb332e5c78a3a850`；绑定代码提交 `0e44ac5adfc4dcc58e1eeb829b39d35e25d17de7`。负责人直接消息 `01a13971-3b26-7d10-9617-9f5343584f34` 已独立核验，精确批准请求 `2d3d5da57a818b2b202b5fe93db632fe8fbfd1e79cb7f2487f478565575b5934` 各执行一次、串行、失败停止、不自动重试，不含医院展示或录屏；R18已完成结果仅复用。总控明确C启动后，核对revision89及writer账本COMMITTED一致/pending0，state SHA `cd7a9127bca91d2ff9c8c813330a86885cc04b0dd81cc57f1956c9376df7c85a`，没有写入state或两份合并表。

owner approval SHA `c965d0e15b925e86e282bf8abc681f73f4f0bd845c772ca5c5db99c864054f55`，原始owner message SHA `cf29dc9a6852f9b8aafc6465ed6cf3ae57ae63d1997cdfa609869f2ed38bfbc9`，执行confirmation SHA `cd6bc230a73e03068a2dd73744b734e6cba7dd8fe35f371ae555209e870e067b`。新候选 `a7d3cc77d17d4bf44fd45b80ea44b35472faa3a1e2c31f8b93a18eeb6b818da0` 的197源码/旧恢复、21dist、23runtime及driver/browser/core绑定全数匹配；旧唯一DATA ledger/policy复用，无第二allowlist。新输出目录执行前不存在，V3精确argv已记录，只调用一次，未重复check-only/生成测试、未改代码或容差。

实际本机浏览器、Backend/Gateway/HTTPS只读流程 **PASS_TECHNICAL_ONLY**：服务、登录、三个既有历史Result、仅64、三个结果刷新恢复、直接API范围拒绝、独立空间检查全部PASS。3个单SOP与原DICOM SHA核对，9个64图层均通过当前decoded/rendered/可见canvas/当前asset readiness；独立原生DICOM IPP/IOP/spacing加相机投影核对每层固定7点，共63点，最大误差 `4.263256414560601e-14` CSS px，原容差0.5 CSS px不变。这里只证明单切片FrozenBaseline/64展示链，未覆盖完整Series、切片顺序、3D、任意crop/resample或新算法；没有重算模型，也不建立科研提升或临床有效性。259条步骤事件包含STARTED/PASS和辅助元数据，不误称259项独立测试；66条静态请求记录均HTTP200，page_errors为空。

原始收据 `.local/demo64-technical-r88-20261014-03/acceptance.json` SHA `02377afccc9cd0a71f7b53cf93d0895baa85d2ac03c96eed0a6d0dc1f5504b7e`；实际验收8.254969917秒、父调用8.574972583秒，分别低于140/180秒预算。退出收据 `services/restore-exit.json` SHA `bd9913e047b5e0cbb33a6a8c6d500e5a7f693f3af7aef822763156b314d89feb`：browser_closed=true，cleanup_errors=[]，自有服务35622/35623/35624均exit -15，恢复父35618和driver35614均exit0，五个已知PID退出后均未列出。源DB不变，Worker未启动，model_calls/new Jobs/外部请求/截图/视频/trace/像素导出均0；只清理本次自有进程。

完整私有索引 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r89-cache-demo64-20261014/INT_EXECUTION_INDEX_V1.json` SHA `820bb019bd785f4e882d01d35bb5961c5da38f4e2d2d7af0bdd712f30f8aab94`，记录许可、源码/运行时、精确argv、日志SHA、原始验收/退出及对账结果。stdout SHA `3c1fb99e39566844c2bf76477eb90cb5ba1b8736e0f2644520a68052f7e600ce`，stderr为空/SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。受保护收据及配置保留本地，不提交患者影像、患者空间细节或凭据。

本次一次许可已消费，不自动重试。旧v16/DB/对象/dist、A/B/C、GT-v1及旧两次失败收据保持；旧版回退范围不扩大。**人工目视NOT_RUN；最终三次演练计数0；医院用途NOT_APPROVED；录屏/播放NOT_RUN且未批准；医院最终冻结NOT_RUN。** 三个历史Result流程不是最后三次演练。仅增量更新本清单及两份工程文档并本地提交，无push/部署/state writer/待决表修改；最终是否PASS/CONDITIONAL PASS/NO-GO由钟佳桦批准，总控统一汇总。


## 2026-10-14｜最终验收步骤准备与首席汇总交付｜SPEC / NOT_RUN

原INTEGRATION工作树/codex/epi-next-integration-20261009，准备前HEAD `6238216f33d7fd3bb56e1e20c2c3b35631bdc4ec`。用户明确授权将本次索引/Git SHA/验收摘要/未完成项交给现有首席算法工程师会话 `01a138ed-90ba-7311-822e-9b48e7363f59` 汇总，并准备人工目视、三次最终演练与备用录屏步骤，未获对应批准不得执行或宣布冻结。

实际核对R89索引SHA `820bb019bd785f4e882d01d35bb5961c5da38f4e2d2d7af0bdd712f30f8aab94`、acceptance `02377afccc9cd0a71f7b53cf93d0895baa85d2ac03c96eed0a6d0dc1f5504b7e` 和exit `bd9913e047b5e0cbb33a6a8c6d500e5a7f693f3af7aef822763156b314d89feb` 一致；3Result/9层仅技术PASS，人工NOT_RUN，最终演练0，视频0，医院冻结NOT_RUN。

在原hospital-release v16交付目录新增 `FINAL_ACCEPTANCE_PREPARATION_20261014.md`，复用逐例人工清单并补充V3候选绑定。步骤分别明确许可/版本/资产/设备/预算、逐层人工观察、同配置三次完整独立流程、失败停止与事务对账、录制和完整播放的独立证据、旧v16更宽范围回退限制及负责人最终决定。操作员/时间/视频路径/SHA和三份运行记录均未预造。此次仅文档和已授权摘要消息，无患者像素/DB/权重读取，无服务/浏览器/模型/队列启动、演练、录制或部署；不修改总控状态或表，不push。


## 2026-10-15｜R91 E2-R纠正绑定与64-only人工收口准备｜PREPARED / NOT_RUN

原INTEGRATION工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`、分支codex/epi-next-integration-20261009，起点HEAD `9eac2e6b8f762d6834bbd10d36963dc4b6c2a71b`。完整读取负责人R91原文SHA `25e76117801ce4b3a27d7cc40042adff604f0e33e8fea07238b73513312eb62b`。权威state90 SHA `cceaf1ffbdd503e0d021f98362f4bcf47cd622337793aed7741fbaa7a0c79126` 与真实writer末COMMITTED一致/pending0；未写state/两表，未建立队列/worktree/dispatch。

E2-R直接继承原纠正增量SHA `69730c02f5b8798180059e835eb10a40c15162c653b3c52ae979661ab5ae69b7` 与binding f16169a…，没有新重复审批对象。24执行源码、LOC锁/目标契约、21runtime、Mask/5F JSON SHA和epoch3604/cell43及相关logits元数据匹配，原MVP66引用一致；实际原check-only PASS，Torch未导入、模型/队列观察0。原case3科学方案14F计划/18F上限、0B/0更新、CPU1/120秒、64MiB及5/6GiB资源停止机制不变；真实数组/权重未读，须执行时原加载器校验。原relative CLI绑定失败和actual=null保留、旧dispatch已消费。未来精确新dispatch经既有derive生成绝对binding argv并通过原窗口/绑定核验才可调用，本轮final execute argv为空；R18优先等待总控独占release。

仅原README补齐真实readout所需原始logits/各区域面积/keep-remove与等面积随机差异/模型进入和actual计数的验收说明，现有输出已覆盖原始字段，可在保存读数上算paired差异，不改科学代码/重复生成测试或新增forward。真实E2-R NOT_RUN，缺新有效精确确认为BLOCKED。

MVP继承实际PASS_TECHNICAL_ONLY，不重跑；当前candidate a7d3cc…的197source/21dist/23runtime及Chrome6引用逐项MATCH，原3SOP/3历史Result/9层不扩大。复用既有LOCAL_MVP_ONLY本机许可支持同一负责人目视/内部三次流程，不重新申请整个本地医学方案；仍按总控“先准备”不启动，人工结果由实际操作员填写。更新原FINAL_ACCEPTANCE_PREPARATION与逐例清单，给出现有持续serve入口精确命令、新且未创建的4个run-directory、实际动态URL/私有登录配置读取方式、启动15秒检查与Ctrl-C/自有服务退出流程，建议人工10分钟/每次演练5分钟；现有serve无自动会话watchdog，明确由操作员计时退出，不称headless入口或自动监督。普通联网/Wi-Fi/HTTPS/投屏不加部署审批，受众/素材传播仍按有效用途；录屏改可选、不作阻断，未制作。

核查索引 `.local/e2-r-readout-r79-20261013/r91-preparation-audit-v1.json` SHA `1b7c49d884dcbe0d06a077828975331862bab098f8b0122ee69d6ba0af78b0c8`。本轮只有元数据/已有保存JSON核对和文档，真实数组/权重/DB/患者像素未读，无服务/浏览器/演练/录制/模型启动。人工NOT_RUN、完整演练0、医院外部用途未批准、最终冻结NOT_RUN；不倒填10月14日，不宣称临床验证。提交检查采用显式base与diff check；无push，由总控读取原会话汇总，不跨会话发消息。


## 2026-10-15｜R91新负责人批准后E2-R行政启动准备｜未执行

原INTEGRATION工作树/codex/epi-next-integration-20261009，准备起点HEAD `df58f20ce21ee2f58aa502c242f67677d824ac15`。独立read_thread核验主控直接userMessage `01a13b48-92dd-7d60-87a7-21ccf0fc648a` 对两项精确增量批准，owner message SHA1d05a47c…/itemized owner bdb752a4…；E2纠正增量69730c02…及原9ae5…/f16169a…/24源/21runtime/Mask与5F JSON元数据一致，原14F计划/18上限/0B更新/CPU1/120秒/RSS5-6GiB/64MiB及停止机制不变。旧task/job无slot或输出，沿用身份，无新task、队列、dispatch时间窗口、共享queue写入或模型调用；真实payload校验留给admitted原加载器。R18优先，本轮不消费科学额度。

在原批准目录INT_E2_R前缀内创建兼容scope view/new owner confirmation、必要新admission与派发/release模板及once launcher，原科研源码/协议不改。行政V1的compact摘要编码被固定recovery校验拒绝，保留V1及失败收据；V2用原canonical_json正确编码后只读validation PASS，不扩大scope。活跃admission SHA `b5cad416745de9a5e4e4f8192449e47e65b5eefdd010a82e7f9e88645f71c217`；派发模板 `bd2859be0461992a9ad2e69c049ec0e8a4579a81fdcbd8d95dabe6e458abd708` 仍DRAFT无窗口，不能执行。

pre-index `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_PRE_EXECUTION_INDEX_V1.json` SHA `372768910edca806dde9b3fbcc89133d4042ffa67fd7351ec351c7ca3bb3ac8e`，PREPARED_WAITING_CHIEF_RELEASE。独立wrapper源码SHA `aebba5b3a6c3399d5ef29d5b8ddfbc40eb77c6d27039f26ab3bb336c0bf1c872`，按原生成器的新dispatch绝对binding/原窗口核对，仅在实际主控release后独占claim再Popen一次。未知结果留null并拒绝重提、不发进程信号；driver exit0不冒充科学PASS。3项生成替身测试PASS0.02秒、默认check-only实际exit0/model_calls0/queue_writes0/slot_createdfalse、原strict dispatch元数据兼容核对用内存非reserved窗口，均非真实科学运行；旧生成测试/技术PASS直接继承。

本轮真实final dispatch、release、LAUNCH_ATTEMPT、原task slot/science/supervision output均不存在。负责人明确“本轮先完成科研准备，人工验收另约”；MVP服务/浏览器/显示/演练/录制0，人工NOT_RUN、演练0、医院冻结NOT_RUN。必要原README/人工说明与双日志收口，本地提交；不push，不改总控state/两表或新建worktree/queue。主控读取本会话后审阅，另发R18退出后的唯一release才可启动E2-R。


## 2026-10-15｜R91 E2-R唯一纠正调用实际完成｜SUCCESS / 非临床验证

继上节pre-index快照后，主控核验R18 train100/eval2 SUCCESS及6个父子PID退出/原锁可用，再单独给出唯一E2 release。独立核验exit证明9b7848a8…、新dispatch aa42b22e…、release ac66d045…与pre-index37276891…，原窗口/精确binding校验通过；绑定once launcher仅提交一次，无自动重试、warmup或预算扩张。实际执行日期2026-10-15；旧job目录名20261013仅身份，不改日期或医院冻结记录。

scientific/readout/runner/supervisor/driver和slot均SUCCESS，真实ADMITTED child6484、driver6475、wrapper6465。actual14F/0B/0更新/extra_autograd0，durable预留14F与actual收据一致；16对象=4历史兼容重用+12新读出，另2adapter check，max_abs0、unrun为空。原case3/epoch3604/cell43/模型和输入、硬面积5/10/20%/固定等模型面积随机、原keep/remove不变。

实际索引 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_EXECUTION_INDEX_V1.json` SHA `fea074c735ce8470e438a0598d0e81f15e96661f28e0e843487e0532b8196c59`。raw readout SHAf273f093…、机制摘要SHA12272900…含原始与扰动logits/模型与native面积/6组配对差值，均私有本地不入Git。完整软Mask保留margin接近原始而单peak保留变化大；ranked keep三面积均保留更多固定目标margin，remove5%较随机drop小、10/20%较大，混合结果不称普遍改善。等面积是模型网格，native面积/形状碎片度并非匹配；固定一个随机seed、adaptive case3/epoch，不是独立定位测试，不修改旧CPF1/3或标注对象0/10，临床有效性NOT_ESTABLISHED。

监督3.322033250秒/恢复3.328654666秒，41样本，采样RSS峰696025088 bytes、最低free fraction约0.56、swap增0、最大父间隔0.099830958秒。保留1条启动期telemetry缺样（原15秒grace内），不声称绝对峰/无缺样；CPU thermal测量未记录。累计输出预留35200040<64MiB、errors为空、STOP不存在、stdout/stderr0 bytes；自有组退出/设备恢复事件、三已知PID退出与原cpu/mps/serial锁空闲核对完成，未向未知进程发信号。原24源码/21runtime和旧R77/CLI失败收据/STOP/5F/归档dispatch SHA均保全，旧actual=null不回填。

本次科学权限已消费，不补用余下4F或重跑。负责人明确人工另约，MVP所有服务/浏览器/显示/演练/录制0，人工NOT_RUN、演练0、医院冻结NOT_RUN；仅必要原文档及双日志本地提交，无push/状态writer/总控两表修改，由主控读取实际索引汇总。


## 2026-10-15｜R92独立R18研究产物消费者与数值页｜工程/元数据完成，医学空间NOT_RUN

原INTEGRATION工作树/codex/epi-next-integration-20261009，起点HEAD `0ac9a2ac11f91814b8a9b294e2b2c7098a76911a`，tracked/untracked初始干净、原ignored研究资产保留。全文核验负责人R92 SHA5614adac…；权威revision91/ad29d070…与writer COMMITTED一致/pending0，只读未写。无可用独立QA代理，本线完成有界实现与验证。

新增r18_research_artifact.py、独立research_review CLI/HTML及生成fixture/测试，不改旧前端/接口/SLICE验证器。按ENC实际R92_R18_SLICE_CONTRIBUTIONS_V1适配，不要求另一生产schema；只读已明确转交贡献JSON94cb4bc0…与成功cache JSONfe19d5f8…，严格record/source_group/context/feature/geometry/split/label join，60组绑定整bag模型输入hash+原8native_Z，不伪造逐片hash。raw/8加数另加bias与bias-included component均值两种单位分开；signed保留，正半轴仅显示；tie按R91 Normal/argmax-first，固定FP64策略c72df980…/1e-8+1e-10，拒绝caller大tol。

实际生成私有规范化JSON和真实静态数值HTML，但未打开真实页面。60组120 logits元数据算术重建最大误差7.105427357601002e-15；3来源弱标签错分均COVID，专家切片标签UNKNOWN，不重算分类成绩、不作病灶结论。现GAP [8,512,1,1,1]无空间图，CAM NOT_RUN，拒绝reshape伪图；新head R91 5c003668…与旧case3 E2分链。当前输入SHA是whole-bag模型输入，不是native CT；个体DICOM身份映射未导出，6 NONCONFORMANT/54 NOT_EVALUATED不重评。

生成回归20 tests PASS0.06s；webapp-testing静态file页面桌面/390宽度6项交互检查PASS，单位切换/正负与正半轴/错分/等logit/缺项/追溯均覆盖，浏览器关闭、页面异常/外部请求0、无img/canvas/iframe，截图仅GENERATED。真实页面浏览NOT_RUN，不启动任何服务；本线模型调用/数组/权重/CT/医学图读取0。正式每次消费2个JSON（额外cache1），初次及受影响代码最终发布分别读取同两文件，字段核查也读同一贡献JSON；JSON算术属于实际计算，不称“没有计算”。

契约及完整正常分支/0F预算与缺口在research/next-hospital-20261014/reports/r92_integration/CONSUMER_CONTRACT_V1.md；源码提交后RESULT_INDEX登记实际commit与产物SHA。真实逐组数值/HTML只存`.local/r92-research-review-20261015-01`，不进Git。原MVP66/候选197源引用全部MATCH，不启动MVP/真实浏览器/录屏，不新建worktree/queue/Job，不跨树写、不push或改总控state/两表。未来CAM/标签/新留出等请求由主控统一，人工另约、医院冻结NOT_RUN。


## 2026-10-15｜INT向首席汇总与最终验收操作准备（未执行）

分支 `codex/epi-next-integration-20261009`，工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`，开发前/代码基线 `1085db4de11f622398aaf63f5e8fe3a5db4ff700`；R92受测源码 `596ef5eab6c5eb267cfa67ffbec198122eab040a`。新增本地 `hospital-release/20261015-chief-handoff/`，只索引既有真实技术/JSON执行证据和SPEC步骤；交付提交可由本节Git历史及发给首席的完整SHA解析，不改变代码或医学资产。

原R92索引SHA `e777d6afc6694c961ff7a1fc2cc32d6600a522c0ecfae88a0ed54b45a7b3aeb5`记录20项生成单测/6项生成页面检查、60组/120 logits元数据核对；不扩展为真实医学页面、空间CAM或临床验收。原64-only技术PASS单独保留。DATA commit `271b2203318602ea0839aa5e4f25a60fc8bae8a4`与固定新A请求 `2a776985783bbd3a9d8a1fdd9bc2a5f03f430b4a9ce807c0cfcad8ecedb8cd4f`的只读评审确认原A0/FD问题闭合；只给固定请求有范围工程结论，任意source_bindings check-only及未测CLI/queue限制保留，未执行A或重扫归档。

本轮实际验证为六份报告引用哈希、105个Python源码与四个控制JSON绑定；2个.so、inventory/payload/真实资产未重新读取。交付步骤细化逐例目视、同配置三轮完整演练、可选视频录制/完整播放/回退，actual=null、演练0、医院默认未定、医院冻结NOT_RUN；对应批准前不启动。首席汇总、钟佳桦最终决定，日期不倒填。manifest触发文档检查要求，已同步本记录及工程日志；未推送/部署/更改总控状态。


## 2026-10-15｜R103 INT真实元数据消费与研究接缝（无新医学执行）

分支 `codex/epi-next-integration-20261009`，工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`，前HEAD `20a37701f44375af87b0767dd2593f9895ca7f1e`。负责人指令SHA `2bfd447ec957f980605e30b1e7f95d820e9d138435bf2e0f71c36942d702c137`已完整读取。INT负责接缝，总控汇总，钟佳桦最终决定；本次不写权威状态/批准。

新增独立 `EPI_NEXT_RESEARCH_METADATA_V1` adapter/validator及生成数据预览，复用原R92 Strict/Reference/JSON reader和研究CLI；旧GAP-only/SLICE E2/F0契约及旧MVP/64资产不改。A标签结构保持mapping UNKNOWN/null分母；B20组/160位置空间声明与已有R92 scalar60组经ENC固定8片控制JSON连接20开发组、160位置MATCH；C Normal_SOURCE原argmax目标/19响应/未校准候选与D旧模型四格分别保留，不将空候选解释为无病灶。保留缺逐片输入SHA、C缺精确head及医学参考UNKNOWN。

实际证据：四R102科学JSON源SHA核对及消费；ENC控制SHA02e1a3a0e45f95d225ed59735d2c5900ec80b15c69a3aa6b9228b086855e2f02、R92贡献源SHA94cb4bc0c769fda0c93a89602dc4f451eeabef5ae87729d76379dda149ea40d9；连接按group/head/geometry/fixed8/saved logits，不读取所引资产。45项定向测试PASS（25新+20原R92），两个最终生成页面各5项PASS、pageerror/外部请求0、浏览器已关闭。5份本地真实元数据输出按最终schema复验通过。

访问说明：C源JSON内嵌CAM/mask数组已随JSON解析，首轮字段发现读出过部分内嵌值；新adapter不访问/复制/计算/渲染该数组字段。不能写成完全未触及数组值。外部数组文件/CT/GT/权重读取0、模型调用0、医学页面/服务/人工演练/录屏0；正式消费未导入NumPy/Torch。没有重跑R102或旧技术任务，没有推送/部署。详细访问账本与复现入口见 `research/next-hospital-20261014/reports/r103_integration/CONSUMPTION_REPORT_V1.md`；精确源码与证据SHA由单一RESULT_INDEX_V1.json索引。

未完成：DATA/LOC/ENC正式新版医学配对/评价schema待总控转交；未知schema拒绝，配对/临床/产品验收NOT_RUN，原技术PASS与人工DEFERRED/医院冻结NOT_RUN保持。文档同步和diff在交付前检查；代码完整提交SHA由本节Git历史及随后精确索引绑定，不预填执行或冻结。

R103源码与报告已本地提交 `6df3dd8124707dc09126f41152edd3c3358ba66c`；新增单一 `research/next-hospital-20261014/reports/r103_integration/RESULT_INDEX_V1.json`，绑定实际JSON消费/20组160位置连接、45项生成测试、最终两页10项检查及生成截图SHA。未扩展执行范围；新增正式医学schema仍待交付，医院冻结NOT_RUN。


## 2026-10-16｜INT文献深读与独立感染Mask空间研究接口

原分支 `codex/epi-next-integration-20261009`、工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`，前HEAD `3e44dc33882393576029593bb5c13fb4e82856b5`。本轮负责人限定为公开文献/作者代码只读、原线独立模块及合成CPU工程；不得读新CT/标签payload/真实内嵌CAM数组、模型训练或新forward。当前state106 SHA471157999c6ba6e3eecc8257d8f3e351dca1437be42886c212a7b8b4d7e608e7与writer COMMITTED事件匹配，未写总状态。

本地增量仅 `epilocate_next/infection_overlay_research_v1.py` 与新增 `qa/test_infection_overlay_research_v1.py`，原MVP/64-only、R18/CT-FM/Ridge/CPF及旧执行源码未改。独立几何元数据/数组函数明确ZYX/XYZ、RAS/LPS、mm、crop及7→224→native显示格中心、nearest resample coverage、同组同系列/网格绑定、完整/部分参考和GT提示门禁；不含真实file reader、模型或UI。显示格中心不能代替ResNet18特征lattice（名义stride32/offset0）或感受野边界。NIfTI1 sform-only/mm只是合成header兼容夹具，qform/NIfTI2/压缩/非仿射stack/跨库及真实体数据仍NOT_RUN，环境无nibabel，未安装依赖。

按总控分配，INT只拥有论文02/06/07/15；全文PDF、分隔页文本/源信息、中文15问笔记、作者固定commit源码/issue审查、技术矩阵、像素协议和最多一条Inf-Net候选都保存在私有 `literature_review_20261016/` 分配子目录，未提交全文或外部源码到Git。四正文已读；MedSAM补充下载SSL/HTML门失败未读，Total补充文字已读、20图页仅概览未逐点数值重算。PDF含失败残留30,989,904B，单篇和本线预算均满足；不下载权重/影像数据集。完整身份、DOI、作者、year及许可/版本冲突记录于source.json/notes，作者reported不能当项目结果。重要发现：Inf-Net是pixel/edge监督，WeakMedSAM含新训练与提示亲和/伪标签U-Net，GT提示交互对照不等于自动定位，肺ROI不等于感染mask。

INT先保存TEST_PLAN/READY，未自行跑测试。总控按计划SHAe4bf086c12aaa767f14003fb150a4479260c488e5725d6b44b85db2be3d366bd串行运行新增19项，PASS_GENERATED_ONLY；外层0.218677s、采样峰值RSS47,939,584B，pytest19 passed in0.06s，精确来源为私有checks/INT_SERIAL_TEST_RESULT_V1.json及日志，测试后源码/计划SHA MATCH。旧57/58/旧8未重跑，医学载荷/模型/医学页/服务/演练/录屏0。仅语法、PDF/文件、文档核查由INT自行进行；不再重跑测试。

未完成与下一步：MedSAM补充未取得；WeakMedSAM许可、paper/code的prompt网格/编码次数/归一化差异未实测消解；真实reference/数据权重SHA/预处理与预训练重叠仍需总控/DATA交付。Inf-Net只是一条BLOCKED前置候选，最多2例×固定8片/16F、0训练，不是批准或可执行新请求。像素评价与临床结果NOT_RUN；原技术PASS/人工DEFERRED与医院冻结NOT_RUN保留。最终交付索引位于私有evidence/INT_COMPACT_INDEX_V1.json，绑定完整本地提交及文件SHA；不跨线程发信，不push/merge/deploy/写state。


## 2026-10-16｜INT执行索引交首席及最终人工验收记录准备

负责人本会话明确要求把本次执行索引、Git SHA、验收摘要与未完成项交首席汇总，并继续准备人工目视、三次最终演练及备用录屏；未获对应批准不执行。此为新的明确交接授权，先前文献任务“不跨线程发信”的当时边界不被改写。复用现有总控，不创建会话、队列、allowlist或并行状态。

工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`、分支 `codex/epi-next-integration-20261009`；交接前代码HEAD `6514dbf733ea18cd78a121f52a5664197842e8b0`，起始tracked/untracked为空，ignored本地资产保持。权威revision106 SHA `471157999c6ba6e3eecc8257d8f3e351dca1437be42886c212a7b8b4d7e608e7`与writer最后COMMITTED匹配；仅只读观察，不调用writer或声称完成新的reconcile。

新增 `hospital-release/20261016-chief-handoff/` README、manifest及实际记录模板，复用10月15日详细步骤而不改UI/运行时。模板包含共用批准/版本/素材/设备绑定、三例逐层目视、三个同配置独立完整流程、可选录屏全片播放/切换、停止/回退及最终负责人决定；所有实际项NOT_RUN/null，演练计数0，不预造记录。不复用已消费execute命令；未知事务先对账，未知进程不终止。

核对原demo64执行索引SHA `820bb019bd785f4e882d01d35bb5961c5da38f4e2d2d7af0bdd712f30f8aab94`、技术收据 `02377afccc9cd0a71f7b53cf93d0895baa85d2ac03c96eed0a6d0dc1f5504b7e`、退出收据及V3 candidate均MATCH，维持PASS_TECHNICAL_ONLY；未重新核对全部旧资产闭包。R103索引SHA `d8fbd8d5a8c5cdc8304391bb6abeb3b93042acd833e35e9a8b57d5a63caa4b36`及其源码/测试日志绑定MATCH；保留历史C JSON曾内嵌CAM/mask的访问说明。本轮19项合成PASS来自总控已存收据（SHA `f5aafbd47eb1ee6b3ce1d391d4a052120c3e6d0cfd28590b88c3c518060d3abb`），未重跑测试。补齐私有INT_COMPACT_INDEX_V1.json（SHA `0610e84a71ff1f8e8e8e5137b4b99a95fed792b02add1698f7051b56a6d5cc6b`），仅收口原文献/合成结果，四篇元数据/正文哈希、15问结构、下载预算与测试计划源码核对PASS。

本次新增真实影像/数组/权重访问、模型调用、医学页面/服务、演练/录制均0，不push/merge/deploy、不更新权威状态。人工DEFERRED_BY_OWNER_NOT_RUN、最终演练0、录屏OPTIONAL_NOT_PRODUCED、医院批准NOT_APPROVED、冻结NOT_RUN；默认算法null，最终由钟佳桦决定。本包完整提交SHA及实际发送结果由交接消息绑定；文档同步检查与diff检查后再提交，仅记录本次真实结果。


## 2026-10-16｜R108 INT医学评价几何与Inf-Net无权重研究接口

负责人R108完整指令已读，原INT分支/worktree，前HEAD `d86097acfcd77652e384568cd63141e1864cf35f`；起始tracked/untracked干净，ignored原位保留。权威revision107 SHA `c58ec5fda876d04aa7601fb3febb8458680fb00798d900688560acc81cdb428f`与最后COMMITTED一致；INT不写状态。复用epilocate-project/Ponytail与既有Inf-Net审计，不扩展综述，不安装依赖。

新增独立 `epilocate_next/r108_research_geometry.py` 和 `qa/test_r108_research_geometry.py`。NIfTI-1 header bytes支持大小端、qform/sform、qfac/quaternion、RAS/LPS与scaling元数据，q/s frame或世界坐标冲突明确拒绝；不读取路径/像素。轴置换flip、crop/resize中心及逆坐标、覆盖域和部分/未知参考状态供DATA/LOC使用；不复制DATA identity或LOC Dice实现。metadata grid允许大体积尺寸声明但不分配整卷数组，旧R107模块/上限不改；Inf-Net native数组适配仍限单片≤1,048,576像素。单位/类型/有效仿射门禁显式，无原HU证明不从窗化值反推。

独立bundle区分CT/GT/CAM/E1/E2/B0/B1/InfNet的method/version/target/evidence/native grid/asset SHA，拒绝跨case混入、解释图混命名概率及临床声明；无MVP导入路径。Inf-Net只适配调用方生成的352² logits，经crop/resize双线性回native，保留原logits、candidate/coverage/编码SHA和runtime身份，域外UNKNOWN；无权重/网络/真实模型入口，许可/重叠/HU/预处理未确认及真实未授权分支BLOCKED。模型runtime=null，不伪报运行耗时/文件路径。已有Inf-Net是监督分割适配，不作为R18定位提升或原创。

本机仅查已安装能力，nibabel未安装，未安装库。跨库生成NIfTI save/load/scaling往返已有条件测试，但当前预计skip，不得报告跨库通过。NIfTI2/ni1/gzip载荷、未知单位、非仿射stack、真实医学文件/整卷与临床评价仍未支持或NOT_RUN。旧R18/head/E1/E2/GT/MVP/数据库/64-only入口均不改，V4未执行。

AST语法解析通过；静态枚举新增27cases（当前预计26可执行+1 nibabel条件skip）。尚未由INT运行/collect测试；已将精确TEST_PLAN/READY及源码SHA交总控统一串行验收。计划SHA `2b420453ccd368f3eb7a8a83d7aa13b45026010cb95dd685dec1c66b8643184b`，CPU1、全套60秒/RSS512MiB/输出2MiB。READY后源码冻结，不重跑旧32/57/58/8/19；测试结果须引用总控实际收据，不能从AST或准备状态推PASS。

报告、源绑定与最终COMPACT_INDEX保存在私有 `r108-medical-localization-20261016/INT/`，本地完整代码提交SHA由索引绑定。真实Index/NPY/CT/GT/weights访问、模型前向/训练/优化、HTTP/下载/安装/远程GPU/医学服务或页面/医院/录屏均0。只总控最终统一登记；没有push/merge/deploy。交付前执行显式base文档同步与diff检查；医学参考验证、模型兼容性和医院冻结不由本包确立。


## 2026-10-16｜R108 INT总控串行合成验收收口

原INT工作树/分支不变，收口前HEAD及受测源提交 `a381e80af4bfffad5e42b1a36c2679e6ee3ba7b9`，工作树起始干净，ignored保留。本次只更新双日志及私有R108/INT报告/index，不改冻结源码/测试/旧依赖或其他线文件。

总控实际INT_v1收据为 `r108-medical-localization-20261016/INT/CHIEF_TEST_RESULT_V1.json`，完整日志 `checks/INT_v1.log`（SHA `3da25762b1c8c17cbc101d0b65d9d654ae614fcae55dfdac8601e8c3f5422651`）。26 passed、1 skipped，pytest0.08s，监控0.2043562079925323s；采样进程组RSS最大47,284,224B，5次采样，不代表绝对峰值或OS硬RSS限制。exit0，无停止原因。计划SHA `2b420453ccd368f3eb7a8a83d7aa13b45026010cb95dd685dec1c66b8643184b`、三源码/解释器/日志绑定MATCH。INT未运行或collect测试，不重跑旧32/57/58/8/19。

证据只为ENGINEERING_PASS合成工程。nibabel缺失的唯一条件case已skip，跨库仍NOT_RUN；公开NIfTI真实几何、医学载荷、实际HU/完整体数据及临床指标未验证。`geometry_coverage_report`始终identity_verified=False；调用者须提供DATA正式registry中CT/GT同病例/患者或来源组、Study/Series、输入/GT SHA、native geometry及reference extent/coverage绑定。shape或affine相同不能证明医学对象身份，INT不自行生成医学参考分母，LOC负责后续指标。

真实Inf-Net许可/重叠/352预处理及HU门禁未解除；真实模型仍BLOCKED。此次真实数据/模型/网络下载/安装/医院/录屏/state写入均0，旧64-only/MVP及历史资产保持。私有COMPACT_INDEX追加实际总控收据和最终文档提交，准备态索引保留快照；只总控统一登记。文档检查及diff检查后本地提交，不push/merge/deploy。


## 2026-10-16｜R112 INT隔离依赖与唯一跨库用例实际失败

原INT工作树/分支，前HEAD `1393451a471fc1355804f2366138d0fb2f58a0b9`；总控在DATA任务finished后明确释放唯一CPU1/IO串行窗口。按已审计划SHA `16e552497c2ddea640ec46097e94df5d2f1c66c8c943e5b818fa3dbf7fb05f2e`一次执行，无自动重试/版本替换。仅固定官方PyPI2元数据GET+2wheel GET，正文3,348,198B，nibabel5.3.2和importlib_resources6.5.2经官方SHA/依赖核验后安装本线.local隔离target，不改共享.venv或R111绑定文件。wheel锁/命令/日志留私有R112/INTEGRATION目录，未提交第三方包。

setup8.2910s、安装exit0。唯一原R108跨库node实际1FAILED/0skip，pytest0.28s、监控0.42406s、采样group RSS72,302,592B；总时9.10502s。RSS口径为自进程及采样进程组，非全树硬峰值。结果收据SHA `6f94917e8b6ac8f5817351d9dd4135699a8b8038f53e7ca123a003c3cf6423cc`、失败日志SHA `b372a84f79549ea68627132f865f002a10769822d86a15c447071454d823fede`；wrapper保存收据后exit0不等于pytest通过，实际test exit1。旧26项/其他全套未重跑，源码/测试不改。已马上向总控报告失败及串行窗口释放。

失败位于qa/test_r108_research_geometry.py:187：初次affine与int16*slope/inter读值精确断言已过；再次保存后的affine一致，但未固定输出编码的int16再保存产生量化，scaled数组不完全相等。已只读安装源码analyze.py/arraywriters.py确认自动缩放路径；不额外跑诊断，不宣称实际最大误差、后续header断言或整个跨库PASS。后续最小建议为独立生成float64/identity scaling无损roundtrip，保留原失败、不降低容差；未实施或执行，须由总控另行安排新工程复验。

R111请求/runtime/15源码/stdlib哈希MATCH；共享.venv 36,979文件stat清单前后一致，base无overlay仍无nibabel，旧MVP/64-only/历史Result不改。真实医学文件/权重/模型、医院/录屏0。跨库缺项更新为TEST_FAILED，真实医学几何/HU/CT-GT资格仍未验证；几何相同不能自行建立DATA身份分母。双日志及diff显式base检查后提交本轮材料；最终私有COMPACT_INDEX绑定执行/失败/依赖与文档SHA，不写权威state、不push/merge/deploy。


### R112原失败的最小纠正准备（当前未运行）

按总控后续指令，仅依据既有失败日志与库源码核查，新增独立 `qa/test_r112_nifti_crosslib.py`（SHA `24358941c2b76d093ce9d017f749ae2c25065ba1bb10110003a54655f3dd15d6`）。不修改原失败test、研究实现、R111/共享runtime。新case把重保存合同明确为float64+slope1/inter0，初始int16缩放和全部数组/affine/q/s元数据继续严格相等，不降低容差或医学门限。

只做AST解析；精确单项计划 `CORRECTIVE_TEST_PLAN_V2.json` SHA `76d0ec1d4ca52388764e94234570a348099de338777165227ab86921cff1a376` 已交总控，CPU1/60秒/RSS512MiB/输出2MiB、0GET/0install、复用隔离包。当前ENC持有窗口，actual_test_runs=0，等待新串行窗口；不能将修正计划当已复验或覆盖原FAILED收据。冻结新test源码供总控审阅、排队，原医学资格仍未验证。


## 2026-10-16｜R112明确float64编码的新单项实际通过

原INT分支/worktree，文档收口前HEAD `84a73884fcc6335a5ca96f5e9af4b5865040179b`。总控确认DATA19项终止并释放新的唯一串行窗口后，按CORRECTIVE_TEST_PLAN_V2 SHA `76d0ec1d4ca52388764e94234570a348099de338777165227ab86921cff1a376`，只执行新增 `qa/test_r112_nifti_crosslib.py` 的1case一次。1 passed/0skip，pytest0.22s、监控0.35236637500929646s、采样group RSS73,285,632B（非绝对峰值或OS硬RSS保证），exit0/无stop。实际收据SHA `892359749dbc6eeffd1112fabd564329c9d5ab45fe775e8ea3af00ce1324de62`，完整命令/日志在私有R112/INTEGRATION目录，计划及源/日志SHA已核MATCH。

源int16+slope2/inter-1024读取及新显式float64+slope1/inter0重保存后的数组/affine/q/s code/scaling/header均严格相等；没有放宽容差、医学阈值或修改原研究实现。仅GENERATED_EXPLICIT_FLOAT64_ONLY工程通过，原默认整数resave失败的test/收据/日志/生成文件保持FAILED且未重跑，不能改成整个历史跨库套件通过。真实公开NIfTI/医学身份/HU/体数据与医学评价资格仍NOT_VERIFIED。

0GET/0install/0medical/0model，旧26项和其他历史全套未执行。隔离依赖不变；R111/解释器/源绑定MATCH，共享.venv stat清单前后相同，base仍无nibabel。自有测试进程结束后已立即向总控释放窗口。本次只补双日志及私有实际报告/index；显式base/range文档与diff检查后本地提交，不push/merge/deploy、不写状态。旧64-only/MVP/历史Result保持，医院冻结NOT_RUN；有界工作完成后停止，不扩展测试。


## 2026-10-16｜R122 INT独立CT/Mask/CAM空间叠加准备与生成验收

原工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`、分支 `codex/epi-next-integration-20261009`，前HEAD `d0fd275629c54adfcc31b90502a5125977dc8e89`，起始tracked/untracked干净、ignored保留。核对总控OWNER_SCOPE_RECORD和权威revision121 SHA `a1162e864809e0ca0f4251c931a25dd27d172234f590248876667d27e96410e4`/COMMITTED一致。真实首例001仍仅继承既有元数据；未扫描ZIP、重哈希全包、读取成员或体素。沿用epilocate-project/Ponytail及webapp-testing的必要合成检查，不扩大产品UI。

先交DATA可复用的R112隔离nibabel5.3.2/importlib_resources6.5.2 runtime描述（SHA `04b2d12eed52ecd932703fe2d741167d1a320b9260dfadc42b4aa1bc84c9e0ef`）：准确解释器/PYTHONPATH、依赖399文件逐项SHA与闭包 `8f9760eb3a708b24e2d6ca4581f52bffbf3f53c151af712db49a7a94f127455c`。无安装/下载，不改共享环境；引用原明确float64合成PASS和整数resave失败边界，不授权真实成员访问。

新增独立 `epilocate_next/r122_spatial_overlay.py`、小HTML模板、9case新单测及极小browser driver。只接生成NIfTI/in-memory契约，CLI无真实输入入口；复用R108 header/typed bundle与nibabel canonical重排，CT/GT/CAM在native同世界空间后才叠加。非对称fixture验证轴置换/翻转、反向Z、raw int16缩放、canonical<->native逆矩阵与display行翻转；UI显示raw/native/canonical/display、RAS/LPS与source/method/version/target/SHA/PASS/UNKNOWN。参考为合成医生Mask接口夹具，非真实医生判读；signed CAM非感染概率，缺CAM为UNKNOWN/null，几何不符不绘制，部分参考域外UNKNOWN。identity_verified=False，不建立医学分母，不改旧MVP/数据库/历史Result。

按TEST_PLAN_V1 SHA `2695720bfb730d65ec7f03a11d96a84b88447cb8a45b6b2ca77c179c4b9d6075`，取得现有CPU/wave1.serial两锁独占窗口运行，9新单测PASS（pytest0.43s，监控0.5787067500059493s，采样monitor+后代RSS113,278,976B）。3必要UI断言的Chrome启动被512MiB cap停止（采样690,798,592B）；经总控仅browser资源计划V2 SHA `2071b4ef1b90f414442f2d01be91575457d3328d386ce3b579a8809361f64f74`将上限明确为1GiB后再启动一次，采样1,163,739,136B仍触cap停止。两次失败exit-9，分别7.4581s/3.5813s，原目录/收据/空日志全部保留。9单测未重跑；3UI标NOT_COMPLETED_RESOURCE_LIMIT，不能写界面PASS/3FAIL或医疗/空间失败。RSS为动态采样，非硬OS绝对峰值，预停线存在采样超调。

只对本次PID/start身份匹配子进程清理，剩余=[]；两锁与窗口已立即释放交其他线。总控指示停止浏览器运行/探索，未第三次运行。静态HTML/JSON快照和新源码保留为实施证据，不是显示/医院验收。最终源/解释器/399隔离文件及旧MVP driver/V3 candidate控制引用SHA MATCH；医学影像资产本身未重新哈希或读取。无服务/安装/下载/模型/真实页面/截图录屏；浏览器没有完成完整请求观察，不能声称整浏览器背景网络为0。

私有 `r122-first-case-qualification-preparation-20261016/INTEGRATION/` 保存runtime合同、输入契约、两计划、实际收据、报告与最终COMPACT_INDEX。提交只含本线四个新文件和双日志；显式base文档/diff检查后本地提交，不push/merge/写权威state。真实CT/GT身份、HU、参考完整性、真实CAM/模型与临床评价仍NOT_VERIFIED/NOT_RUN，旧64-only技术PASS和医院冻结NOT_RUN保持。当前有界任务收口后停止，不新增浏览器/产品或算法范围。
