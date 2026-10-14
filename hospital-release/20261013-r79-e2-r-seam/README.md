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


## R91有界核查｜2026-10-15｜继承原纠正增量，不新建审批对象

负责人R91只授权核查/准备，不是新真实执行确认。原纠正调用增量 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-final-execution-20261013/engineering-r85/E2_R_CORRECTED_INVOCATION_INCREMENT_V1.json`，SHA **69730c02f5b8798180059e835eb10a40c15162c653b3c52ae979661ab5ae69b7**，字节/调用生成器/7项生成回归源/原科学请求均MATCH，直接继承。不重新签整个科学方案，不新建重复批准对象、admission、slot或dispatch。

当前binding f16169a…的24项执行源码、原科学请求1d2611…、原LOC闭包/目标契约、21项runtime、原MVP66引用MATCH；原case3 epoch3604/cell43保存Mask JSON及5F文件SHA、source_binding、原始/完整软Mask logits兼容，四个重用对象具有有限logits。未读取或重哈希医学数组、geometry payload或权重；它们的真实SHA/finite校验仍必须在获准admitted加载链进行，不能把本次元数据PASS称为实际模型调用。

计划14F（2 adapter checks+12新读出，4历史对象重用），上限18F，CPU1/120秒/0B/0更新、输出累计/保留64MiB、RSS5GiB预停/6GiB监督及原压力/thermal/clock停止条件不变。原失败E2_R_ENTRY_EXIT是FAILED_BEFORE_SUPERVISOR，原因精确relative/absolute字典不等；runner_actual_counts=null、无slot/science/supervisor output。其dispatch90b4…已消费，不执行归档argv，即使路径解析到同一文件也不放宽原check。

最终argv只能在新的有效确认、总控新admission/dispatch及R18优先后的独占release齐备时生成：先验证新dispatch路径和SHA，使用其binding字典的绝对path/SHA原字符串，调用既有 `qa.e2_corrected_argv.derive(new_dispatch_ref)`；再核对 `qa.next_e2_readout.check_binding(reference)` 和 `check_dispatch(reference,value,new_dispatch_ref,executing=True)`，全部通过后才形成一次argv。derive仅产生CHECK_ONLY向量且不验证当前时间窗口；正式入口仍执行所有绑定/窗口/输出未消费检查。本轮没有新dispatch，所以最终execute argv为空，不能预造或直接给旧check-only向量加execute。

readout源码已有16对象的原始/扰动logits、selected_pixels/valid_pixels/native面积、keep/remove、region SHA、target margin/probability/drop、adapter checks、new_cost/cumulative_meter_cost及unrun_objects；无需改LOC/执行源或增加forward。真实完成后，对每个5/10/20%和keep/remove分别核对ranked/random同selected_pixels=floor(valid_pixels*p/100)，以保存行计算ranked-random的各类logit差、margin差、probability差及drop差；remove面积用selected_pixels比较，不误用保留补集面积。缺失/非有限则null+原因，不补跑。模型进入证据须实际adapter_checks与NEW_FORWARD行、runner completion/actual计数及监督终态相互对应；预留计数不能替代actual。负收益也如实交付，不以GT挑区，不外推独立定位验证。

R91本地核查索引 `.local/e2-r-readout-r79-20261013/r91-preparation-audit-v1.json`，SHA **1b7c49d884dcbe0d06a077828975331862bab098f8b0122ee69d6ba0af78b0c8**。原metadata check实际exit0：model_calls0/queue_observations0/arrays_weights_read=false/torch_imported=false；不重复33+7项匹配源码的既有生成测试，不重复MVP技术核验。当前科学readout **NOT_RUN**，新增精确执行确认缺口保留 **BLOCKED**；R18优先。只更新必要原文档/双日志，本地提交，不push或改总控state/两表。
