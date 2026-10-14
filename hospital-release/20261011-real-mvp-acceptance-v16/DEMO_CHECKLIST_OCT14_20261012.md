# 10月14日基础演示清单｜2026-10-12管理补充

INTEGRATION唯一维护；首席算法工程师汇总，钟佳桦批准。**HU v5、新分类头、E2正收益退出基础关键路径。** 本地真实MVP PASS（3/3），医院展示NOT_APPROVED、最终冻结NOT RUN。已按既有本地许可完成一次计算关闭的真实只读恢复：原三影像/结果在本机浏览器实际渲染、技术坐标与刷新验收通过。没有新推理、截图/录屏/导出；人工目视与医院受众展示未执行。

## 版本和证据

真实受测source `54ff1565f6c11a6deea873feab0a011e879528fb`；v16交付 `510d387ef02d55c22f01f9cbd282137ea1274934`；原manifest SHA `c8bcb4cc795cdafd36c93588b6d826ef8de69764e9b086618eb5b0fa038051c8`。基础模型baseline_resnet18/FrozenBaseline，checkpoint SHA `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`；formal-resnet18-baseline-rule-b-v1，stage1-occlusion-instability-v1，16/32/64 Occlusion。

[真实验收](ACCEPTANCE_REPORT.md)、[命令历史](COMMAND_RECEIPT.json)、[指标](METRICS.json)、[快照索引](RECEPTION_AND_SNAPSHOT_INDEX.json)：3 Job/3 Result/3接受attempt/27资产，96前向批/2805评估，B/update0、retry0，三真实开发流程通过。原服务已退出；旧目录中的20261013不是执行日期，实际执行2026-10-11。原dist `frontend/.local/mvp-20261011-dist`保留；现有集成树含v17新代码，不能给新版本自动套旧3/3。

## 算法能力和基础演示范围

| 线路 | 已有能力 | 本次定位 |
|---|---|---|
| FrozenBaseline＋旧Occlusion | 原应用实时提交/保存/显示实际跑通3/3；当前没有服务在线证明 | 基础默认保留，只读复用现有结果；不重新调用模型 |
| E1/E2研究预计算 | 独立研究结果与版本；v17 E2 adapter/零模型PRECOMPUTED只有合成应用链验收，默认API及前端flag关闭 | 研究附录，不标真实E2已装入基础前端。独立5F CLI非应用闭环，target_class0/fixed_target1差异保留 |
| CTFM编码/F0/F1 | 编码/特征接口与已训练分类头是不同能力；v17只有体积/head契约及注入测试 | 实验线说明；无基础包真实分类头/volume handler验收，不阻断基础交付 |

**当前基础MVP没有真实E2应用接入验收。** 不把旧Occlusion替名E1，不把研究Mask/gap/PSMI、Occlusion响应与专家GT统称病灶概率。新医学计算、线上切换与医院显示均非本轮授权。

## 启动与回退

1. 核对原manifest/唯一DATA ledger及精确版本；不要复制已消耗COMMAND_RECEIPT命令，它会进入推理Worker流程，不是恢复命令。原数据/DB/资产不覆盖。
2. 旧setup凭据有效期1小时，不能假定10月14日可登录；不导出或传播旧private-config、账号或密钥。
3. **计算关闭的本机只读恢复入口已实现，4项生成测试PASS；R71实际一次只读恢复技术检查PASS；人工目视NOT_RUN。** 目标：新私有运行目录和SQLite副本、新认证，仅127.0.0.1；禁止新增任务/上传/全部Worker接口，读取原已保存结果；没有新模型/Worker启动。精确命令见下节；生成验收、R71真实恢复与旧54ff三真实推理流程分别引用。
4. 仅在获准本机启动后：登录→原三个Result→原生CT/对应16/32/64响应→刷新恢复；R71已按原LOCAL_MVP_ONLY许可实际渲染原三影像并核对保存结果；未重新上传或创建Job，未进行人工目视或医院展示。
5. 回退：停止自己拥有的恢复进程，原SQLite/对象/旧dist保持；关闭实验flag，不做破坏性downgrade/reset/clean或杀未知进程。继续获准本机查阅旧保存结果；无法安全恢复则交负责人决定暂停显示，不用新推理救场。

## 已有证据与缺口

