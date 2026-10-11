# 受保护MVP接缝交付｜2026-10-11

指定工作树`epi-next-integration`、分支`codex/epi-next-integration-20261009`；开发开始HEAD `05a4279177e5d09b80ce3c634fae65c714abca89`。本包是本机工程接缝候选，医院默认模型仍空缺，医院最终冻结和临床验证均NOT RUN。负责人钟佳桦通过总控收集后决定PASS / CONDITIONAL PASS / NO-GO。

`qa/hospital_mvp_protected.py`围绕现有FrozenRunner、WorkerAgent、Gateway/Backend及生产前端构建提供独立本机验收入口，不改历史A/B/C、GT-v1、FrozenBaseline、预处理数学、原核心协议或前端源码。旧FrozenBaseline和16/32/64 Occlusion继续保留。E1/E2/F0/F1没有因本次接缝而成为已注册医院算法。

批准scope只覆盖原固定3 SOP的本机开发派生及三个历史Occlusion jobs：每例32批/935图像评估，总96批/2805图像评估，B0/update0，无预热、无额外分类jobs、无自动重试；总540秒/例180秒、输出256MiB。原16/32/64位置分母和batch序列保持不变；全模型pre-hook先持久预约，post-hook保存原始logits。进入、完成及未完成前向分别保留。刷新只读，不触发模型。

单次提交响应不明确时，对本地SQLite的Job/Attempt/Result、完整submission_digest、保存的资产描述及对象字节进行只读对账；拒绝重发和重算。同Job换Attempt亦不重算，claim/download失败停止。源代码与生成的原生资产、原始数值/logits及SHA独立保全，失败partial产物不随Worker临时目录删除。仅终止本入口创建的三个服务；非daemon Worker及心跳未退出时不得宣告资源恢复。

消费唯一v12恢复链index SHA `12e808bcf23f80571886fa0e8c68efa88a11fb833a51db002ab1820d20fc1a6d`，dependency SHA `093e0a7fd137ae9772dd30595fe39de845a7babe9de1617d633782a02707a192`；没有改索引、旧v3、v4共同IO锁或LOC源代码。真实入口必须同时绑定：owner/scope、新C1决议、DATA派生ledger、当前受保护入口的生成浏览器验收与退出收据、全部本机应用源码/生产构建SHA、包版本、Python及chief exact dispatch。新metadata工具只输出NOT READY fragment，不创建allowlist、批准、dispatch或队列记录。

实际验证：29个轻量生成fixtures PASS，pytest 0.03s；没有Torch导入、权重/患者像素读取、模型F/B/update、队列读取/写入、GPU probe或新浏览器/构建。覆盖96/2805计数、预算/未完成计数、同Job多Attempt拒绝、丢失响应单次对账、字节/身份/描述漂移、partial保全、部署凭据隔离、dispatch绑定及BurnedIn UNKNOWN门。命令见tests.log。复用v11三次生成应用闭环证据及v12恢复链20项证据，不重跑、不冒称为新入口浏览器通过。

总控当前P1真实续接占用唯一模型资源槽；本轮没有并发Torch、浏览器或重型构建。受保护入口的生成三流程浏览器测试仍NOT RUN，须在总控资源窗口执行并保存当前源码关联收据，不能用旧v11收据替代。

DATA确认原3 SOP缺BurnedInAnnotation，保持UNKNOWN。真实上传ready BLOCKED，等待负责人逐图像素复核后由DATA经总控发布新派生ledger及人工检查记录。header去标识、手填NO或合成测试不能代替。集成消费字段与上传约束见v12/DATA_MVP_UPLOAD_HANDOFF.md；正式DATA字段映射尚未完成，不自行制造记录。批准scope仍有效，数据与工程门完成后等待P1终态/恢复核验及总控唯一MVP dispatch。

医院八项真实验收全部NOT RUN；缺医院展示allowlist/模型结果/六项实际空间检查/三次真实流程/预计算与录屏/负责人批准。当前阻塞是应用派生像素复核、受保护浏览器验收及chief串行dispatch，不再以早期715 SOP研发handoff未交付笼统替代。医院展示未批准，未上传、push或部署。

代码源提交、metadata fragment路径/SHA与最终检查在manifest提交后补录。v11/v12已有历史manifest不改写。
