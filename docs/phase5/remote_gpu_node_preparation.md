# Phase 5 Remote GPU AI Node 接入准备

状态：本地配置准备阶段。本文不代表 ECS 或矩池云已连接，不包含生产凭据，不执行端口、Nginx、防火墙、DNS 或数据库变更。

基线 Worktree：`LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`
分支：`codex/p1-phase5-dual-mode-server-demo`
本阶段审计起点：`7babd923c1d40d67c7abe4c0a0d957c60b8d4d0b`

## 1. 已核验事实、设计结论和未执行项目

### 已核验事实

- 现有 Worker 继续使用 Register、Heartbeat、Claim、Submit；`BACKEND_URL` 必须是 HTTPS origin，Bearer Token 由服务端按哈希识别，`WORKER_CA_CERT` 可用于受控 CA。
- `WORKER_DEVICE` 保留 `CPU`、`CUDA`、`AUTO`。显式 `CUDA` 不可用时启动失败，不降级为 CPU。
- GPU 节点实际能力由负责人提供的矩池云验证记录确认：RTX 3090 24 GB、驱动 535.216.01、驱动支持 CUDA 12.2、PyTorch 2.4.0+cu121、PyTorch CUDA 12.1，`torch.cuda.is_available()` 为 True；`cuda:0` 的 1024×1024 矩阵乘法及同步成功，分配 20.12 MiB。
- 上述结果只证明基础 CUDA 运行，不证明 FrozenBaseline GPU 推理、跨云通信或 GPU E2E。
- Worker 下载 Claim 返回的 HTTPS 签名 DICOM URL；结果和 9 个热图通过 Worker result multipart 交给 Backend，GPU 节点不需要 PostgreSQL、MinIO 管理接口或长期 S3 凭据。
- 当前 Claim 逻辑按模型和 checkpoint hash 匹配，未按 CPU/GPU 设备筛选；GPU 首次验收必须使用隔离环境或批准的领取窗口。
- ECS 新 Control Plane 尚未部署；现有正式域名仍属于旧 Review Server。本阶段不能进行正式跨云 E2E。

### 本地设计方案

采用“GPU 主动发起、两个回环 TLS 入口、受限 SSH 本地转发”的最小准备方案：

```text
ECS CPU Worker  -- HTTPS https://127.0.0.1:9443 --> ECS Worker TLS edge --> Backend
ECS Backend     -- presign https://127.0.0.1:9444 --> ECS object TLS edge --> MinIO
GPU Worker      -- local SSH -L 9443/9444 --> ECS loopback TLS edges
```

两种 Worker 使用完全相同的 origin：

```text
Worker API origin:  https://127.0.0.1:9443
Object GET origin:  https://127.0.0.1:9444
```

GPU 节点只在本地监听这两个回环端口；SSH 服务端仅允许转发到 ECS 的 `127.0.0.1:9443` 和 `127.0.0.1:9444`。证书 SAN 必须包含 `127.0.0.1`，GPU 和 ECS Worker 都使用同一个受信任 CA。Backend 生成的 `EPILOCATE_V2_S3_PUBLIC_ENDPOINT` 必须是 `https://127.0.0.1:9444`，代理保持签名 Host（含端口）、路径和原始查询串不变。

这只是候选拓扑。矩池云实际容器是否允许主动出站 SSH、实例是否可持久运行、以及 ECS 是否允许专用转发账号，需经单独授权后核验。

## 2. 矩池云只读核验清单

以下命令是拟执行清单，不是本轮已执行证据。仅输出版本、能力和路径元数据，不输出环境变量值、Token、私钥、患者数据或 DICOM 内容。

### 身份、系统和 GPU

```sh
hostname
id -un
uname -a
cat /etc/os-release
systemd-detect-virt --quiet && systemd-detect-virt || true
cat /proc/1/cgroup
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free --format=csv,noheader
python - <<'PY'
import torch
print({
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "device_count": torch.cuda.device_count(),
    "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
})
PY
```