| 项目 | 已有证据 | 剩余边界 |
|---|---|---|
| 原生叠加 | 三单SOP；64选中像素校验通过，16/32/64选择通过 | 三尺度逐像素人工验收、完整Series方向/顺序/world/crop/resize/resample未齐；映射无法验证不进入医院候选 |
| 保存刷新 | 三Job/Result/Attempt/对象SHA一致、刷新保持64 | 新恢复方式生成验收单独记录；R71实际启动/渲染/坐标技术检查PASS，人工目视NOT_RUN |
| 错误提示 | 原Job失败解释/查询与图层恢复及生成FAILED回归；新六状态生成证据 | 这三真实流程未触发真实失败；不把生成故障写成医学失败验收 |
| 备用材料 | 原开发预计算/截图和SHA保全 | 本地同存储快照非独立备份；医院用途批准、合格录屏/播放检查未完成，本轮不制作 |
| 现场审批 | 本地MVP已接收 | 受限三图的医院展示用途仍待负责人决定；不新建复杂场地/人员审批体系，14日PASS/CONDITIONAL PASS/NO-GO仍由负责人作出 |

## 医院展示数据/用途申请候选（非许可，不创建第二allowlist）

唯一DATA v2 ledger：
/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-data-eval/.local/phase2/mvp-three-sop-owner-reviewed-v2-20261011/MVP_THREE_SOP_DERIVATIVE_LEDGER_V2.json
SHA bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1

仅引用其case_index1/2/3三脱敏派生单SOP，非整Study/Series、源ZIP或新病例：

| 原ledger case_index | 派生DICOM SHA256 | 原本地路径 |
|---|---|---|
| 1 | 8394e5240ff928c4610dc5452f7d173b7bbf88d7ade43fb41893f7ae27fd3f7e | /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-data-eval/.local/phase2/mvp-three-sop-owner-reviewed-v2-20261011/case-1.dcm |
| 2 | 23935291ea6a761494973178f8aba45e8bee6879ec2b5e097866504c83839ecd | /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-data-eval/.local/phase2/mvp-three-sop-owner-reviewed-v2-20261011/case-2.dcm |
| 3 | 2079ccfa6e601d5c9580a9b7f45ebace0075956ccf758d0feb43052b2af4f3c3 | /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-data-eval/.local/phase2/mvp-three-sop-owner-reviewed-v2-20261011/case-3.dcm |

Study/Series/SOP身份、native索引、像素复核与几何值保全以原ledger为准，不复制患者UID到公开文档。各记录权限原文`LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION`；hospital_display_authorized=false、external_imaging_upload_authorized=false。本机许可不等于医院/外传许可。

拟申请10月15日将这三单SOP及严格绑定的FrozenBaseline/Occlusion现有Result用于医院只读科研系统演示，说明模型行为局限、无诊断用途/新推理/训练。总控只需合并受限素材的明确展示/传播用途决定，不新建复杂场地/人员审批体系。正常联网、Wi-Fi、热点、HTTPS、投屏及既有合法控制平面允许，不作为新阻断；但网络或投屏许可不自动授予这三图向医院受众展示、外发、截图/录屏许可。该章仍为候选、无新allowlist或代签批准。用途未获批时，可展示无受限像素的流程/架构示意和已有合法材料。

## 已实现的只读恢复命令与增量验收

[固定命令索引](READONLY_RESTORE_COMMAND_INDEX_20261012.json)绑定本恢复源码和旧dist，不含账号/密钥/数据库正文。元数据校验不会读真实DB或像素：

```sh
cd /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps \
 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/local_mvp_readonly.py \
 --binding /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/read-only-mvp-binding-v1.json \
 --binding-sha b03d88d251eb658d285d66462f550f4d2c392798c930c13bf7dd4e0ce1c0d1e4
```

获准本机操作员要读取原已保存结果时，在上述命令后加以下参数（接口已在R71真实恢复中验证；已消耗验收目录不得重用，本轮已退出）：

```sh
--serve \
--run-directory /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/mvp-readonly-20261014-01 \
--dist /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/frontend/.local/mvp-20261011-dist
```

新目录必须不存在；不重复使用旧MVP命令/任务/输出。脚本保全原SQLite和对象，复制DB到新私有目录后，只在副本撤销旧认证并签发8小时新认证、关闭Worker；必要时续同三源影像的副本读取期限，不新增影像或模型准入。R71已实际读取原SQLite私有副本并使用新认证；手动目视仍NOT_RUN。

等待restore-ready.json后，终端只给本机HTTPS URL及private-config.json路径，不输出密码。操作员在本机私有文件读取新账号/密码，登录现有/mvp/页面，查看原三Result。页面只读提示明确；所有新任务/上传/变更及Worker接口403，直接对象旁路也拒绝；原结果source仍保留其历史LIVE_CASE，不改成新模型运行。本次实际PASS快照仍复用localhost自签证书和本机部署，不安装系统证书、不改部署。负责人允许普通联网/HTTPS/投屏和既有合法控制面；无须为此重构或重新验收无变更功能。全部独立GPU AI Node排除，不增加CPU/MPS实时推理或医学调用；本恢复不启动任何Worker或旧推理命令。

