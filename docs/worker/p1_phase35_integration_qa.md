# P1 Phase 3.5 — GPU Worker 集成与回归 QA

日期：2026-09-27。范围仅限本次独立本地集成 worktree；不代表 NVIDIA GPU 或生产部署验收。

## Git 集成

- 集成基线：`p0/integration` 的 `c9a5cc6373ffc889725971e3cae5bc09252790bd`。
- 输入分支：`feature/p1-gpu-worker` 的 `396d188b6184ec08ce6b71e5f5b1dab7206dc00b`；`merge-base` 恰为上述基线。
- 独立 worktree：`LOCAL_WORKTREE/EpiLocate-p1-phase35-integration`，分支 `codex/p1-phase35-integration`。
- 无冲突合并提交：`fd0e55ff52c20b58858e7ad26ff850e54bcd8a6d`；父提交依次为 `c9a5cc6373ffc889725971e3cae5bc09252790bd`、`396d188b6184ec08ce6b71e5f5b1dab7206dc00b`。
- GPU Worker 输入提交只涉及 `worker/`、`tests/test_worker/`、`qa/` 和 `docs/worker/`。Backend v2、Vue Frontend、冻结算法、checkpoint、训练、Stage 1 和冻结 API contract 均未被合并提交改动。
- 本次 QA 增加可复用的临时凭据输出开关与权限探针、无凭据 JSON 记录和合成病例的浏览器截图。凭据仅写在 worktree 外的 `0600` 临时文件，未纳入提交。

## 四类状态

| 状态 | 结论 |
| --- | --- |
| Implemented | CPU/CUDA/AUTO 设备选择、显式 CUDA 拒绝、实际设备上报、OOM 失败处理、CPU reference 和固定容差比较工具已集成。原有 CPU Worker、Worker 鉴权、heartbeat、租约续期、结果提交、PostgreSQL/MinIO 和 Vue DICOM 刷新逻辑保留。 |
| CPU validated | 本次独立重跑 Worker/Backend/Frontend 测试、迁移与对象存储验证、冻结 reference 比较，以及真实 HTTPS Backend + PostgreSQL + MinIO + CPU Worker + Vue 浏览器 E2E，全部通过。 |
| GPU validated | **否**。当前是 Apple Silicon 主机，PyTorch 2.14.0 的 CUDA runtime 为 `None`，`torch.cuda.is_available()` 为 `False`，设备数为 0。GPU numerical validation、GPU benchmark、GPU E2E：**NOT RUN**。 |
| Production validated | **否**。使用隔离的本机容器和临时自签名 TLS；未执行公网或生产部署。 |

## 设备与数值回归

- 显式 `CPU` 选择 CPU；`AUTO` 在本机选择并报告 CPU；显式 `CUDA` 抛出 `DeviceUnavailable`，没有静默回退。
- 冻结 checkpoint SHA-256：`548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`。合成 DICOM SHA-256：`8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`。
- 重新运行 CPU FrozenBaseline，使用原始 [reference](p1_cpu_reference.json) 比较：[本次机器记录](p1_phase35_cpu_reference_regression.json) `passed=true`，概率、派生数值和解码 PNG 最大差异均为 0。预测 `negative`，正类概率 `0.025618407875299454`，置信度 `0.9743815921247005`；三尺度位置 729/169/36，共 934；9 张资产的 schema、坐标几何和 manifest 一致。
- 预先固定的未来 GPU 门槛保持原值：概率与派生数值绝对差 `<= 1e-4`、解码响应图像素差 `<= 2`；类别、位置索引、候选 mask、几何、schema、模型和输入 hash 必须精确一致。本次没有 GPU 候选 bundle，未执行 CPU/GPU 比较。
- 本机 CPU 单次观测：模型初始化 161.807 ms；分类冷/热 9.581/8.495 ms；三尺度遮挡冷/热 11300.566/11899.462 ms。仅用于本次回归，不作性能优越性结论。

## 全量回归与真实 E2E

| 检查 | 本次结果 |
| --- | --- |
| Worker 测试 | 29 passed，0 skipped。包含设备选择、模拟 OOM、心跳与续租、重连、重试和结果上传；模拟用例不算 CUDA 验收。 |
| Backend v2 测试 | 16 passed，0 skipped，1 条第三方 Starlette/httpx deprecation warning。包含认证、授权、生产型存储、真实 CPU Worker 集成。 |
| Frontend 测试与构建 | 21 passed，0 skipped；生产构建通过。现有 Cornerstone codec externalization、大块和 jsdom `scrollTo` 提示不影响此次通过。 |
| PostgreSQL / MinIO | 隔离 PostgreSQL 16 升级到 Alembic head，14 张必需表存在于 16 张实际表；私有 MinIO bucket 的上传、读取、SHA-256、签名 URL、删除通过。 |
| 真实 Worker E2E | [记录](p1_phase35_cpu_stack_e2e.json)：经数据库签发的 User/Worker 凭据，创建匿名 Case、上传合成 DICOM，Case 为 READY；两个 Job 由实际 CPU Worker + FrozenBaseline 完成；两个 Result 为 `LIVE_CASE`；9 张 PNG 通过 Backend 授权路由可读；位置分页 729/169/36。未使用 Mock Result。 |
| 实际 HTTP 安全矩阵 | [27 项记录](p1_phase35_auth_matrix.json)：所有者 7 条资源路径返回 200，另一用户 7 条返回 404，匿名请求 7 条返回 401；失效/撤销/非法凭据、User/Worker 凭据互用被拒；跨用户创建 Prediction 返回 404。 |
| 浏览器 E2E | Vue 经服务端代理附加 User Bearer，病例列表、READY 详情、112×80 DICOM 刷新恢复、Job COMPLETED、`LIVE_CASE` 结果、16/32/64 px 切换和 224×224 授权热力图均在真实浏览器可见。64 px 图像自然尺寸确认为 224×224。 |

浏览器截图：[DICOM 刷新恢复](../../output/playwright/p1_phase35_case_refresh.png)、[Job 完成](../../output/playwright/p1_phase35_job_completed.png)、[16 px](../../output/playwright/p1_phase35_result_16.png)、[32 px](../../output/playwright/p1_phase35_result_32.png)、[64 px](../../output/playwright/p1_phase35_result_64.png)。图像来自仓库合成 DICOM，不含患者身份或访问凭据。

## 兼容性与剩余风险

- Worker 继续调用现有 `/api/v2/workers/register`、`/heartbeat`、`/jobs/claim` 和 `/jobs/{job_id}/result`；真实 E2E 证明当前 Backend API v2 接受其认证、租约与结果 payload。用户路由与 Worker 路由使用不同凭据，实际 HTTP 权限矩阵通过。冻结 contract 未改动。
- 租约与 heartbeat 的长任务恢复主要由 Worker 测试模拟验证；本次约 12 秒的 CPU 遮挡没有持续到多个真实 15 秒心跳周期。NVIDIA 主机仍需长时间运行、实际 OOM、续租和重连验收。
- 前端目前分别显示原始 CT 与算法响应图，并明确提示坐标不可直接叠加。本阶段不进行 heatmap coordinate fusion。
- GPU numerical validation、GPU benchmark、GPU E2E 均保持开放；生产环境的 TLS、密钥管理、存储生命周期和负载稳定性尚未在本次本地 QA 中验收。
