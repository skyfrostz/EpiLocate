# 固定v3恢复链与R1消费适配

唯一修改是原v3恢复消费：接受语义相同的R1审查，逐一核验两个历史UNKNOWN槽。新决议scope中的`predecessor_recovery_reference`和`predecessor_validation_task_key`明确指向旧决议及其当时允许进入的C1任务；按该历史任务验证前序，不拿新P1/MVP键扩大旧scope。

每节点仍要求独立钟佳桦owner批准、原started/监督receipt、61样本条件及全部原始SHA。新槽started中的administrative_recovery原四字段必须与前序验证结果一致。最多两个decision节点；循环、深链、重复job、SHA漂移、缺证据、未列第三槽、已消费任务拒绝。返回原`old_job_id`及新增`old_job_ids`、`validated_recovery_chain`，两个原门禁使用同一已验证集合。旧snapshot/slot/收据/缺失finished全部保留。

20项生成隔离检查PASS（0.33s）；实际决议`ceb164…`只读验证P1/MVP两键PASS。没有实际队列写入、进程信号、R1采样、GPUprobe或模型。这里不代替科学授权或总控dispatch。

LOC接入：改为manifest中固定的唯一新package/index/dependency，不混用旧v3或共同IO锁v4；消费新decision，保留原单节点字段兼容，允许前序引用。P1计时/输出最终绑定由LOC负责，MVP真实接缝由INTEGRATION负责。医院展示未批准，真实MVP NOT RUN。

源差分见`source-delta.diff`。固定源码、bundle完整绝对路径和SHA在提交后补入同一manifest；旧八模块v3不覆盖。
