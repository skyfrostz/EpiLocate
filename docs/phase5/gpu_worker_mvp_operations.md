# GPU Worker MVP 人工运维

适用范围：2026-09-28 已部署的矩池云 RTX 3090 GPU-only MVP。ECS 只运行控制平面；**不要启动 ECS CPU Worker**。本说明记录已观察到的进程、配置和任务证据；下列人工重启步骤是依据当前启动脚本和 Worker 信号处理实现制定，尚未做容器重启演练。

## 新节点与固定提交来源

以下步骤用于**新 candidate**，不能据此宣称当前运行目录已具备 Git 来源证明。当前 GPU `/mnt/epilocate-mvp/source` 没有 `.git` 或 `SOURCE_COMMIT`。先从 GitHub 交接分支的完整、已通过安全审计的 SHA，在独立目录运行 `deploy/release/prepare_from_git.sh`；该脚本只导出该提交并写入 `SOURCE_COMMIT`，不切换服务。例如目标可设为 `/mnt/epilocate-mvp/releases/<sha>/`。ECS candidate 同样从该 SHA 独立导出，不能从 Mac 复制临时工作树或对运行中的 `current` 执行 `git pull`。确认导出目录的 `SOURCE_COMMIT` 等于批准 SHA，再校验 `worker/`、`algorithm/`、启动脚本及 checkpoint 哈希；凭据仍在受限目录，不放入 Git 导出树。

