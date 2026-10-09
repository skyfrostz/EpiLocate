# 展示流程与回退

以下真实医院流程尚未执行，不得提前记录 PASS。10 月 13–14 日由首席算法工程师组织，10 月 14 日由钟佳桦审阅最终冻结。

1. 核验 source Git SHA、模型/算法/预处理/配置/预算 SHA、正式医院数据 handoff 与获准本地资产 SHA。若缺失或不一致，记录 BLOCKED，不进入现场展示候选。
2. 用现有 EpiLocate 载入已批准原始脱敏 CT，核验左右、顺序、Study/Series/SOP 与显示范围。三例研发 proposal 不能自动当医院 allowlist。
3. 显式标 LIVE 或 PRECOMPUTED，并展示实际模型/版本、原始 logits/未校准分数、证据类型与运行时间。CAM、HSPI、遮挡响应和专家 GT 分别命名。
4. 查看候选的八角点 LPS 坐标、原始 SOP、空间 ledger 与六项实际映射证据；无法验证即禁 overlay/候选展示。不可通过放宽既有前端 geometry 白名单强行叠加。
5. 保存结果并刷新、重新打开，核对 run/请求/资产 SHA。刷新只读取已保存结果，未知事务对账，不重提模型任务。
6. 实测 NO_RELIABLE_RESPONSE、PARTIAL_BUDGET、FAILED、BLOCKED 和 NOT RUN。无可靠响应不解释为正常 CT；部分预算与失败不隐藏。
7. 实际回退 FrozenBaseline 及 16/32/64 Occlusion，核验旧资产未被覆盖、旧协议行为与显示正确。
8. 相同冻结版本完成三次连续真实完整流程，无阻断故障；保留全部尝试和失败，不能只选三条成功日志。
9. 在获准本地目录保留实际真实预计算结果及全部 SHA，录制并实际播放备用录屏；负责人批准后才对外展示。

## 当前可用的配置切换与回退

算法对照入口见 README。生成一个新的不可覆盖 legacy flag：

```sh
PYTHONPATH=research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.hospital_release --manifest hospital-release/20261009-integration-v1/manifest.json --algorithm FrozenBaseline --output-flag hospital-release/20261009-integration-v1/.local/flags/rollback-v1.json
```

将 FrozenBaseline 替换为 Occlusion16、Occlusion32、Occlusion64 可分别保留尺度身份。新 flag 路径须独立，不覆盖历史配置；`dispatch_selected` 校验其 manifest SHA 并交给原 handler。
默认无 flag 继续原 FrozenBaseline handler。该接缝尚未安装为生产 endpoint；不宣称 CLI 生成 flag 已改变线上算法。
E1/E2/F0/F1 在当前 manifest 均拒绝医院选择，直到正式模型与八项真实证据到齐。临时研究单测可直接运行独立侧车，不能代替医院选版。

## 发生故障时

- 设备忙：BLOCKED，保留其他任务；INTEGRATION 不抢 ENCODER 的 MPS，不终止未知进程。
- 提交结果未知：先查原 output_root/run_id 下 receipt 并逐项核对 SHA；COMMITTED 只重放相同请求。缺收据、CORRUPT、CONFLICT 或 global intent 留存则停止自动重提并交总控对账。
- 新算法不可用：切换已验收旧 handler，或明确 PRECOMPUTED 展示已验证真实收据；无合格备用结果则 NO-GO，不生成假输出。
- 空间校验失败：结果保留诊断，移出医院候选；不得凭热图视觉效果决定通过。

最终本地交付包包含真实三次命令/日志、版本与资产清单、预计算及录屏引用、未完成事项。真实影像/标注/权重留获准本地存储，不自动上传或提交 Git。
