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


## R91负责人批准后的行政启动准备｜2026-10-15｜等待唯一serial release

本节更新上节“缺新执行确认”：已通过主控read_thread独立取得负责人原始userMessage `01a13b48-92dd-7d60-87a7-21ccf0fc648a`（thread `01a138ed-90ba-7311-822e-9b48e7363f59`、turn `01a13b48-92b6-7cb2-b794-4db6451c6c0e`），对R18 b23b…和E2-R纠正增量69730c02…答复“批准两项精确增量”。原消息副本SHA `1d05a47cf514e4098b273a95138f89f4532a989b492707fa633f3c7665b75f4f`，逐项owner SHA `bdb752a49d76486a89c66712804e826e730c26f5af597a0e802a9475a719372f`。这是一份新有效确认，不复用旧消费记录；R18先运行，E2仍未获当前时间窗口。负责人另答“本轮先完成科研准备，人工验收另约”，不启动MVP。

可审阅索引：`/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_PRE_EXECUTION_INDEX_V1.json`，SHA **372768910edca806dde9b3fbcc89133d4042ffa67fd7351ec351c7ca3bb3ac8e**，status=PREPARED_WAITING_CHIEF_RELEASE。它绑定新协议适配scope view/owner confirmation、原科学请求9ae5d0e9…、f16169a0…binding、69730c02…增量、24项原执行源码、21runtime、新行政准入及独立启动器。原case3/epoch3604/cell43、14F计划/18F上限、0B/0更新、CPU1/120秒、RSS5/6GiB、64MiB、原时间/压力停止规则不变；真实payload只在admitted加载时检查。旧runner actual=null保持。

行政确认采用原协议结构，是对已直接批准item的兼容视图，不是第二份科学申请或额外预算。活跃准入 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_ADMINISTRATIVE_ADMISSION_V2.json`，SHA **b5cad416745de9a5e4e4f8192449e47e65b5eefdd010a82e7f9e88645f71c217**，只允许原未启动task `EPI-NEXT-E2-R-CASE3-CPU-20261013-V5-R79-INT-1`，job `e2-r-case3-20261013-v5-r79-int-1`；原队列路径不变。新准入由固定recovery-chain原校验器只读验证PASS，不写共享queue、无slot。首次准备的V1 scope摘要使用compact编码而被INDEPENDENT_OWNER_APPROVAL_REQUIRED拒绝；该V1及失败收据保留，不引用执行。V2按原artifacts.canonical_json的indent2+newline生成，scope和科学方案不变。本次没有科学调用失败或次数消费。

候选派发模板 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_DISPATCH_TEMPLATE_V1.json`，SHA **bd2859be0461992a9ad2e69c049ec0e8a4579a81fdcbd8d95dabe6e458abd708**，status=DRAFT_WAITING_CHIEF_EXECUTION_SLOT，window/slot为空，禁止执行。release模板 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_CHIEF_RELEASE_TEMPLATE_V1.json`，SHA **24494414465e383ea15fa1b8568c2e5afcfe4a6cf94f70a91cb187758115b220**，也不是release。pre-index生成时无真实final dispatch、release或LAUNCH_ATTEMPT；当时输出和原task slot均不存在，不伪造新task绕过消费。

原机制的收口步骤：

1. 主控先核验R18 train/evaluate实际终态、已知进程退出和原共享锁资源可用；失败时先可靠清理，对E2这一独立任务是否继续明确发出release，不推断R18成功。
2. 在原批准目录以新不可覆盖文件 `INT_E2_R_DISPATCH_V1.json` 发布final dispatch，沿用模板的binding/owner/admission/compute/spec原字符串；改为READY_FOR_CHIEF_DISPATCH、删除must_not_execute标记、绑定原shared slot与当前aware UTC窗口（原校验要求至少预留123秒）。不得使用旧dispatch90b4…或模板自身的SHA。
3. 另以新 `INT_E2_R_CHIEF_LAUNCH_RELEASE_V1.json` 发布release：status=CHIEF_EXCLUSIVE_SERIAL_RELEASE，绑定本pre-index SHA、final dispatch真实path/SHA、同一binding/owner/admission及source_thread_id；r18_exit_verification.status=CHIEF_VERIFIED_R18_STOPPED_AND_RESOURCES_FREE，evidence为实际R18结束/执行JSON路径及SHA。原release模板为空，仅供字段核对。主控必须在本会话单独发唯一launch release，文件本身不能代替该指令。
4. 已有 `qa.e2_corrected_argv.derive()` 从新dispatch的绝对binding原字符串生成准确CLI；原check_binding和check_dispatch(executing=True)继续做全部绑定/窗口/原输出未消费核验，不因same resolved path放宽。外层一次性launcher `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_ONCE_LAUNCHER_V1.py`，SHA **aebba5b3a6c3399d5ef29d5b8ddfbc40eb77c6d27039f26ab3bb336c0bf1c872**，接受本index/final dispatch/release三组精确path+SHA；默认仅元数据检查。只有核验实际主控release后才提供--execute，当前最终execute argv为空，不预造future SHA。
5. launcher独占创建私有 `INT_E2_R_LAUNCH_ATTEMPT_V1.json` 后仅Popen原入口一次；该claim不删除/重置，不写共享queue。重复调用拒绝；未知等待/写入结果记录UNKNOWN_RECONCILE_NO_RETRY，先对账、不重新提交、不信号未知进程。driver exit0只记DRIVER_EXITED_PENDING_RECONCILIATION，不直接称科学SUCCESS；随后核对原ADMITTED、actual计数、readout、STOP/finished/监督终态。新wrapper不重置原科学时钟、修改预算或加载模型。

本次默认wrapper check-only实际exit0，日志SHA `8b6bc23b8cdcfda1d762229f81fec9b9bf5cc7f7852dbceaafc1195dd49a3597`：model_calls0/queue_writes0/slot_created=false。3项必要生成替身测试PASS（0.02s）：精确vector只提交一次、unknown不重提/actual null保留、template禁止提交；没有真实subprocess或模型/队列。额外原check_dispatch元数据兼容核对仅使用内存GENERATED_NOT_RESERVED窗口，记录INT_E2_R_PROTOCOL_VIEW_CHECK_V1.json，不授予实际窗口。Mask/5F/科学配置元数据新核对PASS，记录INT_E2_R_SCIENCE_METADATA_CHECK_V1.json；不读取真实数组/权重、源DB或影像。三个旧科学生成测试闭包及原7项argv回归直接继承，不重跑MVP技术验收。

上述行政准备快照的科学状态NOT_RUN，已获批准但当时等待R18后主控独占release；launcher在该快照仅默认检查过，未走实际--execute。只有行政准备和必要生成验证，原slot/science/supervision目录未创建，原actual=null不改。所有控制脚本/收据保留上述私有本地目录，不提交患者资产或凭据；本地文档提交，不push/改state/两表，不跨会话发送消息。


## R91纠正调用实际执行｜2026-10-15｜SUCCESS

主控后续发出唯一launch release。独立核验R18结束证明SHA `9b7848a8f86a51e888440510b62f890d3716f95186ab2cd67f9d4370a5a8fee6`：train actual100F/100B/100更新、evaluate2F/0B/0更新，已记录6个PID当前未列出；主控原锁可用证明。新dispatch SHA `aa42b22e95b20bd46a3b9d0e093bcd360b229900e7276e35d033e54374655b22`、release SHA `ac66d045805c45f61376ae166f51da91e460b6ae0ab90a06314c6e937dfc887f` 和原pre-index37276891…全部匹配，原executing=True窗口校验PASS。通过绑定once launcher只提交一次，未修改原entry/生成器/科学配置、预算或路径比较，未消费旧dispatch。

**科学readout、runner completion、supervisor、driver/wrapper退出和slot均SUCCESS**。ADMITTED child6484（driver6475、wrapper6465）；actual14F/0B/0更新/extra_autograd0，与durable14F/0B及两份actual收据一致。16对象完整：4历史兼容logits重用，12新读出+2 adapter check=14实际F；unrun=[]，两项adapter差异max_abs0。不是16次新forward，也没有重做Mask优化。原case3/epoch3604/cell43及保存Mask兼容性保持。

原始科学读出INT `.local/phase2/e2-r-case3-20261013-v5-r79-int-1/readout.json` SHA `f273f09388ff70cd85ada2342e5d09b60216504ec5b8bd7ef12df9d2983d1847`；实际索引 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r91-head-e2-20261015/INT_E2_R_EXECUTION_INDEX_V1.json` SHA **fea074c735ce8470e438a0598d0e81f15e96661f28e0e843487e0532b8196c59**。完整原始/读出logits、区域面积、keep/remove、六组ranked/random配对差值在同私有目录 `INT_E2_R_MECHANISM_READOUT_SUMMARY_V1.json`，SHA `12272900a9f875a6484bdef971bdb7e83d67f49edfc398503557fd9900d0fb4e`；不将逐病例数值/区域阵列复制进Git。

