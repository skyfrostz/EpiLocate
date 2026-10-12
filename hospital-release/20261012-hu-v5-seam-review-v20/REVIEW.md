# HU v5 监督接缝增量审查

2026-10-12；INTEGRATION原工作树/分支，开始HEAD620014f3e1fd7a94b7b5a25df242ac2ed90bfb55。结论：**既有锁/phase可复用，V5本地接缝尚需以下补齐；不重建或修改共享监督器。不是执行批准或真实解码验收。**

实际v4链已从最终执行收据SHA e8b3fb3b0c8ba9a6c2998a0687be82177dc97f56041962c5dad6db88b8b83415核对：thin wrapper源码SHA18da6b9b0b9184187d972b7c5ecb93b0bb75ee7888265839d7c45098ecd0e364，取原wave1.serial.lock/cpu.lock后单次Popen v4 CLI、communicate90秒，CLI调用既有phase。**没有Wave1嵌套，不要求改用Wave1或新架构。**

已核对执行包01（SHA4281ca60edee7627e35d10413f6d17b7f5b1396223df2cdbdf0395c257e998e2）及03（SHA3e145a845ac968cabb63ae724ec2c0459d05375f4c1448d8ff4efb4ef51cf68b）。DATA当前HEAD3a7e55ac1d5d4502f9fd76b7e051469fb6b0f487；以下四文件字节与受测v4提交a28a9bc7f385ea0a3e91fa6285f25b755c525dc6完全一致。只读审查原实现，未评判尚未交付的新v5入口。源码摘要见manifest。

| 接缝 | 已有能力／精确本地建议（仅DATA实施） |
|---|---|
| 单次计数 | ri_hu_v4_diagnostic.py:123–128在API调用前记entered、返回后立即记returned，QA失败仍能保留1/1；但只是worker内存，phase终止会丢失。V5把参数API entered/returned与codec API reserved/entry boundary/returned分开计数；参数探查不冒充熵解码。固定唯一codec/插件入口，codec至多一次、model/training始终0。调用前持久预留一次并保留参数/同frame SHA，返回后在解包/转换/QA前持久returned=1。预留和真实原生进入不是同一事实；中断窗口/不可观测插件状态留UNKNOWN，不补0、不重试，也不调用before_forward把codec记成模型前向。 |
| 迟发失败 | v4 Trace.call:45–73已有first primary_error与reporting_error分离，pipeline:209–220已保留ledger失败的primary；继续复用。缺口在worker只最后通过Pipe交账：a0_acquire.py:54–63/98–111，v4:211–213超时/退出异常会用泛化phase错误和全UNKNOWN替代内存结果。V5在比较/抛错前保存白名单DICOM/JPEG两侧参数及完整成员SHA/EOF/CRC；返回与raw保存也做有界durable进度。phase父端只读已有进度，追加phase/reporting error，保留原primary和已确认计数，进度缺失才UNKNOWN。 |
| raw保全 | v4:129–150先全部shape/dtype/range/rescale QA，188–196才写stored/rescaled；因此返回后语义失败没有raw。V5先检查纯容量/容器安全边界，按新批准保留后端未截位raw诊断和SHA，再做语义门；只有范围/符号/对齐及重标度QA均通过才发布rescaled。超额或保存失败明确raw未完整保存/partial，不clip、不再codec；每个已写文件立即在进度登记，避免第二文件失败时首文件成无索引残留。 |
| 4MiB总额 | v3:172–178的publish_ledger已把入口目录已有文件（含残留）和最终ledger共同限制到4MiB，可复用。但array写入先计额度、后续未预留诊断账本；v4:189–197只在全部写完后将artifacts接到public，晚失败会失去索引。V5统一raw+条件rescaled+进度/最终ledger+所有.tmp/.part/失败残留计量，先留有界错误账本额度再写raw/rescaled，拒绝额度不足。原np.save BytesIO与内容副本也影响RSS。若新请求称全任务输出，需明确监督stdout/stderr/receipts是否在同一额度；不能移动目录或多建Budget绕过4MiB。最终扫描应在worker停止并reap后、无并发写入时进行。 |
| 时限/RSS/退出 | a0.phase:84–111已有60秒phase、overall90秒参数和12秒退出预留；最后参数4*1024**3是**磁盘free floor4GiB，不是RSS或输出上限**。a1_prepare.Budget:59–69的RSS512MiB仅协作检查，阻塞native codec内不连续采样；外Wave1固定5GiB预停/6GiB目标亦不能冒充512MiB。V5在DATA既有thin wrapper/phase接缝补齐明确归属worker的512MiB采样/停止（至少覆盖native阻塞期间），记录盲区/迟延，先reap再报告完成，不重置overall。无需加入外Wave1，后者参数仅说明不能误用其他任务的内存上限。 |

实际wrapper额外三点最小补齐：

1. 重复检查regex仍只匹配`epi_next.ri_hu_v3`，不覆盖实际v4；新v5只更正其精确入口/task/主请求SHA身份，锁内再核对唯一执行claim及新输出不存在。不要改v4、沿用v3正则或用模糊匹配查杀其他进程。
2. `a0._phase_child`独立setsid；v4 wrapper90秒超时仅TERM/KILL CLI进程组，而phase worker另有组。默认CLI被TERM时不能依赖其finally运行；wrapper finally还会释放两锁，child_confirmed_exited只证明CLI已退出。V5局部保存原READY握手确认的phase PID/PGID/start身份，先合作请求既有phase controller执行stop_child/reap；超时升级前核对绑定的phase身份并确认回收，再确认CLI退出/释放锁。无法确认时保留UNKNOWN/BLOCKED及已完成参数，禁止后续派发；不要因PID存在或仅CLI exit推断worker退出，不信号身份不明进程，不重开历史UNKNOWN恢复。不要求新监督器。
3. wrapper `communicate`先无限收集stdout/stderr，再以32KiB决定是否写入收据；这不是生成期输出额度。新接缝采用有界、安全捕获，并纳入新申请明确的4MiB范围/保留额度。wrapper final统计/hash/锁复核/发布任何一步失败都不能覆盖已保存primary和调用进度；CLAIMED之后实际attempt/CLI/phase身份需及时durable，不能执行过后仍仅留未派发claim。

新增fixture现已对**实际绑定v4 wrapper**的90秒communicate超时块做生成注入：两次fake TimeoutExpired，fake killpg只收到CLI组100的TERM/KILL，独立phase组101未被处理，exit0。只执行AST提取的这一个超时块，没有执行wrapper顶层代码、Popen、codec、ps或取锁；不证明历史现场曾发生孤儿进程。初始Wave1生成表检查已被实际wrapper定位取代，不作为v5架构前置。既有decoder失败/returned后QA/ledger报错生成测试在DATA test_ri_hu_v4_diagnostic.py:47–55/100–108，仅读引用、不重跑；T12真实codec正控制与数值闭包归DATA/ENCODER，本审查不声称完成。

此前失败工具仅为只读查找不存在的路径/未匹配glob；已用v12固定索引和真实DATA文件定位，无真实操作失败、无UNKNOWN修复。INT仅提交此报告和一个生成表fixture；DATA文件、共享保护源码、历史包不修改。所有真实成员/codec/model调用、队列读取写入、锁尝试均0。
