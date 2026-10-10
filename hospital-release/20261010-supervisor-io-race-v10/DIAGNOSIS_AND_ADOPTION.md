# P1失败诊断与IO修复候选 v4

## 已核验故障

原job `EPI-NEXT-HSPI-P1-CPU-20261010-01`的监督收据SHA为c842a949006db7eb020691030ad98b8eb0e8eb3ca6fdf20970f65de9baff8f64。父识别FAILED完成标记，child return2、预留/实际forward/backward均0；父确认退出和恢复，槽已finished FAILED。5/8采样缺遥测均在启动期，父未触发遥测缺失停机，不应把这些缺测当作本次失败触发原因。旧job不得重跑、不得改旧收据或task_key来重置失败事务。

原runner-complete reason是telemetry.json.95987.6183383040.tmp的FileNotFoundError；run-1目录当前为空。没有完整traceback，因此实际抛错调用栈仍属推断。源码和确定性复现均支持以下竞态：

1. c9f5369监督源码wave1_supervisor.py:47-50，heartbeat:174及后台loop:179：创建临时文件、写入/fsync、os.replace到telemetry.json；临时路径在replace后消失是正常原子写入语义。
2. LOC d678a254 p1_runner_v4.py:266将guard.directory作为BoundedStore.extra_roots；p1_storage_v4.py:18-26构造即ensure(0)，os.walk先枚举文件名，再对文件名逐个stat。
3. 枚举获得tmp名称，writer完成rename，reader stat该旧名称得到ENOENT；异常传播至runner_v4.py:306-307的FAILED路径。输出目录为空与构造阶段失败相符，但缺traceback不宣称确认了实际调用栈。
4. 这是原子写者与空间预算读者缺少共同同步，不是已证实两个遥测写者抢同一tmp。父最终资产hash发生在自有进程退出之后，与此阶段不同。

## 候选修复与LOC必要接入

INTEGRATION新源码提供IO_CONTRACT_VERSION=EPI-NEXT-SUPERVISOR-IO-LOCK-4：atomic_json持task目录supervisor-output.lock覆盖临时文件生命周期，supervisor_output_size(directory)在同一锁内枚举/lstat；锁等待默认上限0.1秒，超时明确失败，不能当0字节。临时残留文件仍计费，软链接、walk错误及无法解释的缺失仍失败关闭；没有删除临时文件、忽略全部ENOENT或放宽输出预算。

若采用本v4候选，LOC必须在自己的新版本BoundedStore中显式采用同一固定包的supervisor_output_size统计extra_roots，不能继续os.walk未同步读取supervisor目录。建议注入参数supervisor_size_fn：root继续原有统计，每个extra_root调用该函数计费；没有该回调的真实接缝必须阻断。只改supervisor writer不修复旧reader。不得在持IO锁期间再获取counter ledger锁；size callback本身只拿IO锁，不调用guard/模型/ledger。

同一命名包的父、ChildGuard和统计回调必须整体消费新的八模块包及新依赖SHA，不混用v3 writer和v4 reader。新LOC源码/runner依赖锁/readiness/生成fixture由LOC独立发布；本线不改LOC工作树。旧v3固定包保全。C1在总控审阅之前不启动。

IO锁不是调度器或队列准入。全局串行锁、行政决议绑定、设备租约、预算及一次性任务fencing沿用。stdout/child-samples等append-only文件仍可能在统计后增长，因此空间统计是观察值，不是瞬时硬上限；长目录扫描可超过等待上限而导致写者失败关闭，这一行为需在LOC隔离负载fixture验证，不能放宽原遥测/deadline约束。

## 可审查证据

test_supervisor_output_race.py使用原v3 atomic_json函数体与旧size语义，Event固定os.walk→rename→stat时序，稳定复现FileNotFoundError；固定版本统计被writer锁阻挡，release后返回正确字节数。另覆盖残留临时文件计费、软链接拒绝、锁超时非零字节降级、遍历错误失败关闭和非法timeout。所有目录均临时隔离；无生产queue或医学模型。

该候选是工程修复，不是P1重试授权。真实P1已FAILED；新实验若获准必须由总控另定义任务及账本，不能自动重投旧事务。P1/C1本轮实际调用0、生产队列写0、R0重采0；医院冻结及临床验证仍NOT RUN。


## 最新总控方向：优先LOC-only修复

v4不是修复的必要条件，先由LOCALIZATION修复其BoundedStore.size。可审查的最小方向是在识别到监督telemetry.json.<pid>.<thread>.tmp的ENOENT后，从零重扫整个统计范围；锁定最多重扫次数及总时间，若无法在界限内取得完整快照则安全停止。不能跳过消失文件、返回部分累计数、忽略权限/其他已提交文件缺失或放宽cap/reserve。所有现存tmp仍须计费；并发监督输出的cap仍是现有观察值语义，不把重扫宣称为瞬时硬上限保证。LOC需用同一可控竞争时序测试首扫失败→完整重扫成功、持续竞争→有界安全停止、临时文件计费和cap边界；本线没有实现/验收LOC-only重扫。

本v4共同IO锁包仅作备选，未经总控审阅不替换现行v3依赖。原v3固定包保留，P1/C1实际运行0。REPRODUCTION_TRACE.json是本轮隔离生成栈和时序证据，不是原P1缺失的真实traceback。
