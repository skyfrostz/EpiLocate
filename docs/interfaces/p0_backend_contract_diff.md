# P0 后端契约差异（基线 3b3c270）

本记录先于后端修改生成。以当前可运行代码为准；`algorithm_api_contract.yaml` 是目标契约，不直接改动。

| 项目 | 目标契约/交接要求 | 基线实际实现 | 后端处理 |
| --- | --- | --- | --- |
| 单片 DICOM、Baseline、遮挡、位置分页和资产 | P0 可用 | 已通过本机 HTTP/Gradio 验证 | 保持字段和算法结果语义 |
| Job 取消 | `POST /jobs/{id}/cancel` 可安全取消 | 501 | 仅允许取消未开始的队列任务；运行中明确 409 |
| 幂等 | 同键同请求仅建一个任务 | SQLite 先查再写，提交与键登记非原子；并发请求可能重复提交 | 原子占位并保证失败释放；并发中的同键请求明确冲突 |
| Job 状态 | `PENDING/RUNNING/COMPLETED/FAILED/CANCELLED` | v1 映射前四种；Mock 保留小写 v0.1 | v1 补 `CANCELLED`，Mock 响应维持原型兼容 |
| 资产授权 | 对象授权 | 仅校验 result 的 asset_id；本机未认证 | 配置令牌时保护影像相关 API；仍需集成层身份和按对象授权 |
| 上传资源 | 文件类型、质量、隔离 | DICOM 内容检查、大小上限、匿名 ID；文件落盘前无持久幂等占位 | 加强提交原子性、错误处理和存储根保护 |
| 模型缓存 | 每进程只加载一次 | `FrozenBaseline` 的锁和 `_model` 已缓存 | 复用，不改算法 |
| 能力 | 实际可用才 `available` | 由 `baseline.ready()` 决定；其余列 planned | 保留；补未实现项的显式状态 |
| 冻结 validation 摘要 | 设计稿有只读端点 | 未实现 | 维持未实现，不访问 formal test |
| 多切片、NIfTI、患者级、Robust、粗定位、LIME、医生反馈 | 目标/预留 | 未实现或 501 | 不声明可用 |

已验证服务仅适用于 loopback 开发。现有 v0.1 Mock `/jobs/inference` 与 v1 真实接口状态格式不同，属于明确的版本边界；不改既有字段或错误码。`backend_handoff.md` 与 `implementation_roadmap.md` 的早期 B 分支状态已过时，以 `p0_verification_record.md` 和当前代码为准。
