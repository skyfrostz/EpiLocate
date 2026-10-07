# EpiLocate Phase 5 — GPU-only MVP 最终交付验收

**执行时间：**2026-09-28 22:50–23:05（Asia/Shanghai，最终复核时间见提交记录）。**分支：**`codex/p1-phase5-dual-mode-server-demo`。本轮起点：`4d717a3753ef307ab370adeafaf5a00da4dc7af9`；最终提交 SHA 以 Git 提交记录为准。未合并或推送。本轮只新增最终验收证据与人工运维文档，没有修改应用、冻结模型、checkpoint、协议或容差。

## 验收结论

| 门槛 | 结果 | 证据 |
| --- | --- | --- |
| GPU-only 全链路功能 | **PASS** | 新建 synthetic Case；指定 RTX 3090 Worker 的两项 attempt 1 均 `SUCCEEDED`，Prediction / Occlusion 均 `COMPLETED`、`LIVE_CASE`；浏览器结果和刷新恢复通过。 |
| 实际 CUDA | **PASS** | 当前独立 Worker 进程在矩池云容器运行，启动日志记录 `Worker execution device: CUDA`；两项 `job_attempts.worker_node_id` 均指向该 Worker；此前同一环境的 FrozenBaseline CUDA PoC 见 [上一阶段报告](gpu_full_chain_mvp_report.md)。DB 不单独持久化逐任务 accelerator 字段，故组合这些证据判断。 |
| 数据持久化 | **PASS** | PostgreSQL 的 Case/Job/Attempt/Result/Asset 与 MinIO 的一份 DICOM、九份 PNG 重新读取并逐项匹配大小及 SHA-256。 |
| CPU/GPU 固定数值一致性 | **FAIL / OPEN** | 最大 derived 偏差 `0.0010498762130737305`，冻结容差 `0.0001`。本轮没有修改模型、reference、算法或容差；不能宣称 CPU/GPU 可互换。 |

## 本轮全新 E2E

