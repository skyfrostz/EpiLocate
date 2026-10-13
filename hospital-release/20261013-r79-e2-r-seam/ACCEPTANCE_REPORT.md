# R79 定向工程验收

## 修复与边界

`qa/e2_readout_output.py` 继续返回原生 `subprocess.Popen`，共享 `track_child()` 类型、父进程归属与身份校验保持。删去 `poll_after_drain()` 中无超时 `join()`：poll 不等待线程；child 的 native exit 首次被观察后，允许 drain 最多 0.25 秒。未到 EOF 则设置停止事件、记录 `CHILD_LOG_DRAIN_TIMEOUT`，后续 poll 继续监测并等待线程自行退出。drain 使用 0.05 秒 select 检查停止事件；上下文退出时仅使用有超时 join，未退出则拒绝生成正常审计。未完成的 drain 不声称日志完整，错误会经原 pressure/check 与入口终态处理传播。

64MiB 累计/保留峰值限制、1MiB 每日志限额、8MiB 终态预留、失败/替换不退款、原全局 deadline 和自有组停止保持。没有增加调度器、锁、监督 bundle 或计算预算。仅关闭本任务持有的读管道，不信号终止未知后代。

## 实际生成进程验证

命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest -q qa/test_e2_readout_output.py qa/test_e2_readout_launch.py qa/test_e2_readout_lifecycle.py --basetemp .local/e2-r-readout-r79-20261013/generated-acceptance-v1`。

33 passed / 7.43s。临时 queue root 与科学/监督目录全为生成 fixture；没有访问真实 device queue 或医疗资产。成功/提前退出/deadline fixture 的父子均运行固定 v12 bundle，新 IO adapter 在父子两端安装；压力数据为明确 fixture，进程表使用真实 `ps`。因此证明接缝生命周期，不能充当真实内存压力或临床验收。

| 情景 | 实际生成结果 | 证据范围 |
| --- | --- | --- |
| 正常成功 | SUCCESS，slot completed，actual=0/0 | 模块启动、ChildGuard、终态、退出、恢复与双日志 |
| child 提前退出 | FAILED，缺 completion，actual=null | 不以 durable0 补 actual0 |
| 总 deadline | PARTIAL_BUDGET，GLOBAL_DEADLINE | 无 join 阻塞，保留全局时钟 |
| 进程表缺身份 | BLOCKED，未 ADMITTED，actual=null | 注入未知身份，未信号终止未知进程，slot 未伪装完成 |
| 表采样后 child 消失 | MONITOR_FAILURE_ProcessLookupError，actual=null | 实际已退出 child + 明确注入 stale table，getsid 早退竞争 |
| 后代继承 stdout/stderr | drain 超时失败，poll 每次低于 0.1 秒，线程退出 | 普通 fixture 后代自限退出；不对未追踪进程发信号 |
| 日志超额 | 1MiB/fixture 缩小上限、排空与丢弃记录 | 沿原输出保护测试；累计账本不退款 |

初次生命周期 fixture 直接使用未安装 IO adapter 的 ChildGuard，暴露生成遥测临时文件与扫描并发；随后 fixture 改为匹配真实父子 bounded adapter 路径。第二次 fixture 的导入次序缺少 loader 建立的 qa 模块路径，已按真实入口顺序修正。上述均为生成验证失败，目录留在本机 pytest 临时区；没有真实医学重试。最终正式证据目录独立保存在 `.local/e2-r-readout-r79-20261013/generated-acceptance-v1`。

## 原失败与 ProcessLookupError 诊断

只读核对原 R77 真实 receipt、counter、STOP、finished 和既有生成复现：监督 FAILED / MONITOR_FAILURE_ValueError；共享类型检查拒绝代理 `Popen`。原 durable reserved forward/backward=0，sequence=0，cases={}，无 ADMITTED 或 runner-complete。**runner_actual_counts=null**。这不是可评价的 E2 科学失败，也没有新增科学读出可汇报。具体路径与逐项 SHA 在 `prior-execution-audit.json`。

共享监督创建段先取 table[pid]，再 getsid(pid)，再 track_child；child 可在采样与 getsid 间早退。生成测试精确复现 ProcessLookupError；进程在表采样前消失还可能产生 KeyError，在 track_child 中消失也会拒绝。主启动异常与监测异常须分别核验。此诊断不读取 ENC 原资产、不修改 ENC、不归并 R18 两项错误。没有必要发布新共享监督版；冻结 bundle 原样保留，既有代码的快速早退仍可能 fail closed，actual 保持 null。

## readiness 和医院剩余项

新 binding 包含实际 source 和三份测试 SHA，LOC/config/loader/旧 5F 来源绑定保持。绑定 check-only 在独立进程实际 exit0、Torch 未导入、模型调用/队列观察0、数组/权重未读。新 attempt 的 execution permission=false，真实 E2-R `NOT_RUN`，需总控重新批准与派发。

医院限定冻结仍 `NOT RUN`：v16 原三单 SOP 开发结果仅 LOCAL_MVP_ONLY；医院受众展示/传播与录屏用途决定缺失，人工目视与完整 Series 方向/顺序/world/crop/resize/resample 验收未齐，连续三次医院演示与合格备用录屏/播放未完成，负责人最终批准尚缺。R71 既有渲染/刷新技术 PASS 不替代上述项。当前仅核对已保存文档和 source/build SHA，无新显示/恢复/计算/外传；独立 GPU AI Node 不进入方案。
