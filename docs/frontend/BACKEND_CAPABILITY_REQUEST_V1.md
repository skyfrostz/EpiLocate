# BACKEND_CAPABILITY_REQUEST_V1

状态：PROPOSED / 未实施。负责人评审后由 Backend 独立实施。本次前端不请求这些路径。

1. 授权范围病例搜索、排序、统计：返回 scope、observed_at、时间窗、total/完整性、分页游标。需要明确 Case→最新 Job/Result 的 slice/model/protocol 分组与关联证据。
2. 授权任务集合：分页 GET、状态过滤、稳定排序、观察时间；不得暴露他人 Job。重新提交与重读语义分开。
3. session capabilities：服务端授权；建议 system:read 等能力。用户名不代表角色，前端隐藏不替代权限。
4. 运行状态：分别提供 Backend、在线 GPU、Worker heartbeat、Queue、Storage 的 state/source/observed_at/ttl。不得暴露主机、凭证、研究训练信息。
5. 脱敏活动 feed：范围与保留时间明确。当前前端仅显示本会话访问记录。

候选路径参考设计包 /api/v2/ui/dashboard、/api/v2/ui/operational-status、/api/v2/jobs；仅为提议，最终名称/响应/授权由 Backend 评审。没有修改 Worker protocol 或当前 API contract。
