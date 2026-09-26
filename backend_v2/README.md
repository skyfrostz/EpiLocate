# Backend v2 Phase 1

独立 FastAPI 入口：`backend_v2.api.app:app`。P0 `gradio_service` 未修改；部署时由反向代理将 `/api/v2` 指向此应用，旧入口保持原服务。

## 本地配置

- `EPILOCATE_V2_DATABASE_URL`：生产环境使用 PostgreSQL 16 的 `postgresql+psycopg://` DSN。
- `EPILOCATE_V2_USER_TOKEN_HASHES`：JSON 映射，`auth_subject` → 用户 Bearer 的 SHA-256。User 行需由部署认证组件预配；凭据不写数据库。
- `EPILOCATE_V2_LEASE_SECRET`：不少于 32 字符的随机密钥。轮换前排空活跃租约。
- `EPILOCATE_V2_S3_BUCKET`、可选 `EPILOCATE_V2_S3_ENDPOINT`：私有、支持服务端 AES256 加密的 S3 存储。凭据使用标准 AWS 环境/实例身份。
- `DICOM_RETENTION_DAYS`：默认 7，允许 1–365。对象存储需同时配置对应生命周期删除规则；既有对象不会因新配置延长。

运行迁移：`EPILOCATE_V2_DATABASE_URL=... .venv/bin/alembic -c backend_v2/alembic.ini upgrade head`。

启动：`EPILOCATE_V2_DATABASE_URL=... .venv/bin/uvicorn backend_v2.api.app:app`。

Cloud 调度器独立进程：`.venv/bin/python -m backend_v2.workers.sweeper`。每 15 秒验证 CREATED、回收过期租约并清理到期原始 DICOM；不要在 API 进程中运行推理。生产部署应运行一个调度器副本，并配置存储生命周期规则作为清理兜底。

模型和 Worker 凭据须在部署时预配，Register 不能自行创建 Worker 身份或模型版本。`GET /api/v2/cases/{case_id}/dicom` 是保留期内的授权只读 DICOM 读取路径。`POST /workers/results` 是冻结契约路径；`POST /workers/jobs/{job_id}/result` 是本轮实现要求的同语义别名，路径中的 Job ID 必须与提交内容一致。

## Phase 2：接入 Worker v1

在 Backend 数据库执行迁移后，使用 `backend_v2.workers.provision` 预配节点。命令需要实际 PostgreSQL DSN 和 Worker 能访问的 HTTPS 域名；生成的 Bearer token 只写入权限为 `0600` 的本地 env 文件，不进入 Git 或数据库明文。输出的 `worker_id` 对应 `WORKER_ID`，冻结模型 hash 为 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`，`model_id=baseline_resnet18`。

```sh
EPILOCATE_V2_DATABASE_URL='postgresql+psycopg://...' .venv/bin/python -m backend_v2.workers.provision \
  --model-hash 548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734 \
  --preprocessing-version formal-resnet18-baseline-rule-b-v1 \
  --protocol-id stage1-occlusion-instability-v1 \
  --backend-url https://YOUR-BACKEND-HTTPS-ORIGIN \
  --frozen-root /READ-ONLY-FROZEN-ROOT \
  --data-root /PRIVATE-WORKER-DATA-ROOT \
  --output backend_v2/.local/worker.env
```

将 `worker.env` 安全地送达 Worker 主机，加载后在 Worker 仓库运行 `python -m worker`。节点先 Register、发空闲 Heartbeat，再 Claim；Claim 将 `QUEUED` 原子改为 `RUNNING`。运行中的 Heartbeat 续租。Worker 将完整数值结果与 PNG 图层一同提交；Backend 的 `inference_results.result_json` 长期保存原始 `positions/scale_summaries/cross_scale/prediction`，`asset_manifest` 保存每个资产的私有键、SHA-256、尺寸、坐标系、MIME 和大小。公开 Result API 通过 `/positions` 分页读取原始数值，通过 `/assets/{asset_id}` 授权读取 PNG；读取时复验资产大小和 SHA-256。

本地真实 Worker 联调测试：设置 `EPILOCATE_WORKER_ROOT`（批准的 SHA 为 `24d4fbf8674ce4f34070daebe006ea31ab13f647` 或 Phase 2 SHA `1f90321b7b6af9e2a69992c4259fd2dcf32944ed`）、`EPILOCATE_WORKER_PYTHON`（已安装冻结算法依赖的 Python）和 `EPILOCATE_FROZEN_ROOT`（只读冻结模型目录），运行 `.venv/bin/pytest -q backend_v2/tests/test_worker_v1_integration.py`。测试使用隔离的 SQLite 与内存对象存储，不写 Worker 工作区、不使用患者数据，也不代表 PostgreSQL/S3/公网 HTTPS 已验收。
