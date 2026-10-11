# 2026-10-11｜医院 MVP 生成闭环及最小真实流程申请

本包是集成工程候选。三次生成流程 PASS；三次真实应用流程、医院展示批准、最终冻结和临床验证均 **NOT RUN**。负责人钟佳桦通过首席算法工程师汇总审阅，决定 PASS、CONDITIONAL PASS 或 NO-GO。计划 10/14 冻结演示快照、10/15 医院交流；本包没有自动调度或对外发送。

早期 `BLOCKED_BY_DATA_HANDOFF` 是历史快照。总控后续已验收开发DATA v3及首轮研究结果，当前真实MVP缺的是独立应用数据/调用范围及合法共享队列准入；医院专用展示资产尚未锁定。保留旧快照，不把开发交付误称医院allowlist。

工作树：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`；分支 `codex/epi-next-integration-20261009`；开发前 HEAD `0e13a1f9167be9d6f2bf815b49cf3ff9e16650b1`。实际受测文件字节、运行命令、来源提交及资产 SHA 见 [manifest.json](manifest.json)。新内容仅为 QA 接缝、生成证据和交付文档；原前端、Backend/Worker 协议、FrozenBaseline、历史 A/B/C、GT-v1 保持原字节。

## 本轮状态

| 任务 | 实际版本/入口 | 实际开始与退出 | 医学 F/B/update | 核心结果 | 当前阻断 | 下一责任方 |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | LOC `ea3bb52147d4745f473a6ef19fca5c24810184cc` 交付；storage `bc431d…`；固定 v3 supervisor `c9f5369…` | 原真实尝试 FAILED、模型前退出；本轮真实重试未开始。LOC 已保存一次生成同入口完成记录，本线未重跑 | 本轮 0/0/0 | checkpoint 恢复→原子遥测→流式输出→退出生成联调 PASS；36F/18B/18update 为 fake classifier 计数 | 一次重试及 3540 秒活动时钟尚无批准；当前共享队列 C1 新事件也需处理 | 首席算法工程师 / LOC |
| C1 | ENC 执行提交 `b37f85e86dddfe08065fef54a99aba09e6a6b6ed`；binding `604b5d…`、command `f214cf…` | 2026-10-11 01:22:51.523599 UTC→01:22:59.136270 UTC；exit 2 | 2/0/0，CPU1+MPS1 | 32768 元素数值比较 PASS：max 0.0004272461、mean 0.0000264563。清理 tensor 311107584 B、driver 1217085440 B；cleanup FAIL，整体 BLOCKED，slot_completed=false | 新 UNKNOWN 事件不能由旧恢复决议自动让行；数值通过不等于整体设备验收通过 | ENC / 总控；R1集中申请 |
| MVP 生成应用 | `qa/hospital_mvp_generated.py`；既有生产构建 `/mvp/` | attempt6 exit0，含启动/浏览器/收尾 50.272 秒；UTC 起止未独立记录；四个自有服务已退出 | 0/0/0；7 次 fake runner | 三次生成上传→分类→16/32/64遮挡→保存→原生叠加→刷新连续 PASS；另一次 FAILED 持久化 PASS | 工程生成范围已通过；不能升级为真实推理或医院批准 | INTEGRATION |
| 三次真实 MVP | 既有 FrozenRunner CPU / FrozenBaseline Occlusion，拟每例一个任务 | NOT RUN | 0/0/0 | 精确最小申请如下；不等待 E2 阳性、CT-FM head、F0/F1 | 独立数据/调用/展示范围尚未批准，且共享队列新事件未完成合法恢复 | DATA 经总控交付；总控准入；钟佳桦批准 |

所有完整 SHA、实际依赖源字节和证据路径见 manifest。只读核验 LOC 14 份源码绑定、CT bridge/contract 和固定 v3 八模块；只读核验 C1 十模块新绑定。保留旧收据，不再跑既有单元测试、R0采样或模型。备用共同 IO 锁 v4 **未接入本轮**。P1 再次批准检索无需重复；旧批准仅覆盖原任务身份，不覆盖新重试键或新时钟。

## 生成应用证据和复现

真实 loopback HTTPS Edge、Session Gateway、Backend v2、SQLite、WorkerAgent 和 Cornerstone 页面参与此次测试。存储是显式 TestStore；推理是 FakeRunner。WorkerAgent 的 Torch 异常类型和推理依赖为测试 double，manifest 函数从当前源码逐字 AST 提取；成功尝试不加载真实 Torch、checkpoint 或医学权重。没有截获业务 API 响应。浏览器禁止外部请求。

测试输入是现有 generator 生成的 112×80 棋盘 CT，含非单位方向、非等距 spacing 和 LPS 位置。FakeRunner 仅接受该次生成 DICOM 的精确字节；不能拿本入口处理患者资产。兼容现有 Result 2.0 的 wire `LIVE_CASE` 和 frozen SHA 是 **fixture 值**；截图始终标注“GENERATED TEST CT + FAKE MODEL / 非医学推理”。它们不能作为真实模型、真实 CT 或临床证据。

- [浏览器验收](evidence/browser-acceptance.json)：7 jobs，6 COMPLETED，1 FAILED，6 results，27 assets；无 page error、外部请求；三个流程各约9.5–9.7秒。
- [成功截图](evidence/generated-flow-3.png) / [失败截图](evidence/generated-failure.png)：仅生成像素和随机测试 ID。
- [几何指标](evidence/browser-acceptance.json)：五个标记全部被采到，Cornerstone worldToCanvas 与实际 overlay 标记中心最大误差 0.39894 CSS px；仅旋转、非方形 **单切片** 测试，不建立三维空间配准结论。
- [进程退出](evidence/owned-process-completion.json) / [推理隔离](evidence/worker-generated-isolation.json) / [fake调用计数](evidence/fake-calls.jsonl) / [运行日志](evidence/browser.log) / [构建日志](evidence/build.log)。

复现必须使用新的 `.local` run 目录（拒绝覆盖），并在总控允许的轻量资源窗口执行：

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/hospital_mvp_generated.py --run frontend/.local/mvp-generated-FRESH-RUN --dist frontend/.local/mvp-20261011-dist
```

