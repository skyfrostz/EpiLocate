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

模型和 Worker 凭据须在部署时预配，Register 不能自行创建 Worker 身份或模型版本。`POST /workers/results` 是冻结契约路径；`POST /workers/jobs/{job_id}/result` 是本轮实现要求的同语义别名，路径中的 Job ID 必须与提交内容一致。
