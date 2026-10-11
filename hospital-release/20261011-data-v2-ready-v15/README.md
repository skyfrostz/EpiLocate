# DATA v2消费与MVP最终就绪交付｜2026-10-11

仅供总控一次串行调度现有本机MVP。医学执行、医院展示、最终冻结和临床验收均NOT RUN；本包不是chief dispatch，不授予外传权限。

正式DATA v2 ledger SHA `bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1`通过只读消费：DATA_final_evidence_audit PASS、原3 SOP身份/Study/Series/原native索引、原/派生解码像素SHA、encoded payload及pixel/window/空间不变、header去标识、现有decoder和LOCAL_MVP限定均一致。中央decision `437158c…`/review `6f97bb9…`与旧ledger/预览binding/原派生SHA/逐图NO及负责人确认链绑定。原owner记录仍保留OWNER_RECORD_PENDING_DATA_AUDIT，DATA v2明确审计PASS；不改写原记录、不造新PASS。未读取CT/受保护PNG/GT/权重，不创建第二allowlist或改BIA。

`qa/hospital_mvp_protected.py`按实际EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V2字段验证；原V1建议ledger不作正式handoff。Case记录由DATA原样消费，不另产转换allowlist。JPEG Lossless所需现有pylibjpeg 2.1.0/libjpeg 2.4.0加入runtime版本绑定，没有安装环境组件。模型与预算保持原FrozenBaseline及CPU1、96批/2805评估、540秒/例180秒、B0/update0、无预热/重试及256MiB输出；不改FrozenBaseline、前端或核心协议。

48个轻量生成测试PASS0.06s，覆盖原预算/事务/partial与v2身份、像素、owner链、header未知、范围、审计状态及既有队列门拒绝。源码改变后新增生成浏览器attempt1 exit0：三个Occlusion jobs/3 Result/27资产、96假边界回调/2805生成评估、医学F/B/update0，Browser/SQLite Job/Result身份一致，全部自有线程/服务退出。99源码/构建文件SHA闭合，不用旧v13收据替代。

`qa/hospital_mvp_finalize.py`只消费现有metadata binding、DATA v2、owner与生成验收/退出收据，验证当前代码/包/模型/预算，采样既有wave1.serial.lock和cpu.lock可用性及slot/finished/receipt SHA。只打开既有锁、非阻塞检查后立即释放；不创建/修改队列文件，不预留槽，不查杀未知进程。旧两UNKNOWN仅按固定ceb164恢复链例外保留；新UNKNOWN、spent MVP任务、receipt漂移或busy均拒绝READY。正式运行仍由现有supervisor再次取得双门及全局预算，不把snapshot当持续准入。

固定源码后发布final readiness、queue-sample、finalization receipt及command-request，路径/SHA见manifest。command-request是供chief发布的SPEC，绝不自行生成dispatch；argv_without_dispatch_sha已有精确Python/ready及预期dispatch路径，chief正式发布后追加`--dispatch-sha <实际SHA>`两项，避免JSON自身SHA循环。若总控改dispatch路径，须重新绑定command-request，不能盲目重提实际模型任务。

启动还须总控复核DATA最终执行交付hash、readiness及队列状态。刷新和保存读取已有结果，不触发额外模型；未知提交只读对账。通过本地真实MVP后仍须医院六项空间检查、连续三次真实展示、预计算/备用录屏及钟佳桦最终批准；E1/E2/F0/F1医院注册/选版未因这份legacy开发ready而完成。

最终受测源码和实际metadata-only就绪检查提交后补录。原v11–v14历史包保留。