实际探索读数：完整软Mask保留的目标margin接近原始，单峰patch保留改变更大；5/10/20% ranked keep的目标margin均高于同模型面积随机keep。remove混合：5% ranked造成较小drop，10/20%较大drop，不能概括为全部面积或全算法优势。等面积按224模型网格的selected_pixels比较（2508/5017/10035），native投影面积并不完全相等；仅固定seed17随机对照，区域形状/碎片度未匹配。adaptive case3/epoch机制探索，不是独立定位测试，GT未参与选择，不建立临床有效性或病灶概率。

监督总时长3.322033250秒，恢复3.328654666秒；41个父资源样本，sampled peak RSS696025088 bytes、最低free fraction约0.56、swap增加0、最大父间隔0.099830958秒。保留1条启动期TELEMETRY缺样（原15秒grace内）；不能声称无缺样或绝对峰值已证明。CPU样本无thermal测值字段，未补造。累计输出预留35200040 bytes<67108864，guard errors=[]，retained-before-audit35090613；STOP不存在，stdout/stderr为空。DEVICE_RECOVERED和OWN_GROUP_EXITED(returncode0)事件存在，三个已知PID退出后未列出，cpu/mps/serial既有锁只读探针均可用，无未知进程信号。

监督收据SHA `699ba5ddfd667162ce6032b4a3cd8f99edd9dbf319a4f16d55dd746ac9fe695b`、runner completion `49c638df995eb7ce3388d2deed245405d576566fd4fc16ea7ee08a30361ad19a`、slot finished `b90bb175f1ffcb18424b5ddaff57f1f7ee05d2faf80b91ff05688daec1a23dd2`、once-launch原始调用收据 `ca266727c49306ecec6a255722e65b2485784fbb4bc942759ac6592db84b88b8`。原launch收据保留DRIVER_EXITED_PENDING_RECONCILIATION/actual=null快照；上述独立实际索引才记录已对账actual14，不改raw receipt或旧actual=null。执行后24源/21runtime SHA仍MATCH，旧R77/CLI失败/STOP/5F及归档dispatch原字节保持。

本次许可已消费，不再次调用、不补跑未用4F。MVP服务/浏览器/显示/人工/三次演练/录制均未启动；人工另约、演练0、医院冻结NOT_RUN，不倒填10月14日。本线只提交原文档和双日志，将私有结果索引交主控读取汇总；不改状态/两表、不push，不宣称独立临床定位成功。
