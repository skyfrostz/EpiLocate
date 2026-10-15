# R103 INT｜真实元数据消费与版本化研究接缝

日期2026-10-15，原INT工作树/分支 `codex/epi-next-integration-20261009`，开发前HEAD `20a37701f44375af87b0767dd2593f9895ca7f1e`。R103负责人原文SHA `2bfd447ec957f980605e30b1e7f95d820e9d138435bf2e0f71c36942d702c137`已完整读取。只执行元数据工程，不自动重跑已消费R102，不写权威状态/队列/批准，不改变三线源码和旧MVP。

## 实际可接与缺口

| 交付 | 旧接口实际边界 | 新接口实际核对结果 | 不提供的结论 |
| --- | --- | --- | --- |
| A `ARCHIVE_BOUND_AB_RESULT_V2` | 不是预测或医生参考registry，不能塞入E2/F0结果 | 正式JSON SHA匹配；79行、shape[79,200]消费为结构；配对组数/有效片数null、mapping UNKNOWN | 不是79名已配对患者各200张有效片；未读Index/NPY正文 |
| B `R92_TRUE_SPATIAL_RECEIPT_V1` | 旧R92 GAP-only adapter实际拒绝新schema；不能放宽其FP64重构契约来接真CAM | 20组/160位置病例logits、固定native索引、head/geometry及signed-class/signed-margin/positive引用消费；signed margin为class1-class0，positive=max(signed margin,0)仅显示 | 数组/空间几何引用未读取或重验；不是医学定位PASS |
| C `R92_SAME_BAG_COMPARISON_V1` | 旧E2 target契约要求SLICE，不能无声明地表示K8条件BAG | 1组/8位置、Normal_SOURCE原argmax固定目标、18个固定面积keep/remove及1个final-soft响应消费；raw BAG平方损失与consumer派生64倍组件单位分开；候选未校准、空候选不表示无病灶 | JSON不导出精确head引用，保持NOT_EXPORTED；不导入CAM/mask到新输出，不继承旧CPF/PSMI或病灶标签 |
| D `R92_FOURGRID_RESULT_V1` | 属旧case3分类器，不能混入R18 | 四格响应独立OLD_CASE3_NOT_R18/OLD_SINGLE_SLICE；目标ID保留，未导出的类别文字/策略/head不补造 | 不将旧交互机制迁移成R18定位改善 |
| ENC R103 fixed8控制 + 既有R92 scalar JSON | B收据没有逐片scalar，不能通过打开CAM数组偷偷补全 | 固定控制SHA `02e1a3a0e45f95d225ed59735d2c5900ec80b15c69a3aa6b9228b086855e2f02`，scalar源SHA `94cb4bc0c769fda0c93a89602dc4f451eeabef5ae87729d76379dda149ea40d9`；旧adapter验证60组已有signed dot-products，20开发组/160位置按group、head、geometry、fixed8、saved logits连接MATCH | 原生像素身份未独立重验；未导出逐片输入SHA；未做新医学配对、切片AUROC/AP、区域GT评价 |

真实消费证据在单一 `RESULT_INDEX_V1.json`。各医学参考仍UNKNOWN；已保存JSON的病例标签/漏判控制不是医生切片参考。160相关位置不当160名独立患者。原R18/CT-FM/Ridge/旧case3保持冻结，无训练/阈值/采样改变。

## 最小改动与语义

- 新 `epilocate_next/r103_research_metadata.py`：独立版本 `EPI_NEXT_RESEARCH_METADATA_V1`，复用R92的Strict/Reference/有界JSON读取与既有signed重构，不改旧GAP-only validator或SLICE E2/F0协议。明确结构标签、空间声明、条件BAG、旧模型四种类型；未知schema拒绝，不自行推断。
- 新 `r103_research_review.py`：仅生成数据数值页面，病例logits、目标、逐片signed BAG加数raw/8、空间声明、参考UNKNOWN和响应损失分别显示；脚本/图像/外部连接禁用，路径仅转义文本。新profile拒绝真实页面生成，旧 `--real-metadata-page` 也不能绕过。
- 原 `r18_research_review` CLI增量profile `r102-metadata-v1` / `metadata-v1`；可用两个显式JSON/SHA参数对接scalar和fixed8控制。不会递归打开任何引用或后台启动服务/浏览器；输出exclusive，未知已有输出先对账。
- signed raw/8八片求和后另加有效bias；raw+bias的单片组件均值为BAG分数。positive派生不重建logits。64倍损失为单位换算而非E2提升；单片条件解释保留其他7片，不等于区域解释整例CT。