停止按一次Ctrl-C，等restore-exit.json确认三自有服务退出、source_db_unchanged=true、Worker未启动/model_calls0。回退只停止这组已知自有服务、继续保留原v16；再启动使用新的运行目录以重建会话，不清空或覆盖原记录。不终止未知进程。

增量结果：4项定向生成测试PASS2.09s，新认证/过期输入副本读取/结果和资产SHA/刷新一致/拒绝写与Worker/无覆盖及错scope/实际loopback HTTPS登录静态提示和停止回收。只有生成病例/PNG；生成测试阶段没有DICOM解码、模型、浏览器/截图或真实DB复制；其后R71按原许可做独立真实只读恢复，见下节。旧54ff 3/3真实验收不重跑；R71实际渲染/坐标技术验收PASS，人工目视NOT_RUN。这一非医学接入完成不依赖HU v5、训练头或E2收益。

受测恢复源码已固定：`76d032edbd270a1e52b29750e3afbbbda6d7f508`；原真实MVP受测源仍为54ff1565f6c11a6deea873feab0a011e879528fb。命令索引中的restore_source_commit指新恢复代码，不能替代旧3/3验收版本。

## R71独立真实只读恢复｜2026-10-12

[十项实际记录](READONLY_R71_REAL_ACCEPTANCE_20261012.json)：单次总7.979秒（上限180），原3Result/3单SOP、9尺度选择与每例64刷新均实际通过，新登录成功、旧凭据401；网络只有本机、page errors0。渲染/几何badge、图层224尺寸、非退化变换和canvas/viewport边界一致为第6项技术PASS；没有人工目视或医生认可证据，单列NOT_RUN，不写医院空间/临床PASS。

恢复源76d032保持；此次验收封装源482215cecdb133e2edcb271d226cd9c2b32ee546，不替换旧54ff原3/3。三服务受控SIGTERM退出（exit_code=-15），恢复父进程exit0；原DB/SHA、30对象及Case/Job/Result/Attempt/Asset表不变。只在私有副本更新认证/读取期限。上传/新任务/Worker/写接口403，无Worker或模型启动，新增F/B/update0；无PNG/DICOM/视频/HAR/截图/像素导出。已有记录留原本地权限；医院受众展示与录屏仍NOT_APPROVED。失败不重启、未运行新医学任务。

## R72｜A/B已有方案比较与选择（2026-10-12）

**选择A，保留已PASS实现，不切换部署。** 本次仅核对已有源码、配置和收据；R72所述“真实恢复未完成”是较早状态，由R71实际技术PASS及收口提交 `e1731dd413bd1782600c94d3955d62fa2a80522d`更新。本轮没有启动、重跑、断网测试、云/SSH访问或新增验收。

| 比较项 | A：本机只读恢复 | B：已有联网前后端 |
|---|---|---|
| 成熟度 | R71 `PASS_TECHNICAL_READONLY_RESTORE`，人工目视NOT_RUN；三服务已正常退出 | 2026-09-28 Phase5有合成数据、含RTX3090的历史全链路PASS；当前无GPU只读方案 **NOT_VERIFIED**，不推断线上状态 |
| 启动 | 既有单一恢复入口启动Backend/Gateway/HTTPS edge三自有服务，ready后给URL；新私有目录/认证，旧dist不变 | 模板含Nginx/Gateway/Backend/PostgreSQL/MinIO及Sweeper；当前启动、认证有效性及关闭GPU后的配置未核验，NOT_VERIFIED |
| 历史Result | R71原3Result、9次16/32/64选择及三例刷新实际PASS | 历史报告仅证明当时合成Result持久化/读取；当前可读性及本地三Result在B的可用性NOT_VERIFIED |
| 数据路径 | 原SQLite复制到新私有运行目录；原对象目录经SHA核对只读，DICOM与资产经认证API返回 | 历史路径为公网HTTPS→Nginx→Gateway→Backend→PostgreSQL/私有MinIO；没有当前三图云端可用或外传授权证据 |
| 网络/GPU | 所有通信为本机loopback，无云/DNS/独立GPU节点依赖；不启动Worker/model | 历史模板有Worker直达Backend路由，报告含独立GPU；当前是否已隔离GPU及公网/服务健康NOT_VERIFIED |
| 回退 | 停止已知自有恢复进程，保留原v16/DB/对象/dist；后续获准启动使用新目录，已消耗R71目录/命令不重用 | 历史报告有同盘配置/构建回退说明；当前备份和恢复有效性NOT_VERIFIED，本轮不操作远程服务 |
| 额外医学计算 | 无；R71新增F/B/update0，所有新任务/上传/Worker/写接口403 | 读取已保存结果原则上不需推理，但B当前无计算约束未验收；不发任务、不用额外医学计算补证据 |

