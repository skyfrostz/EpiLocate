# FRONTEND_CAPABILITY_MATRIX_V1

2026-10-03；负责人：钟佳桦。开发基线 `2be89143a8abccb3c3896a8f53633e490cf79b28`，分支 `feature/clinical-canvas-v1`。

| 分类 | 能力 | 当前实现和显示规则 |
|---|---|---|
| A 当前 API 支持 | 当前账号病例分页、创建、单切片上传/读取 | `api/client.ts`, `api/types.ts`；保留游标，无 total |
| A | 受保护 Job / Result / assets / positions | 按已知 ID 读取；不新增集合端点 |
| A | Cookie session / CSRF / safe next | `auth/session.ts`, `auth/lifecycle.ts`；会话代际和取消保留 |
| B 现有数据推导 | 已加载病例数、输入可用/到期数 | 只计当前页，不能称全局总量 |
| B | 本会话已知任务及最近打开病例 | 内存范围；重新验证会话时清空；任务保留 GET 观测时间，不推断全病例分析完成 |
| B | 病例 API 最近一次响应 / session 已确认 | 请求成功不能推出全系统健康；时间过期或读取失败明确显示 |
| C Backend 新增 | 全局统计、服务器搜索、Case 最新分析摘要、任务集合 | 独立 capability proposal，不修改 API contract |
| C | role/capabilities、GPU/Worker/Storage/Queue 遥测、审计 feed | 当前浏览器无可信字段，未接入/未知；不以用户名授权 |
| D 不应展示 | 首页概率、诊断、病灶结论、虚构健康/进度/总数 | Dashboard 不读取 Result、DICOM 或热图 |

## 状态与证据

READY 仅表示输入可用。没有 Job 关联显示分析未查询；JobRecord 缺少 model/protocol/slice，不能合并不同任务成为确定的病例结论。已知 COMPLETED 仅表示该任务完成；Result 仍须沿既有链路核验。progress/ETA 当前 Backend 返回 null，界面不造数。跨标签、focus 会话重验也可清空内存集合。

## 本地核验范围

本机注册的 Phase 5、frontend-v1、handoff worktree 无未提交改动。远端 feature/frontend-redesign-phase5 经 ls-remote/fetch 确认为上述基线；无法证明他人电脑不存在未推送改动。本任务独立 worktree，不覆盖其工作。
