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

## 管理网络修订与本轮停止点

正常网络不是阻断，也不要求完全离线或localhost为唯一可能部署。当前按已实际PASS的本机只读恢复交付，不因政策放宽切换部署/增加计算；全部独立GPU AI Node均不进入展示架构。三图原LOCAL_MVP_ONLY素材边界不变，医院展示用途未自动获批；未获批则采用无受限像素的技术示意。R71原独立执行已退出，本轮不新增测试/恢复/截图/录屏，停止新增工作，等负责人用途决定。
