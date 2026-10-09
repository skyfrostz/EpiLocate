# Wave1 共享监督器调用契约 v1

所有者INTEGRATION；LOC/ENCODER/DATA消费固定源码，不另做监督器。资源修订SHA `1011506834d7e5c54c60ef7d67f89900fa9259669d6bde2fb6141c197c6481de`。本接口不授权真实执行、数据访问或模型重算。

源码为 `epi_next.wave1_supervisor`，固定bundle采用独立包名 `epinext_wave1_supervisor_v1`，避免已加载的其他线epi_next污染相对依赖。交付时列齐八个运行模块SHA（另附空package initializer）及numpy版本，消费者核验实际 `__file__` 全部来自bundle。

```python
spec = SupervisionSpec(job_id='unique-job', task_key='approved-experiment',
    device='cpu', owner='DATA', max_forward=0, max_backward=0,
    timeout_seconds=120, per_case_seconds=None)
receipt = run_supervised(spec, command=[python, '-m', 'pinned.runner'],
    output_root=approved_local_root, dependency_root=pinned_dependency_snapshot,
    dependency_sha=locked_sha)
```

runner一开始（模型加载前）创建 `ChildGuard.from_environment()`；每次实际forward/backward之前分别调用 `before_forward()` / `before_backward()`，计数包括适配器、失败尝试和子例。CTFM使用 `begin_case(case_key)` / `end_case()`，单例120秒、全局1200秒不重置。runner正常或部分结束保存自己的独立资产；监督器只追加日志/遥测/终态，不覆盖历史。新job目录只能创建一次，不自动重试。

父进程实际环境变量为 `EPI_NEXT_SUPERVISOR_DIR` 和 `EPI_NEXT_JOB_STARTED_MONOTONIC`。directory内 `spec.json` 固定JOB_ID/截止/调用上限，`STOP`是stop文件，`telemetry.json`是最新原子样本，`child-samples.jsonl`记录20ms目标的每次实际间隔，`counters.json`是跨guard/子进程共享账本。DATA无模型不调用before_*，但持续heartbeat/check。forward/backward是fsync预留的attempt，停止恰在预留后可能未进入模型；runner actual counts单列，不能把attempt自动当实际模型调用。一个job覆盖完整实验，不能以新job重置预算。

child guard捕获SIGUSR1/SIGTERM或stop文件并立即禁止下一次forward/backward；已在途算子无法保证瞬时中断。MPS callback由ENCODER在实际计算子进程提供，`ChildGuard.from_environment(mps_driver=lambda: {'driver_bytes': actual_driver, 'tensor_bytes': actual_tensor})`，不得返回父进程值或假0。DATA启动缺测宽限2秒；模型runner默认15秒，仍计入原全局预算；超过窗口或后续heartbeat陈旧超过默认250ms则fail-closed。child ADMITTED握手完成后才返回guard，避免尚未核验身份就开始有用工作。

父监督器新建start_new_session子进程并固定PID/ps启动时间/PGID/SID，目标50ms采样RSS及全机free/swap。RSS逐PID保存，group aggregate为进程RSS之和（共享驻留页可能重复计入），不与MPS相加。macOS free使用 `memory_pressure -Q` 的 `System-wide memory free percentage`，保存原始输出与来源，不用vm_stat free pages降低阈值。RSS或实际child MPS driver >=5GiB预停（目标6GiB）；free<20%或swap较启动增>1GiB预停；监测异常fail-closed。首次触发写stop/SIGUSR1，默认250ms后TERM、再750ms后KILL；只对已核验新建自有session/group发送。身份未知保持UNKNOWN/slot暂停。全局deadline包含加载，不借退出宽限扩展计算。

所有Wave1先持有 `~/.codex/epi-next-device-queue/wave1.serial.lock` 和跨CPU/MPS UNKNOWN闸门，再复用原tracked_device_slot/device flock；不能CPU/MPS并行。退出及设备恢复确认才写slot完成；未知slot即使flock释放仍阻断下个Wave1。CPU/JSON需要自有进程无活成员且系统压力恢复；MPS必须实际计算child同步/empty_cache后给最终driver/tensor及device_recovered标记，再确认退出/系统压力恢复。异常kill无末样本不能完成slot。共享queue是合作式入口，绕过旧入口直接启动进程不受本模块约束。

完成接口（DATA也必须调用）：

```python
guard.complete(status='SUCCESS', reason=None, device_recovered=False,
               actual_forward=0, actual_backward=0)
```

`complete`先关闭heartbeat、写最终样本，再不可覆盖写 `directory/runner-complete.json`。schema字段是 `{job_id,status,reason,monotonic,actual_forward,actual_backward}`。MPS先由ENCODER同步/释放/测量，再传device_recovered=True；CPU无需该标记。仅调用 `close(device_recovered=False)`不会生成完成标记，会判缺失completion。算法拒绝用 `NO_RELIABLE_RESPONSE`，与SUCCESS均CLI exit0；partial/failed/blocked等exit2；slot释放取决于退出/恢复，独立于科学结果。runner自己的原始算法状态和已有资产另存，监督器只追加 `supervisor-receipt.json`。

CLI准备形态（总控固定spec/runner/dependencies后执行，本线不启动真实）：`python -c 'from epinext_wave1_supervisor_v1.wave1_supervisor import main; raise SystemExit(main())' --spec SPEC --output-root LOCAL_NEW_OUTPUT --dependency-root IMMUTABLE_LOCK --dependency-sha SHA -- python -m PINNED_RUNNER`。科学参数/申请中的旧PENDING/hardcap为历史，当前有效资源语义绑定本契约首部修订SHA。

本轮仅小型合成/故障注入；真实准备命令由总控绑定上述参数、数据与各runner SHA后执行。既有MVP只增加必要接缝，不新增三次真实E2E。


依赖锁必须含上述八个运行模块及numpy版本/Python版本；旧DATA fixture只锁geometry不兼容，须升级为八模块+自身runner/config的完整依赖锁。无__init__的DATA隔离loader兼容；父子双方verify_loaded_bundle核对每个实际加载模块文件字节与依赖锁。固定snapshot若不再消费活跃源，可在entry明确设置live_replay_check=false，执行时仍核验不可变snapshot和实际加载字节；默认保持live源漂移检查。所有Wave1消费者必须固定共享queue路径，不得另设生产queue。

入口注意：固定版本verify_loaded_bundle要求完整模块名存在sys.modules中，直接-m将入口命名__main__可能KeyError；必须显式import main后调用，或用只包含该import/call的独立launcher。不会修改已固定bundle来追补此文档更正。旧验证日志保留。


## 完成后退出等待修订（独立v2 bundle）

已有E1实际运行child SUCCESS792/792，但旧监督器关闭心跳后在Python teardown期间误报STALE_CHILD_TELEMETRY；原FAILED收据SHA `f7b675db91ba1d0016b7296fc5ec66d90a1bc3ccdf4823f80d665585e8b6c757`保留，不能追溯改PASS。新版本只在验证同job/原child PID、合法终态、完成时间>=最终样本、实际计数不超过预留及预算后停止stale检查，记录VALID_CHILD_COMPLETION_EXIT_WAIT。非法/其他job标记不解除心跳保护；全局deadline、资源/归属/进程退出/恢复检查持续。新包名epinext_wave1_supervisor_v2，API及显式import main调用方式不变。不得重跑真实E1补证据。