A实际通信：本机浏览器 `https://127.0.0.1:<edge>/mvp/`读取旧dist；同源 `/auth/`、`/api/v2/`由edge经HTTP loopback转Gateway，再转Backend；认证/会话与SQLite副本均在新私有目录，Backend使用ReadonlyStore读取原本地对象，不走MinIO/S3或云控制面。端口由每次启动分配；以该次ready/私有配置为准，不复用R71端口。依据：`qa/local_mvp_readonly.py`、`qa/phase5_local_https.py`、`session_gateway/app.py`；R71 external_request_count=0、model_calls=0、worker_started=false及退出收据与现存SHA一致。

**断公网影响为配置推断，不是断网验收：** 已安装依赖、旧dist和原对象齐备且本机三服务正常时，A登录/结果/图层/刷新路径没有公网依赖；断公网不应影响这些功能。外部控制服务和依赖网络的无线投屏可能受影响，投屏链路未验收；本机服务/存储或8小时认证失效仍会影响A。正常联网/HTTPS/投屏允许；不为联网放弃A，也不将网络许可升级为三图医院用途许可。

精确版本及回退沿用上文：恢复源 `76d032edbd270a1e52b29750e3afbbbda6d7f508`、R71验收源 `482215cecdb133e2edcb271d226cd9c2b32ee546`、原MVP源 `54ff1565f6c11a6deea873feab0a011e879528fb`、v16交付 `510d387ef02d55c22f01f9cbd282137ea1274934`；binding SHA `b03d88d251eb658d285d66462f550f4d2c392798c930c13bf7dd4e0ce1c0d1e4`保持。R71公开收据SHA `38b0cbd8ae2277588da71cb38715c0fd70469f13192cdfef7efd05dc053bca8c`；B只引用[历史报告](../../docs/phase5/gpu_final_handoff_report.md)和`deploy/mvp/nginx-locations.conf`/服务模板，不扩写成当前部署验收。医院用途未批准、最终冻结NOT RUN；未获素材用途批准时沿用无受限像素的流程/架构说明。

## 管理网络修订与本轮停止点

正常网络不是阻断，也不要求完全离线或localhost为唯一可能部署。当前按已实际PASS的本机只读恢复交付，不因政策放宽切换部署/增加计算；全部独立GPU AI Node均不进入展示架构。三图原LOCAL_MVP_ONLY素材边界不变，医院展示用途未自动获批；未获批则采用无受限像素的技术示意。R71原独立执行已退出，本轮不新增测试/恢复/截图/录屏，停止新增工作，等负责人用途决定。


## 迁移接续最终收口｜2026-10-13

当前仅锁定**候选**：原DATA唯一v2三单SOP、对应历史Result、64尺度Occlusion。16/32、完整Series/3D、未验收研究算法不进入拟议范围；旧v16仍是历史回退版本，不将其原全尺度能力称为已落实64-only限制。

既有private-audit.json（本工作树 `research/next-hospital-20261014/.local/phase2/mvp-real-offline-audit-v16/private-audit.json`，SHA `a186cc714eaa8dccaf84c4c217fe03ab249ad5979509516e8696a33809ae9ac4`）保存准确路径及SHA。下表按`artifact_inventory`的原键绑定，不另建数据allowlist，不读取Result正文、像素或图层内容：

| 原case_index | 历史Result键 / SHA | 64图层对象键 / SHA |
|---|---|---|
| 1 | `case 1 result` / `9cc5ab99f42f64f5ecd5adb9b3b888f6ebf77245f8a6d3ac81e0f5899edfde84` | `case 1 stored candidate-64.png` / `c4041631368acb1c0a274a329398e168a0cf74aabe15e37f4a294c114ceae65d`<br>`case 1 stored response-64.png` / `10faf7717b701ca33a134cf038bb0a1a96a96b6c668370b27d7cadc1fe276dc7`<br>`case 1 stored comparison-64.png` / `46d1d47b9e7b8d9b2a12aa688e91df1a8ca3b8f6e6f5ff21b12d69dde3b76b55` |
| 2 | `case 2 result` / `b8337c0353e1400ab1042d658a67b4e9ac48c228151f6e1f278190c23a19ab5f` | `case 2 stored candidate-64.png` / `c797f57f73f49d8ae7673839c0472ad518e5877e432f51ee1be7dc044bc92c4b`<br>`case 2 stored response-64.png` / `2e25eb2456540592ff6e06ed081e820c845e26b22390e139637129e1bad67094`<br>`case 2 stored comparison-64.png` / `e1cdae133b06c96ae0d53d5f90cebe9655e92f696776b9e4b321ece37eb1ee3f` |
| 3 | `case 3 result` / `6e4874034639c098f8cabc4a671e1d5c2c075b51f859ffd795743515aba05375` | `case 3 stored candidate-64.png` / `c4041631368acb1c0a274a329398e168a0cf74aabe15e37f4a294c114ceae65d`<br>`case 3 stored response-64.png` / `19c4b319cb6842f9fc3f1ca4e7cfbba7cf4b92f5da50be371bf0b70a237dad48`<br>`case 3 stored comparison-64.png` / `70220f0bb009d1dbaacc249015ee8413f22ee2eeeaae78b6f045675bb35a2e82` |

