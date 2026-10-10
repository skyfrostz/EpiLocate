# E2模式结果sidecar接缝 v3

INTEGRATION仅负责消费/保全，不改LOC算法、阈值或GT，不改医院旧protocol和监督v2。供总控转LOC同步；本文件写入不等对方已收到或已执行。

新接口 `epi_next.e2_result_handoff.save_handoff(root, run_id, envelope, assets)`，assets为LOC已经产生的run-local bytes；不运行模型或生成候选。manifest字段：

- schema `EPI-NEXT-E2-RESULT-HANDOFF-3`，method_mode严格为E2-W1/E2-REF/E2-CT，algorithm_version独立明确。
- run_profile包含profile_id、profile_kind（HISTORICAL_COMPONENT/COMPONENT/FULL_CORE_CONFIG/CT_ADAPTATION）、config_sha256；不由mode推断完整配置执行或作者结果复现。
- source_result `{path,sha256}`保留原结果只读身份；model/input/preprocessing SHA分别显式绑定。
- execution_status为既有SUCCESS/NO_RELIABLE_RESPONSE/PARTIAL_BUDGET/FAILED/BLOCKED/NOT RUN；algorithm_status保留原字符串。
- planned_branches列全计划 `{scale_index,grid_yx,stage,max_iterations}`；branches逐一同身份，不隐去未运行分支。scale_index零基、stage一基、selected_iteration及completed_iterations统一一基计数，LOC的epoch若零基需明确转换并保留raw结果。
- branch status严格为COMPLETE/NO_FEASIBLE_MASK/OPTIMIZATION_PARTIAL/NOT RUN/FAILED/BLOCKED；字段completed_iterations、selected_iteration（无选择为null）、selection_scope（FULL_PLANNED_BUDGET/BEST_SO_FAR/NONE）、reason及trace_asset（未跑为null）。COMPLETE需要全部计划迭代、选中轮及trace；NO_FEASIBLE_MASK需要全计划运行、null选择；PARTIAL允许best-so-far但不得称全计划最优。
- trace_asset `{path,sha256}`指run-local单文件（JSON/JSONL/NPZ等已有字节），记录每scale/stage的轨迹，不解析或重算轨迹。source_result完整logits/候选等原始字段保留，不把本sidecar当候选空间QA或hospital output。
- psmi_status为FINALIZED/NOT_APPLICABLE/NOT_FINALIZED_INCOMPLETE_OPTIMIZATION/NOT RUN；acceptance_axes逐项显式METHOD_SPEC/IMPLEMENTATION/SYNTHETIC_CHAIN/REAL_CT_COMPONENT/REAL_CT_FULL_CHAIN/LOCALIZATION_BENEFIT，可为NOT RUN或有scope/reference的状态字典。

保存前校验原result SHA、分支计划覆盖、状态一致与trace字节SHA；调用既有persist_run不可覆盖事务收据。历史结果只在新目录另建sidecar，未知事务先reconcile，不能盲目重写。mode不同不自动映射旧E2 runtime注册表、不启用新医院handler。LOC收到本契约后可在自己的owner路径产生manifest/trace；本线不动态导入仍编辑的LOC源，也不替它实现算法adapter。

任何CPF未满足不等“证明无解”；E2-REF不是作者源码复现，partial或NOT RUN不等全机制PASS。10月14日MVP快照不要求E2阳性或新增真实E2E。
