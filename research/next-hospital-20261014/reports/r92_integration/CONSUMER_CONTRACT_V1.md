# R92 R18研究产物消费者契约 V1

本工具是既有research工具的独立小模块，不修改生产API、旧MVP或SLICE协议。入口 `python -m epilocate_next.r18_research_review`。真实页面仅静态数值元数据，未自动打开；生成UI验证不等于真实医学显示/空间验收。

## 已接收的实际生产格式

直接消费ENC `R92_R18_SLICE_CONTRIBUTIONS_V1`，不是要求ENC重导出另一份结构。

- 贡献JSON：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-encoder/.local/r92-encoder/R18_SLICE_CONTRIBUTIONS_V1.json`，SHA `94cb4bc0c769fda0c93a89602dc4f451eeabef5ae87729d76379dda149ea40d9`。
- 成功cache JSON：`/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-encoder/.local/resnet18-mil-v1/r88-rounding-cache-proposed-1/cache/cache-receipt.json`，SHA `fe19d5f8ad9fc99923abbfbd2edb0077874c4422b44531c08131e4d413457454`。
- 数值策略：ENC `NUMERICAL_POLICY_V1.json` SHA `c72df9804d0efc340c30d17e495ec0e1df918689c9c9271439dcfbd7c6e8e30c`，saved FP64 logits预锁 `atol=1e-8,rtol=1e-10`，不接受调用方任意放大容差。

原JSON不改写。适配器 `from_encoder_contributions()`仅操作这两份JSON内已有值，不打开它们指向的NPZ、head、geometry、CT、PNG或模型文件。正式消费命令读取2个外部JSON（贡献1+额外cache1）；字段核查也读取了同一贡献JSON，不是新增医学资产。后续最终发布因受影响代码收口再次读取同两份JSON，详见私有audit，不把2个不同文件数误称整个会话仅两次file-open。

严格按record_id与source_group_id join，分别拒绝重复；核对context、feature/geometry引用、geometry SHA、split、source diagnosis与原来源标签。`identity.input_sha`绑定**整个预处理K8模型输入**，联合原八个有序、非负、互异native_Z。它不是原始CT hash或逐片hash；`slice_input_sha256=null`，不复制bag hash伪造8份逐片hash。

## 数学与页面语义

ENC实际字段与消费者映射：

| ENC字段 | 消费者/显示 | 检查 |
| --- | --- | --- |
| saved_raw_logits / saved_positive_probability / saved_predicted_class | BAG保存预测；固定0.5，tie=Normal/类别0 | 预测须logit1严格大于logit0；概率与原logits一致 |
| raw_class_terms | 8×2 bias-free dot(a_c,f_i) | finite、恰好8片；不是单片病灶预测 |
| weighted_class_terms / weighted_margin_terms | BAG加数=raw/8 | 求和后另加effective bias/margin bias |
| slice_component_logits / slice_component_margin | 片组件=raw+beta | 8片均值=BAG logits/margin，不能与weighted量混用 |
| effective_bias / effective_margin_bias | 独立保留有效bias | 两类均重建保存FP64 logits，按原锁定容差逐元素检查 |
| correct / source_label / source_diagnosis | 来源弱标签错分筛选；保留全部组 | 不把bag来源标签当切片GT，专家标签UNKNOWN |
| geometry.indices_Z / feature_reference / head_reference / model_version | 来源组、输入、geometry、frozen head、backbone、config/版本追溯 | 原8片不替换；head限定R91 `5c003668…90c8`，旧case3 E2链不能混入 |

本地规范化schema `EPI_NEXT_R18_RESEARCH_REVIEW_V1` 是UI内部视图，见模块中的严格Pydantic定义及 `qa/r18_research_fixture.py` 可运行生成fixture。prediction_scope=BAG、mode=PRECOMPUTED，fixed target默认显式class1−class0 margin，不反向跟随预测翻转。数据为generated或real precomputed，不能混装；patient independence与pretraining overlap继续UNKNOWN。

页面分别切换“raw/8 BAG加数”和“含bias片组件”。signed原值保持；正半轴只是当前margin列的max(signed,0)显示，不能用于logit重建，正component不是感染片预测。1/8与全logits平方损失1/64关系明确显示，不修改旧HSPI/CPF阈值。不会计算新分类评价或替换R91成绩。

现缓存是FP32 `[8,512,1,1,1]` GAP占位，空间CAM为NOT_RUN / NOT AVAILABLE，不reshape成图。未来规范化空间元数据若AVAILABLE，必须声明ACTUAL_PRE_GAP_HOOK、8×512×H×W且H/W>1、hook及8个signed map引用；正半轴产物要独立SHA并绑定signed来源。这里只验证声明结构，不读/画任何医学图；现ENC v1适配器不自动接纳未来CAM新schema。

## 正常分支、预算与缺口

| 分支 | 行为与停止条件 | 本线预算/缺口 |
| --- | --- | --- |
| 生成fixture | 严格校验、生成静态页面、无服务headless交互回归 | 0F/0B/0更新，全部合成；可截图仅生成页 |
| ENC v1 +已交付cache JSON | 严格hash与join、FP64元数据算术、静态派生artifact/页面；真实页不自动打开 | 每次2个JSON、每文件≤4MiB；不读数组/权重/CT，无新许可缺口 |
| ENC v1未提供cache | 显示已有贡献，但input binding明确NOT_EXPORTED | 不伪造输入或逐片SHA；正式当前60组已通过cache分支补齐 |
| 仅保存预测、贡献缺失 | NOT_RUN/BLOCKED/FAILED显式显示，无贡献表/伪值 | 规范化接口支持；不触发模型或后台补算 |
| SHA/身份/单位/重复/finite/重建失败 | 拒绝，不输出可信图，不改变原数据，不放大容差 | CLI exit2；已有输出O_EXCL保护，部分新文件先对账不覆盖 |
| 未来真实CAM | 先等ENC新版本/正式hook与target/geometry绑定；仅元数据校验 | 新空间forward预算和许可由ENC/主控合并申请；本线不造调用数/申请 |

默认CLI只校验。`--profile enc-r92-v1 --cache-metadata <已交付JSON> --cache-sha <完整SHA>`消费上述实际profile；`--normalized`保存独立新JSON，`--html`生成静态HTML。真实数值页另需显式`--real-metadata-page`，这是防误显示开关，不能替代许可。本轮已明确获准生成该静态元数据页，未调用任何打开页面的工具。所有真实派生物留INT `.local/r92-research-review-20261015-01`、0600；源码和生成fixture可进Git，真实逐组数值和页面不进Git。

本线没有新增真实科学计算请求，0 backbone/head forward、0 backward/update、0队列/Job/真实服务。只读JSON和数值算术是实际计算，不能简称“完全没计算”。标签/新留出/CT-FM/两个机制输入及空间forward统一由主控一份分项申请处理，R91已消费额度不复用。

## 已知边界

60组/120保存logits的本地元数据重建复核通过（consumer max abs `7.105427357601002e-15`），3个来源标签错分均COVID；不是新独立测试。源数据全局6 NONCONFORMANT/54 NOT_EVALUATED保持，但当前贡献JSON没有逐组身份映射，视图标NOT_EXPORTED，不重评/不将它们改成合规。

preprocessing当前绑定config摘要/版本，无单独preprocess artifact；standardization引用head receipt的state mean/scale，并未读这些数组。嵌入引用除了两份明确交付JSON均未验证内容；geometry引用不等于医学空间对应PASS。无真实CAM、医生切片/像素GT匹配、真实页面浏览/医院目视或医院冻结。64-only技术PASS、人工另约继续继承；旧66和候选197源码引用MATCH。

最终source commit、代码/契约SHA、真实与生成证据及私有产物路径在同目录RESULT_INDEX_V1.json登记，由主控读取汇总，不另建门户/部署/审批系统，不push。
