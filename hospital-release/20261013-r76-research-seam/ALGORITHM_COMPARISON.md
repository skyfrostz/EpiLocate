# 算法版本对照入口｜R76

本表区分产品默认、生成验证和真实验证。新接缝不改变旧结果含义，也不把热图、响应分数或来源标签显示为“病灶概率”。

| 版本 | 当前角色 | 本次接入与证据 | 不能据此声称 |
| --- | --- | --- | --- |
| FrozenBaseline | 当前本机演示默认候选；旧 v16 保持回退目标 | 既有三条真实开发流程和 R71 只读恢复证据，见 [v16 演示清单](../20261011-real-mvp-acceptance-v16/DEMO_CHECKLIST_OCT14_20261012.md) | 医院用途已获批、临床有效、完整 Series 空间验证通过 |
| E1 | R76 未注册为 E1 | 本次不改名、不复用旧 Occlusion 入口 | 旧 Occlusion16/32/64 就是 E1 |
| E2 | 实验版本 | LOC v5 目标契约接缝、保存结果消费和显示面板通过生成测试；后端实时实验 app 仍需显式装配 | 真实模型已运行、真实 DICOM 热图已通过空间验证、医院已验收 |
| F0 | 实验版本 | ENC v4 保存结果消费；以生成缓存/头参数/评价记录核验 SHA、日志重建、有符号贡献和名义 native/LPS 变换 | 真实 encoder/head/cache 已交付、三维粗图是病灶分割或概率 |
| F1 | 未完成 | 未进入本次应用注册 | 可运行、已完成临床验证或可用于医院默认 |

E2 保存的结果单独记录 `explanation_target` 和原始 `predicted_class`。`DECLARED_FIXED` 使用请求声明类别，允许它不同于原始预测类别；`ORIGINAL_ARGMAX_FIXED` 使用原始 logits 的首个 argmax 类别。实际 `resolved_class` 必须等于声明的 `declared_class`，不一致时拒绝新结果。来源标签保留 `SLICE`、`CASE`、`BAG` 或 `SOURCE_GROUP` 范围，不把 CASE/BAG 标签提升为切片真值。优化目标 `ALL_LOGITS` 与描述响应 `FIXED_TARGET_LOGIT_MARGIN` 分开显示。

F0 消费 ENC v4 的预计算保存材料，不调用 encoder/head 模型；接缝只做有界文件读取、SHA/身份校验、FP64 数值重建及坐标正逆变换核验。输出保留正负 4×4×4 来源分类贡献和 effective bias 恒等式；不做 ReLU、不平滑、不转成病灶概率或精细分割。

现有 E2 selected-fidelity 记录仍按原状态保留：其应用请求 target 0 与真实原始 argmax/fixed target 1 不一致，属于 `NOT_FULL_PASS_TARGET_CLASS_METADATA_MISMATCH`。R76 为新版本增加拒绝门，不回写旧收据。