不重复安装 CUDA/PyTorch，不重跑已提供的基础矩阵测试；后续只在 GPU E2E 批准后运行 FrozenBaseline 验证。

### 出站网络、SSH 和隧道能力

```sh
command -v ssh
ssh -V
command -v curl
curl --version | head -n 1
ip -brief address
ip route
cat /proc/net/route
getent ahostsv4 example.com
timeout 5 sh -c ':</dev/tcp/127.0.0.1/22' 2>/dev/null || true
test -e /dev/net/tun && stat -c '%F %a %U:%G' /dev/net/tun || echo 'TUN_UNAVAILABLE'
grep '^Cap\(Inh\|Prm\|Eff\):' /proc/self/status
command -v capsh >/dev/null && capsh --print | sed -n '1,12p' || true
```

跨云连通性探测（到获批 ECS 目标）另列为后续授权命令，不在本轮执行：

```sh
ssh -F /private/approved/ssh_config \
    -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=10 -o ExitOnForwardFailure=yes \
    -N -L 127.0.0.1:9443:127.0.0.1:9443 \
    -L 127.0.0.1:9444:127.0.0.1:9444 epilocate-control-plane-tunnel
```

### 持久化和进程生命周期

```sh
findmnt -T /mnt -o TARGET,SOURCE,FSTYPE,OPTIONS
df -hT / /mnt
stat -c '%A %U:%G %n' /mnt
command -v tmux || true
command -v systemctl || true
ps -p 1 -o pid=,comm=,args=
ulimit -a
```

平台层还需由负责人确认：实例释放后是否保留进程和网络状态、入口命令是否在启动后自动执行、端口是否只能在租用时导出、`/mnt` 是否属于该区域持久网盘、以及 GPU 实例是否支持保存环境。断开 SSH 后可通过 tmux 保持进程，不能据此推断实例释放后自动恢复。

## 3. ECS 只读核验清单和权限

ECS 侧只需 root 或经批准的等价只读审计账号；不允许使用 Docker 管理接口或任何修改状态的命令，除非另行批准。

```sh
ssh -G epilocate
ssh-keygen -F epilocate -l
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes epilocate \
  'hostname; id -un; ip -o -4 addr show scope global'
ssh epilocate 'ss -H -lnt; systemctl is-active nginx; nginx -v'
ssh epilocate 'systemctl show nginx -p FragmentPath -p ExecMainPID -p ActiveState --no-pager'
ssh epilocate 'find /etc/nginx/sites-enabled -maxdepth 1 -type f -print'
ssh epilocate 'find /etc/systemd/system -maxdepth 1 -type f -name "*epilocate*" -print'
```

须脱敏记录：Worker/object TLS 入口是否监听回环、证书路径和 SAN 元数据、Nginx 路由摘要、SSH 转发策略、云安全组/主机防火墙规则、旧 Review Server 状态及可用磁盘。禁止读取完整环境变量、证书私钥、数据库内容、用户数据和日志中的签名查询串。

## 4. SSH 转发账号和证书方案

ECS 需要一个专用 `epilocate-gpu-tunnel` 账号，不使用 root，不允许密码登录、TTY、Shell、Agent/X11 转发。账号的 SSH key 只保存在矩池云私有目录，known_hosts 必须通过可信渠道核验。

服务端最终配置应限制：

- `AllowTcpForwarding local`；
- `PermitOpen 127.0.0.1:9443 127.0.0.1:9444`；
- `PermitTTY no`、`AllowAgentForwarding no`、`X11Forwarding no`；
- 禁止转发到 PostgreSQL、MinIO 原始端口、管理端口或任意公网地址；
- 断线由 GPU 侧监督进程重新建立，建立失败时 Worker 不启动、不领取新任务。

SSH 仅提供加密传输，不能替代 Worker API Bearer Token、TLS 证书校验或签名 URL 校验。隧道建立成功不算 MinIO 验收通过。

## 5. 本地配置与测试

