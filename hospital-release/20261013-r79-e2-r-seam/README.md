# R79 E2-R 接缝修复交付

**GENERATED_ENGINEERING_PASS / PREPARED_NOT_EXECUTED / BLOCKED_BY_NEW_DISPATCH**。原工作树、原分支；基线提交 `b1a037d04e39cd59b2453e0281ec32e898c07f6d`。本包仅修复新 E2-R 的进程/日志接缝，准备精确申请；真实 E2-R 没有重跑。

- 申请（供总控合并唯一审批表）：`.local/e2-r-readout-r79-20261013/approval-item-r79-v1.json`，SHA `058a1e929bb4c235d4a6b420821dae7fa3a31e9ec076256f0204dca603acf1a6`。
- binding：`.local/e2-r-readout-r79-20261013/execution-binding-r79-v1.json`，SHA `f16169a035add8a8a022f1ccb5fa5add32229dc57905e332f8acd064e9cc2daf`。
- 新 task：`EPI-NEXT-E2-R-CASE3-CPU-20261013-V5-R79-INT-1`；job：`e2-r-case3-20261013-v5-r79-int-1`。科学/监督 output 均尚不存在。
- 原 case3、原保存 Mask、v5 science 配置 SHA `1d2611e8371a3d8074441f53e2832fdc46f4f38b5011a58ffb22f37ae9b3ae52` 不变。计划 14F，上限 18F（4F 不分配），0B/0updates/CPU1/120 秒/64MiB，无额外 warmup、优化、P1/P2/P3、重试或 GT 选择。

代码和三份定向测试的 SHA 均进入新 binding；metadata 检查验证测试闭包。33 项生成测试通过（7.43 秒），其中生命周期测试实际启动普通 Python child，走冻结 v12 `run_supervised`、模块加载、ChildGuard、退出、收据和生成 queue slot。只检查命令通过，Torch 未导入，真实数组/权重读取和真实队列观察为 0。详见 `ACCEPTANCE_REPORT.md`、`generated-lifecycle-evidence.json`、`generated-tests.log`、`prior-execution-audit.json` 和 `manifest.json`。

原 R77 已消费，不能复用旧 owner/admission/dispatch。新申请不是批准。执行仍需新分项 owner、新 task 在既有恢复队列的 admission，以及按 DATA/R18/CTFM 优先级明确的总控独占 slot/dispatch SHA；本包不制造权限或时间窗口。默认 CLI 仅做 metadata check，准确 argv 在 manifest；不得自行加 `--execute`。

原 R77 监督失败是 `MONITOR_FAILURE_ValueError`。**durable reserved=0F/0B，runner actual=null**；原 receipt/STOP/finished 保持原字节，不将未知 actual 改成 0。此前 b1a037d 交付中的“0F/0B”只能解释为持久预留计数，本包明确纠正其实际计数口径。R77、R78 和 fixed-v1 是历史记录，当前源码/申请以本 R79 包为准。

无新监督版本交给 ENC。冻结 v12 bundle 的 8 个模块 SHA 全部 MATCH；现有 index 路径、每个模块路径/SHA 在 manifest。`ProcessLookupError` 的早退竞争只完成独立生成诊断，未修改 bundle 或 ENC 工作树，未认定其一定就是 R18 历史原因。

v16、旧只读恢复、FrozenBaseline、A/B/C、GT-v1、旧 16/32/64 和原 5F 保持不动，MVP binding 的 66 个源/构建 hash 全部 MATCH。原本地 3/3 MVP 与 R71 技术验收保留；医院用途批准、人工目视/完整空间验收、医院三次流程、备用录屏及最终 PASS/CONDITIONAL PASS/NO-GO 决定仍未完成。医院默认未正式批准，冻结 `NOT RUN`，不依赖独立 GPU AI Node；本轮无新恢复服务、模型、影像导出或远程操作。


## 迁移接续最终收口｜2026-10-13

当前待审批对象为本目录 `approval-item-r79-v2.json`，SHA256 `9ae5d0e90663934ed4962edec83dd2942584209ba6c2e7d2d91b64581d2b776b`。V1和原manifest/执行binding保留原字节；V2仅追加实际源码commit、runtime逐文件绑定、既有输入/Mask/权重索引与停止/验收规则，未改执行代码、科学范围或预算。INT执行源码commit `ae39a6b6fe0c4c46fac98b4d2e086dacf980f982`，LOC锁定源码对应commit `11ac87b91ea863a0f394aa53a9e3db6571691bc6`。

33项生成测试不重跑，当前源码SHA匹配；现存日志 `600bf0b81f9d8958f69b91ae3a0ef398808dbb4399fdc1ef55fe9f23ecb352c0` 为 **33 passed in 7.54s**，此前正文7.43秒为旧摘要，以现存日志/manifest为准。本轮原metadata入口再次PASS，Torch未导入、arrays_weights_read=false、model_calls=0，状态ENGINEERING_READY_OWNER_ADMISSION_SLOT_PENDING；V2新增外层runtime引用单独按字节核对，不冒称原入口验证了新字段。

绑定不变：`f16169a035add8a8a022f1ccb5fa5add32229dc57905e332f8acd064e9cc2daf`。静态读出路径为2次原输入adapter一致性检查+12次规定新读出；四组历史logits复用，完整软Mask仍在报告对象内。无额外预热或未计数最终调用；上限18不代表允许增加4次实验。仍REQUEST_ONLY_NOT_APPROVAL、execute_permission=false；无admission/slot/dispatch和新真实结果，不要求等待R18。
