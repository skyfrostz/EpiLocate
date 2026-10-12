# 独立 E2 5F 父监督入口 v18

2026-10-12 Asia/Shanghai；原 INTEGRATION 工作树、分支和 v17 包保留。独立 E2-FIDELITY-5F 已取得真实分项 owner 批准和精确新 task 准入 metadata，当前 **WAIT_CHIEF_UNIQUE_EXECUTION_SLOT / 医学 NOT RUN**。此包不包含实际 dispatch、执行窗口、数组、权重、Mask、GT或影像，不涉及 E2-Q、新应用重跑、医院展示或编码训练。

`index.json`给出草稿绝对路径/SHA、父入口源码 SHA、owner/admission/index 摘要、唯一 task/Job/输出目录及命令模板。私有草稿 status=DRAFT_WAITING_CHIEF_EXECUTION_SLOT、execution_window=null；它不能启动计算。总控另行发布最终 dispatch，保留所有科学/源码/环境绑定，补 READY_FOR_CHIEF_DISPATCH、CHIEF_SLOT_GRANTED、slot_id、带时区 UTC 起止。科学 binding SHA cb5468820ab76aa0de5736ef1a6bac7ea630dc438743afe7c9428274ab48dc73 不变，原应用 source6f1a1f1及交付22f2fa7不覆盖。最终命令仅缺总控发布的最终文件 SHA；路径提案见 index。

父入口 `qa/next_selected_fidelity_parent.py --dispatch <文件> --dispatch-sha <实际SHA>` 默认只审计 metadata；加 --execute 需要当前处于唯一获准时段，不等待或自动重试。父入口直接复用既有 v12 run_supervised/new administrative recovery，不新增队列/锁/调度器、不重新复制监督包。代码 hash、已安装 package/python 和8加载模块/10监督依赖由原 verify_loaded_bundle 验证；实际原队列/旧 UNKNOWN/finished 收据及两锁只在总控派发时由既有监督器再准入。本轮没有观察队列或尝试锁。

监督 spec 固定 CPU / INTEGRATION / F5 B0 / 全局120秒 / case120秒、15秒初始telemetry、0.25秒heartbeat gap、0.25秒合作退出、0.75秒TERM退出、2秒资源恢复。120秒从父监督器创建子进程前启动，覆盖子脚本/实际 Torch 导入、输入/权重/旧Mask核验与5F，不能从模型加载后重新计时。时间窗口须留出120秒工作和既有3秒退出/恢复参数；采样与操作系统退出有延迟，收据保存实际runtime，不称绝对瞬间上限。原5GiB预停/6GiB采样目标、free≥20%、swap增长≤1GiB及自身进程组 identity/退出/恢复机制保持；未知进程不发信号。

CPU环境明确 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1、MKL_NUM_THREADS=1、PYTHONPATH=原工作树、PYTHONDONTWRITEBYTECODE=1。同一父文件的 --child 在确认既有监督 ADMITTED 的本PID及精确spec后，只设定/读取实际 Torch intra/inter op线程数1，写一次 runtime-threads.json，不进行额外模型前向。然后进入字节不变的原5F CLI，建立唯一 ChildGuard；科学/模型/预算/输出路径均按原 binding。线程收据保存实际版本/线程/环境和原 global_started_monotonic；不重置时钟。

原 selected-fidelity.json 的64MiB文件上限继续复用 save_json，监督输出独立保留原采样/退出日志。任何已有科学输出或同Job监督目录拒绝重试；需总控对账。算法 partial/失败与监督状态分别看：原子CLI在非SUCCESS时退出1，原 supervisor可能将无预算触发的非零退出记 FAILED；不能只看传输状态把算法partial抹掉。失败模型实际数可能 UNKNOWN/null，不补零、不重复提交。只有既有supervisor确认自身进程退出和资源恢复后写 finished；否则slot保持UNKNOWN/阻断。

实际验证：8项父封装定向生成测试 PASS/0.03s，覆盖metadata0调用、未派发拒绝、精确一次委托、源码/线程/预算篡改及无时段拒绝、生成Torch线程收据、已准入child路径。actual metadata CLI exit0，19源码绑定（18原文件+父入口）及原监督锁/版本校验PASS，torch_imported=false、processes_started=0、queue observations/writes=0。生成测试使用监督/torch double，不算真实监督退出、Torch测量或5F验收。没有重跑v17后端/前端/浏览器或加载真实资产。