已添加不含凭据的 [GPU Worker 环境模板](../../deploy/remote_gpu_worker.env.example) 和 [SSH 转发模板](../../deploy/remote_gpu_worker_ssh_tunnel.example.conf)。模板中的 hash 是当前冻结 checkpoint hash；Token 有意不放入仓库。

本地静态测试覆盖：

- GPU 模式为 `CUDA`，hash 与 `MODEL_VERSION` 一致；
- Worker API 使用 HTTPS 回环 origin；
- 模板不含 Token 或私钥；
- SSH 只转发 9443/9444，启用严格主机密钥校验、连接失败即退出和 keepalive；
- 不允许转发 PostgreSQL 5432、MinIO 9000 或 `0.0.0.0`。

后续获批的实际传输测试顺序：

1. GPU 节点到 ECS Worker edge 的 Register/Heartbeat/Claim/Submit 小流量探测；
2. 生成真实 Claim 的签名 URL，分别从 ECS CPU Worker 和 GPU Worker 下载同一对象；
3. 对比两端响应状态、响应字节 SHA-256、Host/路径/查询串保真和日志无 SigV4 查询串；
4. 执行结果 multipart 上传并通过 Backend API/MinIO 重读；
5. 主动断开隧道，确认 GPU Worker 停止领取且心跳/租约按原协议恢复；
6. 仅在以上通过后进入受控 GPU FrozenBaseline E2E。

## 6. GPU 任务归属与 E2E 门槛

当前协议没有设备路由字段，本阶段不修改调度协议。首次 GPU E2E 必须：

1. 暂停或隔离 CPU Worker 的领取，或使用只包含 GPU Worker 的批准队列；
2. 记录 GPU Worker ID、注册时 `hardware.accelerator=CUDA`、实际 `torch.device=cuda:0`、任务 attempt 和结果 provenance；
3. 使用相同去标识输入和冻结 checkpoint 先运行 CPU 参考包，再运行 CUDA 比较门；
4. 固定使用已有阈值：概率/派生值绝对差 ≤`1e-4`，解码 PNG 差 ≤2 灰度级，离散类别、位置索引、候选 mask、几何、schema、输入 hash 和模型 hash 必须一致；
5. 最后执行真实 `LIVE_CASE` Prediction、16/32/64 Occlusion、729/169/36 位置和 9 个资产持久化验收。

基础矩阵乘法通过不能替代这些门槛。

## 7. 故障恢复和 Stage 4A 依赖

- 隧道失败：不启动 Worker 或暂停 Claim；保留既有租约处理，不修改 90 秒 lease、15 秒 heartbeat 和 45 秒 offline 判定。
- Worker 进程崩溃：保留独立数据目录和 claim 状态，监督进程重启后先 Register/Heartbeat，再允许 Claim；由现有协议处理过期 attempt。
- ECS TLS edge 或对象 edge 异常：GPU Worker 停止领取；不绕过证书验证，不改成直接 MinIO 凭据。
- GPU 实例释放/重建：从 `/mnt` 恢复代码、模型和 CA；重新核验 GPU、driver、PyTorch 和 host key，不能假设旧进程仍在。
- 回滚：关闭 GPU Worker/tunnel、撤销 GPU Worker Token、恢复仅 CPU Worker；不删除 ECS 数据，不改变旧 Review Server 和正式域名。

正式接入依赖 Stage 4A：先部署并验收私有 Control Plane、PostgreSQL、MinIO、Backend、Gateway、Sweeper、CPU Worker 及两个回环 TLS edge；完成容量、备份、日志和 SigV4 验收后，才可申请 GPU 跨云传输和 GPU E2E。正式公网入口、旧服务停止和域名切换仍是独立审批动作。

## 8. 本阶段未执行项目

- 未连接矩池云或 ECS；
- 未开放端口、修改 Nginx、防火墙、DNS、systemd 或 Docker；
- 未创建线上 Worker Token、SSH key、TLS 私钥或 CA；
- 未运行跨云 Worker API、签名对象下载、FrozenBaseline CUDA 推理或 GPU E2E；
- 未合并、推送或修改其他 Worktree。
