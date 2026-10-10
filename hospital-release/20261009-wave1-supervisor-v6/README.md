# 完成后退出等待修复：独立v2 bundle

只修合法完成后心跳误判及计数闭环，无真实重跑，不追溯改原FAILED收据。bundle、源码及八模块SHA见manifest；旧v1包/证据保留。

调用API不变，包名改为epinext_wave1_supervisor_v2。必须显式import main：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/absolute/fixed-v2-bundle-parent \
 /absolute/approved/python -c 'from epinext_wave1_supervisor_v2.wave1_supervisor import main; raise SystemExit(main())' \
 --spec /absolute/locked-spec.json --output-root /absolute/new-local-output \
 --dependency-root /absolute/full-dependency-lock --dependency-sha LOCK_SHA \
 -- /absolute/approved/python -m pinned_runner
```

同job/原child合法完成标记才进入退出等待并停stale；child不准新forward/backward，父持续核对预留计数不变。全局deadline/资源/归属/退出/恢复仍执行，未知槽不完成。非法或其他job标记不解除保护。真实各runner的新增执行仍由总控锁定，科学配置和当前预算不变。
