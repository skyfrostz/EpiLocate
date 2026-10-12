# 演示流程与回退方法

## 10 月 15 日演示准备

1. 当前唯一可复用的系统演示基线是原 FrozenBaseline/v16 本机只读恢复包。流程、登录/刷新检查和操作入口见 [既有演示清单](../20261011-real-mvp-acceptance-v16/DEMO_CHECKLIST_OCT14_20261012.md)；R71 真实只读技术证据见 [恢复验收摘要](../20261011-real-mvp-acceptance-v16/READONLY_R71_REAL_ACCEPTANCE_20261012.json)。本次没有启动服务或再次运行其命令。
2. 负责人尚未决定原三张本地影像/结果能否用于医院现场显示、截图或录屏。决定到达前，只准备不含像素的系统结构与算法状态讲解；不要把本地用途扩展为医院展示许可。
3. 若负责人确认材料用途，仍须以本包的算法对照表向观众说明：FrozenBaseline 是原默认候选；E2/F0 是生成测试通过、真实算法验收未完成的实验版本；E1 未注册，F1 未完成。禁止把任何响应称为“病灶概率”。
4. 不在本次 R76 代码包中启用新 Worker、提交真实病例任务或打开远程 RTX 3090。实际新算法演示需要后续明确的数据/模型 handoff 和负责人验收，不可用本地生成 fixture 代替。

## 回退

- 新结果接缝位于独立的 `backend_v2.research_application.create_research_app` 工厂；基础 `backend_v2.api.app:app` 不会自动注册它，next-algorithm 默认开关仍需显式启用。保持该开关关闭且不装配新 handler 时，旧入口继续使用原流程。
- 前端只在结果含 `diagnostics.research_contract` 时显示研究面板；普通旧结果不显示该面板。
- 如需现场恢复，回到已绑定的 v16 只读包和其原操作清单，按该包已有恢复步骤操作。不要覆盖、删除或重命名新结果/旧资产，也不要重放已消费的原任务命令。
- 此接缝无数据库迁移，不改 FrozenBaseline、GT-v1、A/B/C、旧 Occlusion16/32/64 或 v16 静态包。回退只切回原应用与版本入口，不需要改写历史结果。

## 对照和交付

- 算法状态及语义：[`ALGORITHM_COMPARISON.md`](ALGORITHM_COMPARISON.md)
- 验收边界：[`ACCEPTANCE_REPORT.md`](ACCEPTANCE_REPORT.md)
- 负责人决定前，最终医院冻结状态维持 **NOT RUN**。
