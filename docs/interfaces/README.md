# EpiLocate 前后端接口交接包

此目录始于 2026-09-26 的接口设计稿；当前集成分支已实现本机单切片 DICOM Baseline 与 Stage 1 遮挡。先看 `p0_real_integration.md` 和 `p0_verification_record.md` 的实际范围，再看设计字段。B 分支未改写。

| 文件 | 用途 |
| --- | --- |
| `repository_interface_audit.md` | 真实仓库、远端分支、已实现与未实现能力 |
| `algorithm_api_contract.md` | 字段语义、数据来源、坐标、状态、错误与请求/响应样例 |
| `algorithm_api_contract.yaml` | OpenAPI 3.1 目标契约，路径上标有 `x-implementation-status` |
| `p0_real_integration.md` | 当前可运行接口、合成 DICOM 向量和复现步骤 |
| `p0_verification_record.md` | HTTP/Gradio、离线一致性与未完成范围的实测记录 |
| `frontend_handoff.md` | 九页前端交互和图层对齐要求 |
| `backend_handoff.md` | Adapter、模型缓存、job、存储、授权与数据库字段 |
| `implementation_roadmap.md` | P0/P1/P2 依赖和验收 |
| `team_handoff_messages.md` | 两份可直接复制的飞书消息 |
| `fixtures/` | synthetic JSON 与完全合成的 CT DICOM；不含患者或正式实验结果 |

冻结验证集的新增探索性分析位于 `analysis/stage1_validation_exploratory_v1/report.md`。源 formal validation 161 项、checkpoint 和冻结 protocol/config 未改动。
