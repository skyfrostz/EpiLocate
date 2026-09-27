# Backend v2 Production Foundation

独立 FastAPI 入口：`backend_v2.api.app:app`。P0 `gradio_service` 未修改；部署时由反向代理将 `/api/v2` 指向此应用，旧入口保持原服务。

## 本地配置

- `EPILOCATE_V2_DATABASE_URL`：生产环境使用 PostgreSQL 16 的 `postgresql+psycopg://` DSN。
- `EPILOCATE_V2_USER_TOKEN_HASHES`：JSON 映射，`auth_subject` → 用户 Bearer 的 SHA-256。User 行需由部署认证组件预配；凭据不写数据库。
- `EPILOCATE_V2_LEASE_SECRET`：不少于 32 字符的随机密钥。轮换前排空活跃租约。
- `EPILOCATE_V2_S3_BUCKET`、可选 `EPILOCATE_V2_S3_ENDPOINT`：私有、支持服务端 AES256 加密的 S3 存储。凭据使用标准 AWS 环境/实例身份。
- `DICOM_RETENTION_DAYS`：默认 7，允许 1–365。对象存储需同时配置对应生命周期删除规则；既有对象不会因新配置延长。

运行迁移：`EPILOCATE_V2_DATABASE_URL=... .venv/bin/alembic -c backend_v2/alembic.ini upgrade head`。

迁移验证：`EPILOCATE_V2_DATABASE_URL=... .venv/bin/python -m backend_v2.scripts.validate_migrations`。验证会升级到 Alembic head，并检查 PostgreSQL／SQLite 所需的 13 张核心表，包含 `assets`（另有 Schema 中的 `experiments` 表）。初始 revision 固定旧表结构；结果 metadata 和 Asset 表由 `0002_result_metadata_and_assets` 添加，后续 migration 不会修改旧 revision 的 metadata。

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

本地真实 Worker 联调测试：设置 `EPILOCATE_WORKER_ROOT`（当前 HEAD 必须从固定基线 `24d4fbf8674ce4f34070daebe006ea31ab13f647` 派生）、`EPILOCATE_WORKER_PYTHON`（已安装冻结算法依赖的 Python）和 `EPILOCATE_FROZEN_ROOT`（只读冻结模型目录），运行 `.venv/bin/pytest -q backend_v2/tests/test_worker_v1_integration.py`。测试使用隔离的 SQLite 与内存对象存储，不写 Worker 工作区、不使用患者数据，也不代表 PostgreSQL/S3/公网 HTTPS 已验收。

## PostgreSQL + MinIO production-like 环境

复制 `backend_v2/.example.env` 到部署系统的 secret/config 管理器；不要依赖未提交的 `.env.local`。`VITE_API_BASE_URL` 只进入 Frontend 构建环境，Worker token、租约密钥和 S3 secret 不能进入浏览器。

本地启动 PostgreSQL 16、私有 MinIO bucket 和输入对象 7 天 lifecycle：

```sh
docker compose -f backend_v2/docker-compose.production-like.yml up -d
set -a; . backend_v2/.example.env; set +a
EPILOCATE_V2_DATABASE_URL='postgresql+psycopg://epilocate:change-me@127.0.0.1:55432/epilocate' \
EPILOCATE_V2_S3_ENDPOINT='http://127.0.0.1:59000' \
EPILOCATE_V2_S3_ACCESS_KEY='change-me' \
EPILOCATE_V2_S3_SECRET_KEY='change-me-change-me' \
.venv/bin/python -m backend_v2.scripts.validate_migrations
```

再运行 `EPILOCATE_V2_PRODUCTION_DATABASE_URL` 与 MinIO 变量已设置的 `.venv/bin/pytest -q -m production_like backend_v2/tests/test_production_like.py`，它会验证 schema、上传、读取、删除对象。Compose 的 MinIO bucket 保持 private；Backend 只在通过 Case/Result/Asset 所有权校验后签发不超过 5 分钟的 Result `asset_url`，同时保留代理读取端点。Frontend 可把 `asset_url` 交给浏览器加载，不能拼接 bucket URL。原始 DICOM 的 7 天清理不影响结果 JSON 或 heatmap asset。

只验证对象存储链路可运行：`set -a; . backend_v2/.example.env; set +a; .venv/bin/python -m backend_v2.scripts.validate_storage`。该命令只上传随机测试字节，读取并校验 SHA-256，生成最长 5 分钟的 SigV4 URL，最后删除对象；不会上传 DICOM 或推理结果。

真实 Browser → Backend → MinIO 验收还需要 HTTPS 反向代理把 `EPILOCATE_V2_S3_ENDPOINT` 留在服务端，并把 `EPILOCATE_V2_S3_PUBLIC_ENDPOINT` 指向浏览器可达的 HTTPS MinIO/S3 域名；浏览器不直接持有 S3 凭据。Frontend 使用 `VITE_API_BASE_URL` 查询 Result 和 asset route，不能拼接 bucket URL。