CLI复现模板（SPEC，实际元数据消费使用同一公开函数；生成CLI路径已测试）：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epilocate_next.r18_research_review \
 --profile r102-metadata-v1 --artifact <总控固定B-JSON路径> --sha a6cd0c3f08ca9ab160a073bf0b08bb33b7d04d39fd8409e096cba8e93434ab56 \
 --slice-contributions-json <总控固定R92贡献JSON路径> --slice-contributions-sha 94cb4bc0c769fda0c93a89602dc4f451eeabef5ae87729d76379dda149ea40d9 \
 --fixed8-control-json <总控固定ENC控制JSON路径> --fixed8-control-sha 02e1a3a0e45f95d225ed59735d2c5900ec80b15c69a3aa6b9228b086855e2f02 \
 --normalized <未占用的获准本地输出JSON路径>
```

不要加真实HTML/浏览器；这不是新的医学数组/计算命令。实际路径与哈希均在索引引用中，模板不暗指新执行许可。

## 实际验证与访问账本

- macOS，项目 `.venv/bin/python`：`qa/test_r103_research_metadata.py` + 原 `qa/test_r18_research_artifact.py`，45 passed in0.07s（新增25+原20）。覆盖错误target、正半轴来源/别名、GAP伪空间、旧谱系、缺固定面积响应、单位混用、假医生参考/候选、错head/geometry/indices/logits/dev集合、无资产I/O的scalar连接、生成CLI连接、真实render标志不能绕过。
- 最终两个生成页面各5项检查；目标/参考、无病灶误推断、signed八片贡献或BAG/组件单位、无医学资源/脚本、来源/手机宽度。外部请求0、pageerror0、浏览器已关闭、服务0。截图仅生成数据，非真实医学验收。
- 实际科学元数据输入6个distinct JSON：A/B/C/D + ENC固定控制 + 既有R92 scalar。另有总控索引/交付索引和指令等控制文件；字段发现/核对曾重复读取部分JSON，不谎称每文件只读一次。scalar连接2个新增JSON读取；最终5份本地标准化输出按最终schema复验通过。
- **C源JSON本身内嵌真实CAM/mask数组，已经随JSON解析，首轮字段检查读出过部分内嵌值。** 不将本轮表述为“完全未触及数组值”；新adapter用标量白名单投影，不访问/复制这些字段，不进行map算术/显示。没有读取外部NPY/NPZ/权重/CT/GT payload；正式消费无NumPy/Torch导入，模型调用0、真实医学页面0。原科学70F/9B/8mask更新属于R102历史，不算本轮执行。
- 源码闭包以索引逐文件SHA绑定；旧R92 artifact及旧HTML未修改，只有独立CLI增量。未重新hash患者资产/197运行资产或重跑MVP；保全依据为限定Git改动及原技术PASS继承，不伪称新全链路回归。

## 后续schema的明确入口条件

未收到DATA正式医学配对或LOC/ENC新版医学评价schema前不接受PAIRED值、不生成指标。收到总控固定版本后，以新adapter一致性核对：source_group/record身份、参考版本及SHA、PAIRED/PARTIALLY_PAIRED/UNKNOWN/CONFLICT、有效原生Z及fixed8对应、可评价分母与排除原因、固定target/policy/class对照、BAG/切片/区域单位、同组同片几何来源。不因来源类别/预测/GT命中择映射或重新选片。切片0/1不能作pixel mask，原POLYGON计数不是独立三维病灶数。

本交付状态：真实JSON元数据可消费与接缝工程DONE；新医学配对/评价及产品验收NOT_RUN；原MVP PASS_TECHNICAL_ONLY、人工DEFERRED_BY_OWNER_NOT_RUN、医院冻结NOT_RUN保留。INT不自行推进状态或发批准；向首席汇总实际接口证据与缺口。
