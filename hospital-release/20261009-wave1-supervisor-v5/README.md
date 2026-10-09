# Wave1共享监督器固定交付

固定源码、八模块SHA、bundle/import/dependency manifest SHA及实际导入路径见manifest。接口契约在 research/next-hospital-20261014/reports/WAVE1_SUPERVISOR_CONTRACT_V1.md。无真实模型调用，无生产state写入；真实执行由总控串行放行。DATA最终完整入口握手由DATA验收，本线不重复。

固定bundle路径见manifest。总控先核验bundle_receipt/imports/dependency SHA，再将其作为PYTHONPATH。DATA的无initializer八模块隔离loader兼容；dependency lock须包含全部八个模块（并追加实际runner/config/dependencies），geometry-only锁不能通过verify_loaded_bundle。固定源码snapshot可明确live_replay_check=false，但实际加载字节和snapshot仍必须核验。

准备命令：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/absolute/fixed-bundle-parent \
 /absolute/approved/python -c 'from epinext_wave1_supervisor_v1.wave1_supervisor import main; raise SystemExit(main())' \
 --spec /absolute/locked-spec.json --output-root /absolute/new-local-output \
 --dependency-root /absolute/full-dependency-lock --dependency-sha LOCK_SHA \
 -- /absolute/approved/python -m pinned_runner
```

所有Wave1共享 ~/.codex/epi-next-device-queue/wave1.serial.lock 和跨设备UNKNOWN闸门，禁止消费方改生产queue绕过串行。DATA 0/0calls、120秒；E1 792/0calls、120秒；E2 7000/10000、900秒；CTFM 24/0、总1200/子例120秒。这些值必须由总控锁spec且与既有许可一致；本工具不签发授权。MPS仍ENCODER owner。

ChildGuard.from_environment在加载前创建；before_forward/before_backward只在真实调用前预留attempt，actual另记；DATA无模型只check/heartbeat。正常/部分完成先保全资产，再guard.complete(status,reason,device_recovered,actual_forward,actual_backward)。SUCCESS和NO_RELIABLE_RESPONSE为正常完成exit0；其他exit2，槽是否释放由退出/恢复而非算法增益决定。MPS最终driver/tensor来自实际子进程，需ENCODER同步/empty_cache后明确恢复。

测试覆盖零调用、隔离bundle、跨设备门禁、计数不重置、预停/超时/缺测/监测故障、身份及无关进程保护、资产保存。一次clean回归系统ps超时导致注入测试预期原因不匹配，按fail-closed终止；保留原失败日志，定向复核通过。采样峰值不代表瞬时峰值，不把旧hardcap注释当当前保证。采样延迟、同UID绕过、旧runner未接入等限制保留。医院展示、MVP三次E2E仍未获本轮授权。

调用方式更正：使用上述显式import入口，不能直接以 `-m epinext_wave1_supervisor_v1.wave1_supervisor` 启动。`-m`把入口装载为 `__main__`，固定版verify_loaded_bundle按完整模块名查sys.modules可能KeyError；显式import保留该完整模块绑定。只更正文档，固定源码/bundle/manifest SHA和既有日志不变。总控已报告DATA真实标签任务SUCCESS、槽恢复、模型calls0；该结果由DATA/总控原收据负责，不是本轮重验收。
