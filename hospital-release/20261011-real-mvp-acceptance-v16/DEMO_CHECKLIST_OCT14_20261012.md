# 10月14日基础演示清单｜2026-10-12管理补充

INTEGRATION唯一维护；首席算法工程师汇总，钟佳桦批准。**HU v5、新分类头、E2正收益退出基础关键路径。** 本地真实MVP PASS（3/3），医院展示NOT_APPROVED、最终冻结NOT RUN。本轮仅复用元数据并开发计算关闭的本地恢复，不执行新推理、真实像素展示、截图或录屏。

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
3. **计算关闭的本机只读恢复入口已实现，4项生成测试PASS；真实启动/画面检查NOT RUN。** 目标：新私有运行目录和SQLite副本、新认证，仅127.0.0.1；禁止新增任务/上传/全部Worker接口，读取原已保存结果；没有新模型/Worker启动。精确命令见下节，新恢复与原54ff三真实流程验收分别记录，不把生成测试升级为真实恢复已验收。
4. 仅在获准本机启动后：登录→原三个Result→原生CT/对应16/32/64响应→刷新恢复；本轮不实际显示真实像素，不重新上传或创建Job。
5. 回退：停止自己拥有的恢复进程，原SQLite/对象/旧dist保持；关闭实验flag，不做破坏性downgrade/reset/clean或杀未知进程。继续获准本机查阅旧保存结果；无法安全恢复则交负责人决定暂停显示，不用新推理救场。

## 已有证据与缺口

| 项目 | 已有证据 | 剩余边界 |
|---|---|---|
| 原生叠加 | 三单SOP；64选中像素校验通过，16/32/64选择通过 | 三尺度逐像素人工验收、完整Series方向/顺序/world/crop/resize/resample未齐；映射无法验证不进入医院候选 |
| 保存刷新 | 三Job/Result/Attempt/对象SHA一致、刷新保持64 | 新恢复方式生成验收单独记录；真实恢复启动/画面检查本轮NOT RUN |
| 错误提示 | 原Job失败解释/查询与图层恢复及生成FAILED回归；新六状态生成证据 | 这三真实流程未触发真实失败；不把生成故障写成医学失败验收 |
| 备用材料 | 原开发预计算/截图和SHA保全 | 本地同存储快照非独立备份；医院用途批准、合格录屏/播放检查未完成，本轮不制作 |
| 现场审批 | 本地MVP已接收 | 医院指定受众/设备/用途、冻结配置三演示及14日PASS/CONDITIONAL PASS/NO-GO仍由负责人决定 |

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

拟申请10月15日在负责人明确的医院/场地/受众/受控设备上，只读展示这三单SOP及严格绑定的FrozenBaseline/Occlusion现有Result，说明模型行为局限、不用于诊断、不新增推理/训练/病例访问。医院名称、受众、设备、显示渠道、是否允许离线副本/截图/录屏分别待负责人绑定；默认无云上传/公网/文件发送/截图/录屏许可。该章节只是精确用途候选，供总控合并唯一申请，没有签署批准、自动展示或新数据allowlist。

## 已实现的只读恢复命令与增量验收

[固定命令索引](READONLY_RESTORE_COMMAND_INDEX_20261012.json)绑定本恢复源码和旧dist，不含账号/密钥/数据库正文。元数据校验不会读真实DB或像素：

```sh
cd /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:frontend/.local/mvp-20261011-browser-deps \
 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python qa/local_mvp_readonly.py \
 --binding /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/read-only-mvp-binding-v1.json \
 --binding-sha b03d88d251eb658d285d66462f550f4d2c392798c930c13bf7dd4e0ce1c0d1e4
```

获准本机操作员要读取原已保存结果时，在上述命令后加以下参数（本轮未执行真实启动）：

```sh
--serve \
--run-directory /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/.local/mvp-readonly-20261014-01 \
--dist /Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-integration/frontend/.local/mvp-20261011-dist
```

新目录必须不存在；不重复使用旧MVP命令/任务/输出。脚本保全原SQLite和对象，复制DB到新私有目录后，只在副本撤销旧认证并签发8小时新认证、关闭Worker；必要时续同三源影像的副本读取期限，不新增影像或模型准入。真实恢复读DB副本操作和手动画面检查未在本轮执行。

等待restore-ready.json后，终端只给本机HTTPS URL及private-config.json路径，不输出密码。操作员在本机私有文件读取新账号/密码，登录现有/mvp/页面，查看原三Result。页面只读提示明确；所有新任务/上传/变更及Worker接口403，直接对象旁路也拒绝；原结果source仍保留其历史LIVE_CASE，不改成新模型运行。自签localhost证书不安装到系统、不对外开放；不启动任何Worker或旧推理命令。

停止按一次Ctrl-C，等restore-exit.json确认三自有服务退出、source_db_unchanged=true、Worker未启动/model_calls0。回退只停止这组已知自有服务、继续保留原v16；再启动使用新的运行目录以重建会话，不清空或覆盖原记录。不终止未知进程。

增量结果：4项定向生成测试PASS2.09s，新认证/过期输入副本读取/结果和资产SHA/刷新一致/拒绝写与Worker/无覆盖及错scope/实际loopback HTTPS登录静态提示和停止回收。只有生成病例/PNG；没有DICOM解码、模型、浏览器/截图、真实DB复制或真实像素访问。旧54ff 3/3真实验收不重跑；恢复模式真实视图验收仍NOT RUN。这一非医学接入完成不依赖HU v5、训练头或E2收益。