测试依赖仅在本线 `.local`；前端依赖只读复用既有工作树，未改正式 Torch 环境。已完成生产 Vite build，不因整理文档重复构建。失败的 attempt1–5 保留在 ignored 本地目录，未把它们混作成功证据。attempt4 检查到 Worker 静态 Torch 导入后中断，核对精确本线父/子身份并停止；无医学调用，未终止任何身份不明进程。修正为测试 double 后 attempt6 通过。

## 算法对照和候选模型

版本化输入/输出和空间契约复用 [INTERFACE](../20261009-integration-v1/INTERFACE.md)。E1 固定目标遮挡 `INPUT_OCCLUSION`、E2 HSPI `OPTIMIZED_INPUT_MASK`、F0 `CAM_CONTRIBUTION`、F1 残余输入 `INPUT_OCCLUSION`、专家 GT `EXPERT_REFERENCE` 分开保存。原始 logits、响应数值、执行状态、坐标链、预算和产物 SHA 属于研究 sidecar；未伪装成旧 Result 2.0 的“病灶概率”。

```sh
PYTHONPATH=research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.hospital_release --manifest hospital-release/20261011-mvp-v11/manifest.json
```

这是只读算法对照入口，准入缺失会明确列出。E1/E2/F0/F1 **尚未注册到产品 Backend/Worker/UI**；现有 dispatch_selected 为独立 opt-in 接缝，默认及无 flag 回退维持原 handler。未经医院验收不能创建通过门禁的选择 flag。

| 类别 | 当前状态 |
| --- | --- |
| 当前应用默认 | 保留 FrozenBaseline `baseline_resnet18`；checkpoint SHA `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`；原16/32/64 Occlusion可用。医院默认模型仍未选定 |
| E1 研究基线 | `E1_BASELINE_FROZEN_WITH_LIMITATIONS`；10%共同FOV面积预算下16/32/64的**三例患者平均**已标注覆盖为0/0/4.2808%，不能写成每例成绩；填充对照无增益，不重跑 |
| E2 实验 | 六条旧真实轨迹共6000步联合CPF可行数0；保留轨迹、数值及负结果；P1真实恢复未运行，不要求阳性才可做MVP |
| F0 未完成 | 没有已训练并验收的真实head；本轮C1只核对编码输入/设备，不构成F0定位证据 |
| F1 实验 | 合成实现/联调范围；没有医院真实应用验收 |

## 一次性最小真实 MVP 申请（尚未批准）

沿用 DATA 唯一正式开发交付及已锁定三张 SOP，使用既有 prepared_delivery SHA `b85eaf6c78d1547e2aa4b93458734f533d34be5de1ed056fd152c30b92ebaa99` 的 case_index 1/2/3。既有 3人/715 SOP 是开发范围，本申请只消费其中 **3 SOP**，不新增患者、不用封存测试集、不自行签发第二份 allowlist。原 `three_case_proposal.json` 仅是提案，不能替代医院批准。

