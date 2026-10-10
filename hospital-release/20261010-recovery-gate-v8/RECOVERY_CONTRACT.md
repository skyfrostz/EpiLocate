# 独立行政恢复决议消费契约 v1

当前生产状态仍 UNKNOWN；本交付不包含实际决议、不解除生产队列。R0一次只读审查已由总控完成，不能重复采样。R0通过仅是必要条件，不是设备恢复证明。旧slot、BLOCKED/FAILED收据、计数及缺失finished.json均保全。

## 固定调用接缝

`epi_next.execution_lock.validate_administrative_recovery(queue_root, task_key, decision_path=None, decision_sha=None)`只读验证，返回原job标识和决议绑定；无绑定返回None。

`run_supervised(..., recovery_decision_path=ABSOLUTE_PATH, recovery_decision_sha=SHA256)`在原wave1.serial.lock内验证；将同一绑定传入原tracked_device_slot，再在device_lease内复验。原八模块闭包不增加模块。LOC及C1必须消费同一个固定源码包，不混用本次execution_lock与旧v2监督器。旧只读v1/v2 bundle保留；本次不就地修改它们。

直接调用tracked_device_slot也接受同名参数，并阻断所有未决槽及已用task_key。只有决议明确绑定的一个旧UNKNOWN槽可被绕过。新job_id仍须全局独占、新task_key不得重复。历史计数不重置，旧任务不可重跑；任何未来续做配额必须由总控单独审批、绑定已有账本。此接缝不授予数据、模型或计算权限。

## JSON字段

引用统一为`{"path":"绝对路径","digest":"文件原始字节SHA256"}`，拒绝路径任何层级的软链接。

决议schema `EPI-NEXT-ADMINISTRATIVE-RECOVERY-1`，status `APPROVED_ADMINISTRATIVE_RECOVERY`，queue_root为实际共享队列绝对路径，historical_status_unchanged=true，model_authorization_granted=false，approval_reference为独立批准引用。

scope必须包含old_job_id、old_task_key、started_sha256、supervisor_reference、r0_reference、allowed_next_task_keys。scope字节绑定使用`sha256(canonical_json(scope))`；canonical_json是本项目函数，不用其他JSON序列化代替。

批准schema `EPI-NEXT-OWNER-RECOVERY-APPROVAL-1`，status `EXPLICIT_ADMINISTRATIVE_RECOVERY_APPROVED`，principal `钟佳桦`，scope_sha256绑定上述scope。总控仅在负责人明确答复后发布批准资产和决议，并通过可信沟通发布决议路径与SHA。早先APPROVED_ONCE_READONLY或条件计算批准不能代替它。

R0必须绑定原result.json并核验其所有raw_sha256文件；五项checks全部true、61样本、无GPU探针/信号/模型调用且原槽未改变、finished仍缺失。原started及supervisor原始SHA必须仍一致、原receipt仍FAILED/BLOCKED且slot_completed=false。

SHA提供字节完整性，不提供同UID写入者身份认证；负责人答复真实性由总控负责。决议的持续有效性也由总控负责，不能把该机制解释成独立设备健康探针。门禁读不到文件、解析错误或哈希变化均失败关闭，不自动重试。

## 回退和验收边界

省略决议两个参数恢复严格旧门禁；旧UNKNOWN继续阻断。不要创建旧finished.json，也不要清理槽来解除阻断。医院最终冻结、真实CT三次演示、预计算及备用录屏仍须正式交付与验收，本生成测试不替代它们。