这些是保存记录中的映射，不是本轮重算图层SHA或空间验收。原三SOP与人工身份复核继续绑定唯一DATA v2 ledger `bc9198383f12eb231e9125e8cf5a65a6f67a2f37d2233b7ad46b5308023ac6c1`，不重复人工身份复核。

DATA新增独立expected坐标：`.local/phase2/mvp-display-metadata-preparation-20261013/DISPLAY_COORDINATE_EXPECTATIONS_V1.json`（DATA工作树），SHA `270533c2b878cfe49a81335d99fa452db3aed9617c6b923457801e137dd16578`。其E1/E2 prepared网格不能直接当作旧FrozenBaseline/Occlusion生产链已通过；仍需独立核对原生位置、真实64层格网、crop/resize、viewer flip/rotation/viewport以及叠加目视。

原INTEGRATION会话后续工程因服务503中断，现场保留未跟踪`frontend/demo-candidate/`的两文件与`qa/demo64_build.py`，未纳入本轮提交，未运行构建/恢复。当前缺64-only冻结dist、与三Result匹配的API限制验证及空间核验；不能仅凭候选代码称入口已关闭。

用途状态：LOCAL_MVP_ONLY；医院展示NOT_APPROVED，三次最终演练NOT_RUN，录屏/播放NOT_RUN，最终冻结NOT_RUN。候选用途为展示既有历史分类输出和输入遮挡响应，不作疾病诊断或实时推理；现场展示与备用录屏必须分项批准。普通联网/投屏不替代素材用途。没有获准录屏，不能把录屏作为已可用回退；当下保底仍是无受限像素技术材料。

本轮仅维护候选清单和缺项，不启动服务、不新增Job/Worker/模型调用或患者影像显示。旧开发3/3与R71技术PASS不抵扣最终三次演练。具体用途/演练/录屏待决继续由现有合并待决表统一呈交。


## 64-only候选工程冻结｜2026-10-13

本节更新此前“中断/未构建”状态，旧v16/R71和历史失败保留。源码提交 **c3ddad7064c79ba6afd24884c5ec3abed1bcf8ce**（codex/epi-next-integration-20261009）；候选构建位于 `frontend/.local/demo64-candidate-20261013-v2/dist`，21个文件。

私有冻结清单：[frozen-candidate-v1.json](../../.local/demo64-candidate-20261013/frozen-candidate-v1.json)，SHA **191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917**。它绑定190个源码/旧恢复文件、完整dist、23项runtime引用、生成来源清单、原DB/对象索引与候选投影。投影SHA **b0dcd6e69cb057e8be3b92ac6a052b8d3415442ee4042f6771efbf1b3c5b934a**，仅从唯一DATA ledger与已有offline audit导出，三SOP/Result/9个64资产的精确身份仍在私有目录，不是新数据allowlist。权重仅沿用历史checkpoint身份，查看不加载权重。

| 项目 | 本轮状态及证据 |
|---|---|
| 64-only前端 | 3项生成测试PASS；只保留历史三结果/登录/偏好路由；旧16/32偏好不恢复，图层只取64，直接其他Result不读取影像。无Series/3D/研究入口 |
| API/对象范围 | 8项生成测试PASS（2.26s）；严格匹配三Result、三单SOP、9个64图层，16/32和其他对象、上传、新Job、Worker及写接口拒绝；源DB不变。HTTPS登录探针仅内部映射，直接病例列表拒绝；退出后401 |
| 构建 | vue-tsc + Vite8.3.1 PASS；旧codec browser-externalization及大chunk警告保留。隔离构建不覆盖旧dist；未进行本候选真实浏览器流程 |
| 几何 | 原11项生成数值测试PASS，与新增前端3项合计14项/590ms。仅验证数学与生成数据，不填实际空间PASS |
| 保存对象保护 | 原恢复绑定66项源码/dist SHA一致；本轮没有读取影像像素、复制真实DB或重哈希原对象payload；没有修改原DB/资产 |
| 服务 | 测试仅使用生成DB/PNG/fake-DICOM字节，三自有loopback服务退出；无Worker/模型。真实候选服务NOT_RUN |
| 医学读出 | R18/E2-R新attempt NOT_RUN；无新admission/slot/dispatch。工程测试不建立科研提升 |
| 医院及最后验收 | 医院用途NOT_APPROVED；真实空间叠加、人工目视、最终三次演练、录屏与播放NOT_RUN。候选工程冻结不等于医院最终放行 |

