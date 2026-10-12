# R77｜E2-R 实际执行入口准备

状态为 **PREPARED_NOT_EXECUTED / BLOCKED_BY_APPROVAL**。这是一份科研读出入口交付，不是新的 MVP 联调或医院展示。固定源码 `e303595099b31d7ab6f66652feda1b7fdffc1fa5`；仅复用既有加载器、监督器、全局计数和恢复队列，没有真实医学调用。

唯一最终绑定：

- 路径：`.local/e2-r-readout-v5-20261013/execution-binding-r77-final-v4.json`
- SHA-256：`92fb6d542b69d094f0e3fb65474f16827bc75d5f81b2632d584f225f0bf8f928`
- 可合并批准项：`.local/e2-r-readout-v5-20261013/approval-item-r77-final-v4.json`
- 批准项 SHA-256：`0f330e7ef460f3e00811583f3e4ea93aa5a4f8232d8800fef806ebe2e97aa53a`
- LOC 配置：`configs/e2-r-readout-v5.json`，SHA-256 `1d2611e8371a3d8074441f53e2832fdc46f4f38b5011a58ffb22f37ae9b3ae52`。

此前 draft/final-v1～v3 仅是未派发工程草稿，不可用于最终申请或执行；新绑定没有覆盖它们。完整绝对路径、入口及命令在 `manifest.json`。

## 实际加载路径与预算

`qa/next_e2_readout.py` 默认只核对源码、环境和绑定元数据。真实 child 仅在总控派发和共享监督准入后调用 `epilocate_next.e2_readout_launch.run_existing_readout`：复用原 `build_existing_e2_runner` 的 prepared/model/config loader，再调用 LOC `epi_next.e2_readout_v5.run_readout`。不重跑 P1 或旧 5F，不载入新 CT/GT，不改变原科学对象。

固定 case3 / epoch3604 / cell43，5/10/20% 排名区域及同面积随机对照；共16个对象，其中4个原保存 logits 必须严格兼容。核验不匹配立即停止，无 fresh fallback。新增12次读出与2次 adapter checks 合计计划14F，上限18F；4F未分配，不能用于额外校验。0B/0更新/0重试，CPU1，既有父监督全局120秒，不在加载后重置时钟。

64MiB 同时限制生命周期累计写入预留和保留文件/atomic临时峰值，包含科学结果、失败残留、父子 stdout/stderr、遥测/监督收据和本任务 queue slot 文件。父子使用现有 `supervisor_output_lock` 内的同一持久账本；替换和失败不返还额度。每次账本自身写入保守计费512字节；普通阶段最多56MiB，8MiB留给终态记录。终态收据不能装入剩余额度时拒绝写入并保留失败/未知状态，不宣称预留必然足够。

父子4条日志各最多保留1MiB，native输出通过管道受限写入，超额继续排空并记录丢弃字节，触发失败。执行摘要和父异常均留在受限日志中，不在监督退出后重复 stdout/traceback。已知失败部分计数写入 `runner-complete.json`；确实未知仍为 null，不补0。未完成的账本临时事务按 UNKNOWN 阻断，不复用旧值继续写入。

## 生成验证与真实阻断

25项定向测试通过，2.74秒：包含正常14F/4复用、适配不符2F停止、旧logits不符0F且模型未加载、父时钟不重置、精确批准/新task/同队列/slot拒绝，以及替换累计、父子共享账本、失败不返还、native日志限制和已知/未知失败完成计数。仅使用生成数组和 toy model；一次普通Python日志fixture和生成目录内共享guard不占计算slot。最终日志控制修正后未扩大测试范围，最终源码只检查命令通过；详见 `generated-tests.log` 与 `final-check-only.json`。

实际医学前向0、真实 prepared/权重读取0、队列观察/准入0、新slot0。旧 MVP 66项源码/构建哈希全部匹配；本轮未读原DB/影像/对象，未启动服务、MPS/GPU、新展示或重跑旧验收。

仍需总控合并并取得三项精确条件：

1. 新 owner 分项批准包含 `E2-R`，其 item 锁定最终 binding、limits、task_key、job_id 和 output_root。
2. 既有恢复队列上的新 task-key admission：`EPI-NEXT-E2-R-CASE3-CPU-20261013-V5-INT-1`，沿原恢复链，`scope.basis.e2_r_itemized_owner` 与 `e2_r_itemized_request` 锁定对应 SHA。不得复用已消费 5F/P1 的任务权限。
3. 唯一 `CHIEF_SLOT_GRANTED` 窗口和最终 dispatch。模板 schema 为 `EPI_NEXT_E2_R_DISPATCH_V1`，精确字段见 CLI 校验与 manifest；窗口保留既有退出/恢复余量。

只检查命令已实际通过。一次实际 `--execute` 命令已经固定在 manifest，仅缺总控发布的最终 dispatch 文件及其 SHA；未发起该命令。CT-FM 既有科学批准保留，不作为本次新增申请。基础 v16 和 E2/F0 真实应用消费继续待命。
