# 验收报告｜集成候选

日期：2026-10-09，Asia/Shanghai。环境：本机 `.venv` Python、CPU 合成测试；无真实 CT 模型计算、MPS 或远程任务。
实际受测代码提交、命令、环境、日志、数量及 SHA 以 `evidence/verification.json` 和 manifest 为准。

| 医院验收项 | 状态 | 实际证据缺口 |
| --- | --- | --- |
| 1 原始脱敏 CT 显示正确 | NOT RUN | 正式空间 handoff 与真实浏览器显示 |
| 2 真实模型结果可追溯 | NOT RUN | 总控转交精确模型、真实 run、logits 与收据 |
| 3 热图与影像空间正确 | NOT RUN | 六项真实映射证据；合成矩阵/生成 DICOM 不能替代 |
| 4 保存及刷新恢复 | NOT RUN | 合成侧车重放已测试；真实应用链恢复待测 |
| 5 失败状态清晰 | NOT RUN | 六状态合同与候选阻断已测试；真实浏览器待测 |
| 6 旧版可回退 | NOT RUN | callback 保持旧协议/flag不可覆盖已测试；真实应用回退待测 |
| 7 连续三次真实流程无阻断故障 | NOT RUN | 需要三条独立、连续的真实完整流程记录 |
| 8 真实预计算与备用录屏 | NOT RUN | 成功结果/全部资产 SHA、实际录屏及播放核验 |

真实流程总状态 `BLOCKED_BY_DATA_HANDOFF`：本地研发 allowlist 已由 DATA 发布；真实 GT-vNext、ordered SOP/affine/volume ledger 与接受后的模型运行适配器尚未转交。
医院默认算法待定；最终冻结 `NOT RUN`；医院对外展示尚未批准；临床验证 `NOT RUN`。

合成集成范围包括版本化 E1/E2/F0/F1、错误证据类型拒绝、六执行状态、左右/斜位/切片方向、不等 spacing、实际 HU/重采样、crop/resize 半像素约定、候选 SOP、全局设备锁、预算/故障计数、未知事务阻断、hash 重放、原协议 fallback 与未验收新算法拒绝。
测试中伪造的 LIVE_CASE 验收 JSON 只用于门禁单测，不保存为实际患者或医院证据。

准入要求相同 source commit、数据 handoff、模型、预处理、算法版本、参数、任务和预算 SHA；新算法须 ENGINEERING_ACCEPTED。
三次记录必须有独立 workflow_run_id、连续 sequence、全部六流程检查 PASS、blocking_faults=0。
预计算必须验证请求/结果和全部资产 SHA；回退必须是 PASS 和精确 legacy 算法；录屏必须有容器头及绑定其 SHA 的实际播放核验记录。
这些检查证明记录关联与完整性，真实影像正确性依赖实际运行/人工审阅，最终批准仅由钟佳桦作出。