生产链静态核对：`src/preprocessing.py`采用HU/窗映射、整幅bilinear antialias resize到224、无preset crop，然后复制通道/标准化；`algorithm/service.py`64窗口、stride32、fill0.5生成响应，candidate/response为224平面，comparison为14区域均值栅格。14栅格不能误称64遮挡采样格网。`frontend/src/viewer/geometry.ts`及`CornerstoneSliceViewer.vue`利用rendered image indexToWorld/worldToCanvas和四角验证构造画布affine，受实时viewport影响。这些代码/生成测试没有验证本次真实SOP的crop/resize、flip/rotation、viewport及叠加残差；DATA prepared expected参考不替代这条链或人工目视。

既有许可核对：原LOCAL_MVP_ONLY和持续的同三例本机研发/保存结果复用记录已覆盖本地只读技术检查，不再次申请同一用途；R71单次收据仍只证明当次运行。本轮按已指定静态/合成收口范围停止，未将旧R71流程重做或记作本候选三次最终演练。后续真实技术/人工验收须继续引用原许可与冻结候选，医院受众展示、最终演练用途和录屏范围继续由原待决表集中处理。

元数据检查（不启动服务、不读影像）：在INT根执行以下命令。实际`--serve`应只在匹配用途/验收范围下使用，配新`.local`运行目录；原v16入口保持可回退，不能重用已消费验收目录。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps \
 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/local_mvp_demo64.py \
 --candidate .local/demo64-candidate-20261013/frozen-candidate-v1.json \
 --candidate-sha 191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917
