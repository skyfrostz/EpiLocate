# 源码分布与整合边界

| 路径 | 实际职责 | 审查和修改时应遵守的边界 |
|---|---|---|
| `apps/landing/` | Welcome，React/Vite 欢迎页 | 独立构建；不提供病例管理、推理和登录会话。 |
| `frontend/` | Vue 工作台、任务状态、空间响应和影像查看 | 用合成或测试资产验证几何、缩放、会话恢复与错误状态。 |
| `session_gateway/` | 浏览器会话、请求代理和会话边界 | 后端用户与 Worker 凭据不直接交给前端。 |
| `backend_v2/` | 病例、输入、任务、结果、资产、身份及数据库迁移 | 权限同时作用于结果与资产；后端不执行模型。 |
| `worker/` | 独立计算、设备选择、任务协议与结果提交 | 固定模型、几何、预处理和数值容差；设备变化需另行验证。 |
| `algorithm/`、`src/`、`configs/`、`scripts/` | 基线、数据处理、研究工具与配置 | 开放程序不包括其研究输入、模型或运行许可。 |
| `research/next-hospital-20261014/`、`epilocate_next/` | 研究准备、协议、生成测试及工程实现 | 定义/检查器的存在不能代替合格参考、受控真实运行与独立准入。 |
| `research/portable-p2/` | 可独立运行的分层查询路由 | 生成分数用于功能检查，只在已查询位置解释响应。 |
| `research/source-excerpts/r168-roi/` | 可复核的 ROI 前后端和迁移摘录 | 该目录是独立交付内容；是否接入运行中的应用需由目标版本与测试证明。 |
| `aid_site/`、`epilocate_review_server/`、`gradio_service/` | 展示站、历史人工复核、早期服务与原型 | 三者的账户、受众和用途与 AI 工作台分开。 |
| `deploy/` | 部署配置和依赖示例 | 指向示例环境；参数清单不构成任何现网状态证明。 |

历史整合采用按文件导入。较早规划中的 `services/` 等迁移目标不代表已迁移；应以仓库实际实现为准。[来源与公开范围](../handoff/SOURCE_PROVENANCE.md) · [模块验收手册](../engineering/PUBLIC_OPERATOR_GUIDE.md)
