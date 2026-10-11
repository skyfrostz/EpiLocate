# 运行、演示与回退

本文件是预备操作手册。新真实launcher NOT_READY，实际医院演示/最终冻结 NOT RUN。现有RICORD DATA v3/Prepared2DInput已交付，加载代码可用；只有总控补齐新模型/科学结果/应用空间绑定和新的执行scope后，才可执行真实步骤。

1. 总控固定现有ModelVersion及独立实验model_id，提供完整ApplicationRequest、canonical digest、应用Worker ID、输入resolver和LOC/ENC handler绑定。Backend使用既有认证/Job/Attempt/lease。仅显式设置next_algorithms_enabled及两个绑定集合；前端实验提交设置VITE_NEXT_ALGORITHMS=true才显示，不改原主流程。
2. 输入Case/Study/Series/Slice、display SHA与native dimensions须对应用户自有READY记录。DICOM非合规源使用DATA的研究数组/sidecar；CTFM必须完整Series 64³及独立head，缺resolver即拒绝。不得临时repeat/reshape成2D任务。
3. 优先用E2-Q科学结果进行PRECOMPUTED回放，F0/B0/update0，明确原证据与原计算成本。不为证明应用再跑一遍E2-Q。真实保存Result/SHA后进入结果页，选择分开的Mask/gap/PSMI支持图层；partial/拒绝/空间未验证叠加关闭。实际路径/原值仍保全。
4. 刷新只读取原Result/资产，不调用模型。新POST同完整request返回原Job；未知submit结果查询/api/v2/workers/jobs/{job_id}/receipt，digest不同或未接受时停止并交总控对账。不得另造Job/Attempt重算，也不重播已消耗M0命令。
5. 医院批准配置上重复三次实际保存/恢复/展示流程，保留命令、每次Job/Result、资产SHA、空间审阅、失败和退出收据。生成测试不能替代。预计算备份及备用录屏需另外批准和实际制作。
6. 10月13–14日据真实可追溯结果选择默认；14日固定源/模型/config/data/资产SHA和已知限制。首席算法工程师汇总本地包给钟佳桦，由负责人决定PASS/CONDITIONAL PASS/NO-GO。当前默认null。

回退：关闭新提交开关，停止自己拥有的应用Worker发起新领取，保留其终态/partial及原资产；不终止未知进程。保留新结果表/sourcecheck，不自动downgrade有ALGORITHM数据的数据库。选择旧Baseline和16/32/64入口；其原2.0契约不变。M0历史source54ff1565f6c11a6deea873feab0a011e879528fb及既有frontend/.local/mvp-20261011-dist是快照恢复目标，复用原受保护结果需总控新增计算关闭的启动范围。没有reset/clean/服务部署或历史覆盖。

算法对照入口沿用research/next-hospital-20261014/epi_next/hospital_release.py读取版本manifest；本包manifest列出新增应用接缝状态，不作为旧selector的替代授权。E1/F0/F1仍使用原独立sidecar；E2应用adapter已生成验证，CTFM仅共享接口与注入结果。所有结果解释为模型证据，不叫病灶概率。