| 独立批准项 | 精确范围 | 执行条件 |
| --- | --- | --- |
| D：应用数据及派生许可 | 三例已锁定切片，DATA确认符合现有上传去标识规则；必要时由DATA发布3张去标识单切片派生物及SHA/原始SOP映射，保留像素、IOP/IPP/spacing，不改原始CT | 只通过总控接收派生路径和实际SHA；当前不读取/生成真实派生物。医院allowlist由DATA/总控唯一发布 |
| M：真实计算 | 三次新Occlusion任务，各含16/32/64。CPU单线程、冻结模型和预处理不变；每次原图1+遮挡729+169+36=935图像评估，batch32对应1+23+6+2=32次模型forward；总96批forward/2805图像评估、B0/update0 | 不另点分类任务，不预热/重试/诊断求导。每流程180秒、总540秒，包含加载/审计/保存/浏览器/退出；输出总256MiB；采样RSS5GiB预停/6GiB监测目标不冒称硬上限。Chief以既有监督器/串行队列唯一dispatch，C1新事件合法恢复前不得计算 |
| H：展示准备要求，**NOT_REQUESTED** | 候选仅3张选定切片、对应保存结果/预计算及本地备用录屏 | 当前没有精确展示资产路径/SHA或已批准受众清单，故不提交模糊展示申请。D/M完成后，经总控提交资产哈希及受众明确的独立H申请；未获批不现场显示、不外传、不上传或部署 |

任务键提案 `EPI-NEXT-HOSPITAL-MVP-THREE-LEGACY-CPU-20261013-V1`；是 **REQUEST_ONLY_NOT_APPROVED**，不挪用 P1/C1 配额。相同事务结果未知时先查 job/attempt/Result/asset SHA；如果已有结果只读取，不追加第四次任务或自动重提。三次读取预计算不算三次真实端到端。当前申请不是设备恢复批准，不能释放C1新槽。

96是**模型batch调用数**，已含每例1次基准分类，共3次基准前向；不是96张扰动图像。扰动样本每例934、总2802，连基准总2805。batch上限32：16px每例22批×32+尾批25，32px为5批×32+尾批9，64px为1批×32+尾批4；另基准batch1。所有恢复/核验前向均计入96，不保留额外校验调用额度，失败停止不自动重试。算法锁定**历史FrozenBaseline/Stage1 Occlusion**，不能写为研究E1。

## 八项验收、演示步骤和回退

| 医院验收 | 已完成工程范围 | 医院真实范围 |
| --- | --- | --- |
| 1 原始脱敏CT正确显示 | 生成单切片显示 PASS | NOT RUN；等待D |
| 2 模型真实结果追溯 | fake invocation/源码/资产SHA已保存 | NOT RUN；等待M |
| 3 热图空间对应 | 生成单切片原生overlay PASS；既有空间单位测试/正式DATA证据复用 | 真实产品显示 NOT RUN；左右、原生世界坐标必须核对；本版不宣称Series三维演示 |
| 4 保存和刷新恢复 | SQLite实际保存+刷新 PASS | NOT RUN |
| 5 失败显示 | 真实Backend保存FAILED，刷新恢复，无完成链接 PASS | NOT RUN；不为验证失败增加医学调用 |
| 6 旧版回退 | 16/32/64切换、现有handler默认路径 PASS | NOT RUN |
| 7 连续三次真实演示 | 三次**生成**连续 PASS | NOT RUN，不可代替 |
| 8 真实预计算+备用录屏 | 生成截图已留存 | NOT RUN；等待D/M/H |

获批后：登录→创建独立匿名病例→上传DATA交付的固定单切片→核对原生CT→**只运行一次16/32/64遮挡任务**→记录job/attempt/模型和资产SHA→显示原生叠加与三个尺度→刷新确认同一Result/设置恢复；按既定次序重复三例。保存真实运行日志、空间检查、三次记录和真实预计算；H获批后录本地备用视频。实时与预计算入口标明来源，现场不为刷新重复计算。无可靠响应展示实际状态及原始CT，不用假阳性热图补位。

回退：停止选择实验flag，回到当前 FrozenBaseline 结果及16/32/64。只读重开已完成Result，不删除旧job/资产，不覆盖实验输出；需要新的计算必须重新检查具体许可和队列。实时故障先对账，切到获准预计算真实Result；服务不可用则播放获准本地录屏。空间链未验证、资产SHA不匹配或身份无法追溯的结果退出展示候选。无已获准备用结果/录屏时不得宣称可完成真实医院演示。

10/13完成获准流程验证后再按真实证据选择默认；10/14固定代码/配置/清单/模型/预计算/录屏SHA和所有失败状态，由总控交钟佳桦。当前仅可交付生成工程快照，不能宣称医院正式获批。