浏览器为 macOS 上的 **Playwright Chromium headless**，访问 `https://project.xbstu.com/mvp/`，使用仓库固定 synthetic DICOM `docs/interfaces/fixtures/p0_synthetic_ct.dcm`；输入 SHA-256 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`，无患者数据。新建了一次性账号用于验收，不写入密码或 Token；验收后撤销账号与 Backend 凭据。

| 对象 | 新 ID 与结果 |
| --- | --- |
| Case / Slice | `case_8fe29c5aa54ec10956b5e79306cb4ebe` / `slice_e20595b001e675685d688d2c4a07dd24`，Case `READY` |
| GPU Worker | `node_1db0cbcf325be5669472ebde94cb20a3`；Python `/root/miniconda3/envs/myconda/bin/python3.12`，PyTorch `2.4.0+cu121`，RTX 3090 |
| Prediction | Job `job_b06c183b11f5d6b9e173903d4241a5bc`；Result `result_91ba8d97bc194696960399cac84717a4`；`COMPLETED`、`LIVE_CASE`、attempt 1 `SUCCEEDED` |
| Occlusion | Job `job_0c2f41b8f0766873351c89ac77dce379`；Result `result_866d4964cf154c94847cf35d391fbd27`；`COMPLETED`、`LIVE_CASE`、attempt 1 `SUCCEEDED` |
| 冻结模型 | checkpoint `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`，两项 Job 的模型哈希均匹配 |
| Occlusion | 16/32/64 px 位置分别 **729/169/36**；candidate、comparison、response 各三尺度，共 **9** 个 Heatmap Assets |

浏览器完成登录、Case 创建、上传、CT 解码、Prediction/Occlusion 创建与结果展示、三尺度/三图层切换、CT Overlay 与 70% 透明度，刷新后恢复 64 px comparison 图层、Overlay 与透明度；注销后受保护 API 返回 401。完成后又用新会话重新打开结果页，等待 CT 真正渲染，再拍摄 [Prediction](evidence/gpu_final/prediction-result-rendered.png)、[Occlusion Overlay](evidence/gpu_final/occlusion-overlay-rendered.png) 与 [刷新恢复](evidence/gpu_final/refresh-restored-rendered.png)。[浏览器脱敏摘要](evidence/gpu_final/browser-e2e-summary.json)记录新 ID、位置数、9 个 PNG SHA-256 和各步骤结论。

ECS 直接复读 PostgreSQL 与私有 MinIO：[脱敏持久化审计](evidence/gpu_final/persistence-audit.json)记录 DICOM 18,522 bytes 与输入 SHA-256 一致，9/9 PNG 的字节数与 SHA-256 均匹配数据库 Asset 行。Worker 在数据库已注册，复读时 `IDLE` 且心跳距当前约 6.9 秒；两项成功 attempt 均指向指定 Worker。完成 Job 的 `inference_jobs.worker_node_id` 会清空，归属以 `job_attempts` 为准。

本轮后 ECS 上 `epilocate-minio`、`epilocate-backend`、`epilocate-gateway`、`epilocate-sweeper`、`epilocate-review`、`epilocate-gradio`、`aid-site`、`nginx` 均保持 active；旧 `/healthz` 与新 `/mvp/` 均 HTTP 200。没有启动 ECS CPU Worker，也没有变更旧服务或正式根入口。

## 本轮回归与证据边界

| 本轮重新执行 | 结果 |
| --- | --- |
| `cd frontend && npm test -- --run` | 36 passed；jsdom `scrollTo` 提示 |
| `cd frontend && VITE_PUBLIC_BASE=/mvp/ npm run build` | PASS；既有 codec externalization 与大 chunk 提示 |
| `PYTHONPATH="$PWD" .venv/bin/python -m pytest -q session_gateway/tests backend_v2/tests` | 19 passed，2 skipped；跳过项不计为通过 |
| `PYTHONPATH="$PWD" <冻结 Python 3.11> -m pytest -q tests/test_worker` | 29 passed；协议/设备回归，不是本轮另一次 GPU 推理 |
| Playwright Chromium、ECS PostgreSQL/MinIO 复读、GPU 进程/日志、旧服务检查 | PASS；使用本轮新 Case/Jobs |
| `git diff --check` | 提交前执行并记录结果 |

上一阶段报告中的 CPU/GPU 数值对比、GPU 本机 PoC、GPU 资源峰值属于**引用已有验收**；本轮没有重跑固定数值比较或容器重启演练。首次截图发生在 CT 加载期间，已通过重新打开页面、等待真实画面与重拍更正；最终提交的是渲染完成后的截图。首次自写持久化查询误以为完成 Job 保留 `worker_node_id`，按真实 schema 改用 `job_attempts` 后复读通过；这不是任务执行失败。

## 运维、未解决项和交付界限

GPU Worker 启动、停止、状态、日志及人工恢复步骤见 [GPU Worker MVP 运维说明](gpu_worker_mvp_operations.md)。当前 Worker 在 tmux 会话 `epilocate-gpu-worker` 中运行，日志位于 `/mnt/epilocate-mvp/logs/worker.log`，工作与数据根为 `/mnt/epilocate-mvp`，启动脚本强制 CUDA。本轮没有停/重启正在服务的 Worker；人工重启步骤依据真实启动命令与代码信号处理，**未通过容器重启演练**。

**Remaining Open Issues：**CPU/GPU 固定数值一致性 FAIL / OPEN；GPU tmux 进程无自动重启；矩池云实例释放后的持久性未验证；缺少独立异地备份/恢复演练；MinIO 当前未实现 KMS 支持的服务端静态加密，Backend 仍持有 MinIO root 凭据。这些不改变本轮 GPU-only 工程 MVP 功能通过结论，也不构成 Production Ready 声明。