```

仅此候选未来获准启动时使用新私有目录，原恢复架构保持三自有服务；Ctrl-C后检查该目录restore-exit.json确认三服务退出与原DB不变。失败不杀未知进程、不自动重启；录屏尚未获准/生成，不作为已可用回退。没有影像用途时采用无受限像素的现有架构、流程和真实研究汇总材料。


## 64-only首次真实技术核验｜2026-10-13｜FAILED_OR_PARTIAL

负责人直接消息01a134e5-e172-76b3-83e4-7dc09f0bc7a6明确允许对候选SHA `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917`进行一次本机只读技术核验，不包含医院用途、截图、录屏或外传。沿用既有三SOP用途，新私有目录 `.local/demo64-technical-20261013-01`，未重用R71目录；原v16/DB/对象保留。

真实服务启动与登录PASS。脚本首例取得Result、仅64摘要/资产集合以及DICOM SHA断言通过后，等待“单切片 DICOM 已恢复…”可见时失败：元素已匹配但hidden。原始receipt checks仅持久化services/login；先前断言执行由驱动顺序与失败位置支持，不冒充完整三例验收。三Result、9图层、刷新、真实接口拒绝、独立实际空间映射尚未完整执行；计划中的DICOM LPS+相机投影公式未取得实测，不能填PASS。该断言失败也不足以判定图像解码或空间算法失败。

acceptance.json SHA `884e5a8a971c34e70c2f5624c9c04a7d5dbd47968a41cd22eff2b7bbc58e7c89`；私有驱动 `.local/demo64-technical-driver-20261013.py` SHA `716bab8b2f399142fed37057fcfaca20a389cef9197ea27e6c0d16a5677133fc`，未改冻结源码/dist。总8.908842秒，浏览器已关闭，三自有服务SIGTERM退出，源DB SHA不变；Worker未启动、model_calls0、external_requests0、page_errors0、截图/视频/trace/像素导出0。人工目视NOT_RUN，最终三次演练计数0，医院用途仍未批准。

不自动重试。本轮技术核验已消费，后续先修正readiness断言与证据分步保存，再明确允许新的单次核验；不能因为生成测试PASS或DOM提示存在就回填真实空间/目视PASS。唯一状态writer已记录revision84/CONSISTENT/pending0，SHA `84a1b8a4a9454f7327da89221b60d32e874df2f9d1b3728a546a1eec1e502875`。

## Revision85 后工程诊断｜2026-10-13｜无真实重试

84→85 是原 writer 的 `BOUNDED-CLOSEOUT-DOC-INDEX-20261013` 文档索引提交，理由为绑定已提交清单；没有新执行。上节84是执行收口快照，不应回退当前状态。

旧 hidden 回执未保存 computed style/祖先状态；源码提示为 ready && !loading && !error 条件节点，源码/CSS检查未证实它被设计为隐藏，也没有重复节点证据。**旧真实隐藏根因 UNKNOWN**，不宣称应用正常或已显示。

仅验收侧修改：`qa/demo64_readiness.js/.py` 监听当前 image/viewport 的真实渲染事件并检查 decoded、rendered_status、可见非零 canvas、无可见加载错误与当前资产实际 draw；清空 overlay 会使 readiness 失效。`qa/demo64_technical_v2.py` 保留三Result/9资产、刷新、拒绝接口和原独立空间检查（原固定点、0.5 CSS px 容差未变），替换提示文字断言；每步原子持久化，主失败/清理失败分开。默认只检查元数据，真实运行需新的精确确认。

生成 DICOM 走现有 CornerstoneSliceViewer 实际解码/渲染链，覆盖无当前影像、隐藏提示但已渲染、缺资产、错资产、异步资产就绪、旧渲染代次、清空图层及提示存在但解码失败。浏览器回归通过；日志模块和实际驱动 finally 的成功/失败清理另有合成回归。无真实三SOP服务、截图、视频、trace、医院展示；人工目视仍NOT_RUN，最终演练仍0。

全部旧candidate source/dist/runtime引用核对通过，候选仍 `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917`。新驱动及辅助文件不在旧冻结清单内，不改变旧候选身份；下一次技术请求额外绑定这些文件和浏览器runtime。下一申请见原合并待决表的本轮增量，不重复原三项已消费批准。

## 2026-10-14｜revision87批准后的64-only技术核验V2｜FAILED_OR_PARTIAL

直接负责人消息01a138fa-a7da-7b60-b9d5-799e1983bda5批准原待决表1—3各一次，owner SHA `daa12ff3b21284178b6860fdb1063e898fca2cee78b58f749a9a67de99eb5d40`。总控确认ENC串行任务/资源退出后明确发出C启动指令；按原请求 `7398099e6ceffb2067e5e5566668c0957023e872d02c3615b6da5a651aa001cf`、候选 `191b47b46ac2710e1a1d2d08b6b7b5e67c5c137c22d0d9cb105fb7f76911d917`，原驱动源码246cdd1884a59bf9c0dcb1f872a26802378488de执行一次。精确confirmation SHA `738213092b93603e0bb9c11b9e768bf70401a7c932b2b969ee5b3559d5e0e651`，原V1等待索引保留；未重跑check-only/生成测试。

输出 `.local/demo64-technical-20261013-02`，验收耗时19.766909959秒，父调用20.114539208秒，均在整体180秒内。**FAILED_OR_PARTIAL**：服务/登录PASS，首例Result HTTP200、单64摘要、九资产中本例三资产ID集合、仅64选择按钮、DICOM HTTP200及输入SHA核对均有逐步PASS。等待当前影像readiness超时，renderSequence=0、overlaySequence=0；current_render/decoded/rendered_status/canvas_visible=false、location/no_error=true。asset=true在此因尚未要求assetUrl而非证明64资产已绘制。不将该观测写成已证实解码错误、应用正常或空间失配；实际根因UNKNOWN。`flows=[]`，三Result/九层、刷新、真实API直接拒绝、固定点0.5 CSS px实际空间核验均未完成/NOT_RUN。

原始acceptance SHA `19d1afe5e3aa7e70b211bf5cc61cc2b6f49fd0778d855f729d881d9612bb4d4d`；exit SHA `1ec9507d6ef2d9d05a56b9737dc93092621a47a83dc7c33dfd4afdc136b990c3`。primary_failure.message保留CURRENT_IMAGE_READINESS_TIMEOUT；原step记browser_closed，因browse finally先记录清理再传播异常，实际失败位置由assert_09后wait_ready及原源码确认，不改原receipt。cleanup_errors=[]、browser_closed=true，三个自有服务exit -15、自有恢复父/driver exit0；**driver exit0不等于技术PASS**。原DB不变、model_calls0、worker_started=false、external_requests0、page_errors0、截图/视频/trace/像素导出0；已知driver/服务/恢复父PID均未再列出，不信号任何未知进程。

实际索引 `approved-abc-execution-20261014/INT_EXECUTION_INDEX_V2.json` 位于原私有总控交付目录，记录owner/confirmation/精确argv/原始收据/日志及退出SHA；当次结果索引SHA `02bc8e23ddf046f2f0c54bd78a786e11bf0f57aa9f112ecb01b6c8134e8a7efd`。无新Job/slot/模型，原v16/DB/对象/dist保全、旧FAILED_OR_PARTIAL/hidden根因UNKNOWN不变。本次许可已消费，停止且不自动重试。人工NOT_RUN、最终演练计数0、医院用途/录屏未批准、最终冻结NOT_RUN；不抵扣最后三次演练。仅文档增量，不改总控state/合并表，不push。


## 2026-10-14｜revision89精确批准后的64-only技术核验V3｜PASS_TECHNICAL_ONLY

本节补充R88工程准备的真实运行结果，保留此前两次FAILED_OR_PARTIAL及其根因UNKNOWN。INTEGRATION原工作树 `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration`、分支 `codex/epi-next-integration-20261009`，执行前HEAD `eeda34d76a5f302830beaa1fcb332e5c78a3a850`；绑定代码提交 `0e44ac5adfc4dcc58e1eeb829b39d35e25d17de7`。负责人直接消息 `01a13971-3b26-7d10-9617-9f5343584f34` 已独立核验，精确批准请求 `2d3d5da57a818b2b202b5fe93db632fe8fbfd1e79cb7f2487f478565575b5934` 各执行一次、串行、失败停止、不自动重试，不含医院展示或录屏；R18已完成结果仅复用。总控明确C启动后，核对revision89及writer账本COMMITTED一致/pending0，state SHA `cd7a9127bca91d2ff9c8c813330a86885cc04b0dd81cc57f1956c9376df7c85a`，没有写入state或两份合并表。

owner approval SHA `c965d0e15b925e86e282bf8abc681f73f4f0bd845c772ca5c5db99c864054f55`，原始owner message SHA `cf29dc9a6852f9b8aafc6465ed6cf3ae57ae63d1997cdfa609869f2ed38bfbc9`，执行confirmation SHA `cd6bc230a73e03068a2dd73744b734e6cba7dd8fe35f371ae555209e870e067b`。新候选 `a7d3cc77d17d4bf44fd45b80ea44b35472faa3a1e2c31f8b93a18eeb6b818da0` 的197源码/旧恢复、21dist、23runtime及driver/browser/core绑定全数匹配；旧唯一DATA ledger/policy复用，无第二allowlist。新输出目录执行前不存在，V3精确argv已记录，只调用一次，未重复check-only/生成测试、未改代码或容差。

实际本机浏览器、Backend/Gateway/HTTPS只读流程 **PASS_TECHNICAL_ONLY**：服务、登录、三个既有历史Result、仅64、三个结果刷新恢复、直接API范围拒绝、独立空间检查全部PASS。3个单SOP与原DICOM SHA核对，9个64图层均通过当前decoded/rendered/可见canvas/当前asset readiness；独立原生DICOM IPP/IOP/spacing加相机投影核对每层固定7点，共63点，最大误差 `4.263256414560601e-14` CSS px，原容差0.5 CSS px不变。这里只证明单切片FrozenBaseline/64展示链，未覆盖完整Series、切片顺序、3D、任意crop/resample或新算法；没有重算模型，也不建立科研提升或临床有效性。259条步骤事件包含STARTED/PASS和辅助元数据，不误称259项独立测试；66条静态请求记录均HTTP200，page_errors为空。

原始收据 `.local/demo64-technical-r88-20261014-03/acceptance.json` SHA `02377afccc9cd0a71f7b53cf93d0895baa85d2ac03c96eed0a6d0dc1f5504b7e`；实际验收8.254969917秒、父调用8.574972583秒，分别低于140/180秒预算。退出收据 `services/restore-exit.json` SHA `bd9913e047b5e0cbb33a6a8c6d500e5a7f693f3af7aef822763156b314d89feb`：browser_closed=true，cleanup_errors=[]，自有服务35622/35623/35624均exit -15，恢复父35618和driver35614均exit0，五个已知PID退出后均未列出。源DB不变，Worker未启动，model_calls/new Jobs/外部请求/截图/视频/trace/像素导出均0；只清理本次自有进程。

完整私有索引 `/Users/skyfrost/Documents/Techniques/EpiLocate-private/manifests/epi-next-phase2-coordinator/r76-48h-20261013/approved-r89-cache-demo64-20261014/INT_EXECUTION_INDEX_V1.json` SHA `820bb019bd785f4e882d01d35bb5961c5da38f4e2d2d7af0bdd712f30f8aab94`，记录许可、源码/运行时、精确argv、日志SHA、原始验收/退出及对账结果。stdout SHA `3c1fb99e39566844c2bf76477eb90cb5ba1b8736e0f2644520a68052f7e600ce`，stderr为空/SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。受保护收据及配置保留本地，不提交患者影像、患者空间细节或凭据。

本次一次许可已消费，不自动重试。旧v16/DB/对象/dist、A/B/C、GT-v1及旧两次失败收据保持；旧版回退范围不扩大。**人工目视NOT_RUN；最终三次演练计数0；医院用途NOT_APPROVED；录屏/播放NOT_RUN且未批准；医院最终冻结NOT_RUN。** 三个历史Result流程不是最后三次演练。仅增量更新本清单及两份工程文档并本地提交，无push/部署/state writer/待决表修改；最终是否PASS/CONDITIONAL PASS/NO-GO由钟佳桦批准，总控统一汇总。