当前 RTX 3090 经核验的 Python 为 3.12，PyTorch `2.4.0+cu121`、TorchVision `0.19.0+cu121`、CUDA 12.1。新隔离环境使用 `deploy/gpu/requirements-gpu-worker.txt` 的直接依赖版本，不复制整份 Conda freeze，也不换模型或容差。PyTorch 官方的 [2.4.0 CUDA 12.1 安装说明](https://docs.pytorch.org/get-started/previous-versions/) 指向 cu121 wheel index。安装后在**相同 Python 解释器**下执行：

```sh
python3.12 -m venv /PRIVATE-PATH/epilocate-gpu-venv
/PRIVATE-PATH/epilocate-gpu-venv/bin/python -m pip install -r deploy/gpu/requirements-gpu-worker.txt
/PRIVATE-PATH/epilocate-gpu-venv/bin/python -m pip check
/PRIVATE-PATH/epilocate-gpu-venv/bin/python - <<'PY'
import torch
import torchvision
assert torch.__version__ == '2.4.0+cu121'
assert torchvision.__version__ == '0.19.0+cu121'
assert torch.version.cuda == '12.1' and torch.cuda.is_available()
print(torch.cuda.get_device_name(0))
PY
```

在发布前，另用**已批准、可公开的 synthetic JPEG Lossless DICOM fixture**核对 Transfer Syntax `1.2.840.10008.1.2.4.70`，并访问 `pydicom.dcmread(path).pixel_array`，只记录 shape、dtype、成功状态，不记录像素或患者元数据。仓库目前没有该压缩 synthetic fixture，因此这一项不能从安装成功直接判为 PASS。核对冻结 checkpoint 的 SHA-256 为 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`。然后在独立 candidate Worker 身份下执行 synthetic Prediction 与 Occlusion，确认 `WORKER_DEVICE=CUDA`、完成态、九张 heatmap 和持久化；在没有完成这些检查前，保留当前正常 Worker。

新版本 `deploy/mvp/run_gpu_worker.sh` 要求源码目录中存在有效 `SOURCE_COMMIT`，并可用 `EPILOCATE_EXPECTED_SOURCE_COMMIT` 与批准 SHA 比对。部署时需将新脚本与新源码配套切换；不要把它单独覆盖到尚无 marker 的当前目录。CPU/GPU 固定数值一致性仍为 `FAIL / OPEN`，不得以 CUDA 功能通过替代该门槛。

## 当前实例

- SSH 别名：`epilocate-gpu`；连接须使用 `BatchMode=yes`、`StrictHostKeyChecking=yes`，先核对负责人确认的 ED25519 主机指纹。
- 持久工作根：`/mnt/epilocate-mvp`；源代码工作目录：`/mnt/epilocate-mvp/source`。
- 启动脚本：`/mnt/epilocate-mvp/run_gpu_worker.sh`；Python：`/root/miniconda3/envs/myconda/bin/python3.12`。
- 私密环境文件：`/mnt/epilocate-mvp/secrets/worker.env`，当前所有者 root、权限 `0600`；仅在 GPU 节点读取。它提供 `WORKER_ID`、`WORKER_TOKEN`、`MODEL_HASH`、`BACKEND_URL`、`EPILOCATE_FROZEN_ROOT`、`WORKER_DATA_ROOT`。不要复制到仓库或工单。
- 当前 `WORKER_ID=node_<private-id>`，`BACKEND_URL=https://project.xbstu.com`，冻结 checkpoint SHA-256 为 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`。启动脚本在载入私密环境后强制 `WORKER_DEVICE=CUDA`，执行 `python -m worker`。Worker API 为 `/api/v2/workers/`；DICOM 的签名 GET 经同一 HTTPS 站点的 `/epilocate-private/`，TLS 校验保持开启。
- 日志：`/mnt/epilocate-mvp/logs/worker.log`；运行会话：`epilocate-gpu-worker`（tmux）。不把日志原样贴到公开渠道；先删去可能出现的凭据和签名 URL。

## Start

在已核验身份的 GPU 节点上，以当前部署用户 root 执行。先确认 `tmux has-session -t epilocate-gpu-worker` 返回非零且无 `python3.12 -m worker` 进程，避免两个 Worker 使用相同身份。确认源码、checkpoint、Python 和私密环境文件仍在持久目录中；如文件缺失，停止并恢复已批准的部署材料，勿临时换模型或凭据。

```sh
tmux new-session -d -s epilocate-gpu-worker '/mnt/epilocate-mvp/run_gpu_worker.sh >>/mnt/epilocate-mvp/logs/worker.log 2>&1'
```

这与当前 tmux pane 实际启动命令一致。脚本会检查私密环境文件是当前用户拥有的普通文件且权限为 `0600`。启动后执行下节检查；仅有 tmux 会话不代表注册或领取成功。

## Status 与 Claim 证明

```sh
tmux has-session -t epilocate-gpu-worker
pgrep -af '[p]ython3.12 -m worker'
tail -n 100 /mnt/epilocate-mvp/logs/worker.log
nvidia-smi
```

启动日志必须含 `Worker execution device: CUDA`。在 ECS 上使用既有的授权、只读 PostgreSQL 访问，检查 `worker_nodes` 中上述 `node_id` 的 `registered_at`、`last_heartbeat_at`、`activity_state` 和 `disabled_at`；心跳应持续更新。**Claim 的持久证据在 `job_attempts.worker_node_id`**，与 `worker_nodes.id` 关联，并核对该 attempt 的 `outcome=SUCCEEDED`、Job 的 `status=COMPLETED` 和 Result 的 `source=LIVE_CASE`。完成后的 `inference_jobs.worker_node_id` 会清空，不能据此判断 Worker 归属。当前最终验收的 Prediction Job 为 `job_<private-id>`，Occlusion Job 为 `job_<private-id>`；两者的 attempt 1 均由上述 GPU Worker 成功执行。

日志中的 CUDA 启动记录、实时 GPU 进程、DB 中的 Worker 归属和完成结果需组合判断。单独看到注册、心跳或 CUDA 空载均不能证明新任务完成了 GPU 推理。

## Stop

先停止提交新任务，并确认该 Worker 没有 `RUNNING` attempt；若在执行中，等其完成及结果提交。随后在 GPU 节点运行：

```sh
tmux send-keys -t epilocate-gpu-worker C-c
tmux has-session -t epilocate-gpu-worker
pgrep -af '[p]ython3.12 -m worker'
```

`worker.__main__` 的 SIGINT/SIGTERM 处理会设置停止事件并在退出时调用 `agent.stop()`。后两条检查应最终显示会话和进程均已结束；若未结束，先检查日志和租约，不要立即强杀或重复启动。SSH 断线时只离开 tmux 会话，不发送 `C-c`。

## Recovery

- **SSH 断开：** detached tmux 会继续运行。重新核验 SSH 主机指纹后连接，检查会话、进程、心跳和 CUDA 日志；不要重复启动。
- **Worker 进程退出：** 确认旧进程确已退出、没有活动 attempt 或待提交结果，读取本机日志末尾并检查私密环境/模型文件元数据。按 Start 启动一次，确认注册、心跳，然后用下一笔受控 synthetic Job 验证 Claim/Submit。租约超时与重试由现有 Backend/Sweeper 协议处理，不手工改 Job 状态。
- **矩池云容器重启：** 本 MVP 没有自动重启。先确认 `/mnt/epilocate-mvp` 的源码、checkpoint、数据、脚本、私密环境和日志均仍在，Python/CUDA 可用；再按 Start 启动。实例释放后的持久性尚未实测，路径缺失时停止并按批准的备份/部署程序恢复。
- **Backend 暂时不可达：** 先核查 ECS 控制平面和公开 HTTPS Worker API，再观察 Worker 自动重连与心跳恢复。不要关闭 TLS 校验或开放未认证 API。网络恢复后若 Worker 未重新注册/心跳，再按上述安全 Stop/Start 处理；过期 attempt 的恢复交给 Sweeper。
- **回退：** 若本轮 GPU Worker 无法恢复，停止 GPU 领取并保留 PostgreSQL、MinIO 与日志证据；不要临时启用 ECS CPU Worker 来冒充 GPU-only 验收。旧 Review Server、Gradio、Aid 不在 Worker 操作范围内。

## JPEG Lossless 依赖复核（2026-09-29 事故）

本次实际上传对象使用 JPEG Lossless Transfer Syntax `1.2.840.10008.1.2.4.70`。GPU Python 曾缺少 `pylibjpeg` 与 `pylibjpeg-libjpeg`，使 pydicom `pixel_array` 抛出缺失插件的 `RuntimeError`；两项 Job 因而为 `INFERENCE_FAILED`。当前运行环境已补 `pylibjpeg==2.1.0`、`pylibjpeg-libjpeg==2.4.0`，PyTorch/CUDA 和冻结 checkpoint 未改变。恢复容器或重建环境时，在启动 Worker 前核对这两项依赖，以及经批准的脱敏 JPEG Lossless fixture 能在该 Python 下解码；`Case READY` 只代表上传头部校验通过。缺依赖时按事故报告的最小版本补齐，不修改影像、模型或容差。详见[事故记录](gpu_failed_job_incident_20260929.md)。

## Secret 与日志边界

不要把 Bearer Token、SSH 私钥、PostgreSQL/MinIO 密码、Session secret、完整签名 URL、原始患者影像写入 Markdown、Git、截图或工单。只记录变量名和权限受控的文件位置。当前 Worker 使用公网可信 TLS CA，不能通过 `verify=false` 绕过证书校验。任何凭据轮换或线上配置改动须另行审批。
