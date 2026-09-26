# EpiLocate Database Schema v1.0 Freeze

状态：**正式冻结版 v1.0，待最终确认后进入实现**。适用范围是 Backend v2 Cloud Control Plane；不迁移或改写 P0 SQLite、审核库、冻结科研产物。本设计基于 `EpiLocate_Database_Schema_v1.0.docx`、Backend API Contract v2.0、AI Worker Architecture v1.0、Deployment Architecture v1.0、2026-09-26 Design Freeze Review 和仓库 HEAD `021e4f56103e53c82b5abf76465f62fb4f1bc6c3`。上游只给出实体与原则；本文件固定字段、PostgreSQL 类型、约束和保留策略。

## 统一约定

- 数据库目标为 PostgreSQL 16。`UUID` 主键由服务端生成 UUIDv4；时间均为 `TIMESTAMPTZ`、UTC 存储；`TEXT` 枚举以 `CHECK` 约束固定；`JSONB` 只存受 Schema 校验的非 PHI 元数据。表名使用复数 snake_case。
- `—` 表示无默认值。下表的“索引/约束”列同时列出主键、唯一键、外键和普通索引；所有未注明的普通列均无单列索引。外键删除动作见“删除策略”。
- `public_id`/`anonymous_id` 为对外随机 128 位标识，带 `case_`、`pat_`、`slice_` 等类型前缀；与内部 UUID、患者信息、DICOM UID、文件名均无数学或可逆关系。客户端不得提交或选择这些 ID。
- 数据库不保存 DICOM 像素、患者姓名、PatientID、原始 Study/Series/SOP UID、原始文件名、明文 Worker token、checkpoint 文件或原始图层字节。`staging_object_key` 和资产清单是私有存储键，不作为公开 URL。云端原始 DICOM 仅存私有临时对象，默认 7 天后清理；云端不是长期 DICOM 存储。
- 第一阶段单 Slice：一次上传生成一个 Study、Series、Slice；关系允许后续多 Study/Series/Slice。一个 Patient 可有多个 Case；默认每个新 Case 创建一个新的匿名 Patient，跨 Case 关联必须由经授权的显式流程完成。

## 关系

`users 1:N patients`；`users 1:N cases`；`patients 1:N cases`；`cases 1:N studies`；`studies 1:N series`；`series 1:N slices`；`cases 1:N inference_jobs`；`inference_jobs 1:0..1 inference_results`；`worker_nodes 1:N job_attempts`；`model_versions 1:N inference_jobs`。`experiments` 是研究元数据容器，不让实验记录自动变成在线结果。

### users — User

| 字段 | PostgreSQL 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK |
| auth_subject | VARCHAR(255) | 否 | — | UNIQUE；认证系统的不可变主体标识 |
| role | TEXT | 否 | `'USER'` | CHECK `USER,ADMIN` |
| is_active | BOOLEAN | 否 | `TRUE` | — |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| updated_at | TIMESTAMPTZ | 否 | `now()` | — |

不在本表存密码或邮箱；身份凭据由部署的认证组件管理。`auth_subject` 不得包含邮箱或姓名。`role` 不代表医院多租户授权，v1 只有所有者与管理员。

### patients — Patient

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, owner_user_id)` |
| owner_user_id | UUID | 否 | — | FK → `users.id`；INDEX |
| anonymous_id | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE `(owner_user_id, anonymous_id)` |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| retention_until | TIMESTAMPTZ | 是 | `NULL` | INDEX；仅在单独批准的保留策略下赋值 |

### cases — Case

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, owner_user_id)` |
| owner_user_id | UUID | 否 | — | FK → `users.id`；INDEX `(owner_user_id, created_at DESC)` |
| patient_id | UUID | 否 | — | 复合 FK `(patient_id, owner_user_id)` → `patients(id, owner_user_id)`；INDEX |
| anonymous_id | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE；INDEX `cases(anonymous_id)` |
| status | TEXT | 否 | `'CREATED'` | CHECK `CREATED,READY,EXPIRED,DELETING` |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| updated_at | TIMESTAMPTZ | 否 | `now()` | — |
| retention_until | TIMESTAMPTZ | 是 | `NULL` | INDEX；结果关联元数据默认长期保存 |
| deletion_requested_at | TIMESTAMPTZ | 是 | `NULL` | INDEX；清理流程的墓碑时间 |

`READY` 只表示有合格输入可提交任务，不表示模型结果已完成。

### studies — Study

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, case_id)` |
| case_id | UUID | 否 | — | FK → `cases.id`；INDEX |
| study_ref | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE `(case_id, study_ref)` |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |

### series — Series

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, case_id)` |
| study_id | UUID | 否 | — | 复合 FK `(study_id, case_id)` → `studies(id, case_id)`；INDEX |
| case_id | UUID | 否 | — | FK → `cases.id`；INDEX |
| series_ref | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE `(study_id, series_ref)` |
| modality | TEXT | 否 | `'CT'` | CHECK `modality='CT'`，扩展需迁移 |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |

### slices — Slice

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, case_id)` |
| series_id | UUID | 否 | — | 复合 FK `(series_id, case_id)` → `series(id, case_id)`；INDEX |
| case_id | UUID | 否 | — | FK → `cases.id`；INDEX |
| slice_ref | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE `(case_id, slice_ref)` |
| ordinal | INTEGER | 否 | — | CHECK `ordinal >= 0`；UNIQUE `(series_id, ordinal)` |
| width_px | INTEGER | 否 | — | CHECK `width_px > 0` |
| height_px | INTEGER | 否 | — | CHECK `height_px > 0` |
| source_sha256 | CHAR(64) | 否 | — | 输入完整性校验；不对外返回 |
| staging_object_key | TEXT | 是 | `NULL` | 私有临时对象键；不得含患者名/原文件名 |
| staging_expires_at | TIMESTAMPTZ | 是 | 上传时按配置设为当前时间 +7 天 | INDEX；清除后置空 |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |

### model_versions — ModelVersion

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK |
| model_id | VARCHAR(96) | 否 | — | UNIQUE `(model_id, version)` |
| version | VARCHAR(96) | 否 | — | — |
| checkpoint_sha256 | CHAR(64) | 否 | — | CHECK 64 位十六进制；INDEX |
| preprocessing_version | VARCHAR(128) | 否 | — | — |
| protocol_id | VARCHAR(128) | 否 | — | — |
| lifecycle_state | TEXT | 否 | `'ACTIVE'` | CHECK `ACTIVE,RETIRED` |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |

记录 checkpoint 的不可变内容哈希；云端不保存权重。已被 Job 引用的行不得修改上述版本字段。

### worker_nodes — WorkerNode

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK |
| node_id | VARCHAR(64) | 否 | 管理员预配的随机 ID | UNIQUE；INDEX `worker_nodes(node_id)` |
| token_hash | CHAR(64) | 否 | 管理员预配 | UNIQUE；只存 token SHA-256 |
| display_name | VARCHAR(96) | 否 | — | 不含个人或设备序列号 |
| supported_models | JSONB | 否 | `'[]'::jsonb` | 只允许已注册 model_id + checkpoint SHA |
| activity_state | TEXT | 否 | `'IDLE'` | CHECK `IDLE,RUNNING,ERROR` |
| registered_at | TIMESTAMPTZ | 是 | `NULL` | — |
| last_heartbeat_at | TIMESTAMPTZ | 是 | `NULL` | INDEX |
| disabled_at | TIMESTAMPTZ | 是 | `NULL` | — |
| updated_at | TIMESTAMPTZ | 否 | `now()` | — |

`ONLINE/OFFLINE` 由 `disabled_at` 和 `last_heartbeat_at` 派生，不与 `activity_state` 混成一个字段。`BUSY` 是旧 Worker 文档对 `RUNNING` 的描述，不进入 v1 数据库枚举。Worker 协议的 `worker_id` 映射 `node_id`，`supported_model_versions` 映射 `supported_models`；这些映射必须单一实现，不能产生两套身份或能力记录。Bearer token 为高熵随机值，SHA-256 仅用于查找/比对，比较必须为恒时操作。

### experiments — Experiment

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK |
| public_id | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE |
| owner_user_id | UUID | 否 | — | FK → `users.id`；INDEX |
| name | VARCHAR(120) | 否 | — | 不含患者信息 |
| protocol_id | VARCHAR(128) | 否 | — | — |
| status | TEXT | 否 | `'DRAFT'` | CHECK `DRAFT,FROZEN,ARCHIVED` |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| retention_until | TIMESTAMPTZ | 是 | `NULL` | INDEX；实验元数据默认长期保存 |

此表只为已有 Schema v1.0 的 `experiments` 留结构；v2 第一批路由不暴露实验写入，也不触碰 sealed test 或冻结 validation。

### inference_jobs — InferenceJob

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；UNIQUE `(id, case_id)` |
| public_id | VARCHAR(48) | 否 | 服务端随机生成 | UNIQUE |
| case_id | UUID | 否 | — | FK → `cases.id`；复合 FK `(case_id, requested_by_user_id)` → `cases(id, owner_user_id)`；INDEX |
| slice_id | UUID | 否 | — | 复合 FK `(slice_id, case_id)` → `slices(id, case_id)`；INDEX |
| requested_by_user_id | UUID | 否 | — | FK → `users.id` |
| model_version_id | UUID | 否 | — | FK → `model_versions.id`；INDEX |
| experiment_id | UUID | 是 | `NULL` | FK → `experiments.id` |
| kind | TEXT | 否 | — | CHECK `PREDICTION,OCCLUSION` |
| status | TEXT | 否 | `'CREATED'` | CHECK `CREATED,QUEUED,RUNNING,COMPLETED,FAILED`；INDEX `(status, next_attempt_at, created_at)` |
| request_json | JSONB | 否 | — | 白名单参数，含 protocol/scales，不含路径或 PHI |
| request_digest | CHAR(64) | 否 | — | 标准化请求 + model/protocol/preprocessing SHA-256 |
| idempotency_key | VARCHAR(128) | 否 | — | UNIQUE `(requested_by_user_id, idempotency_key)` |
| attempt_no | SMALLINT | 否 | `0` | CHECK `0 <= attempt_no <= max_attempts` |
| retry_count | SMALLINT | 否 | `0` | CHECK `0 <= retry_count <= 2`；已领取的重试次数 |
| max_attempts | SMALLINT | 否 | `3` | CHECK `1 <= max_attempts <= 3` |
| next_attempt_at | TIMESTAMPTZ | 否 | `now()` | 调度索引的一部分 |
| worker_node_id | UUID | 是 | `NULL` | FK → `worker_nodes.id`；INDEX |
| lease_expire_time | TIMESTAMPTZ | 是 | `NULL` | 当前 Attempt 租约到期时间；INDEX |
| last_heartbeat | TIMESTAMPTZ | 是 | `NULL` | 当前 Attempt 最近一次通过验证的心跳时间 |
| failure_reason | VARCHAR(64) | 是 | `NULL` | 稳定、脱敏的终态失败码 |
| error_message | VARCHAR(256) | 是 | `NULL` | 脱敏消息 |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| queued_at | TIMESTAMPTZ | 是 | `NULL` | — |
| started_at | TIMESTAMPTZ | 是 | `NULL` | — |
| finished_at | TIMESTAMPTZ | 是 | `NULL` | — |
| updated_at | TIMESTAMPTZ | 否 | `now()` | — |

`attempt_no` 是已领取次数，首次为 1；`retry_count=max(attempt_no-1,0)`，最大 **2 次重试 / 3 次总领取**，在领取事务内同步更新。`lease_expire_time` 与当前 `job_attempts` 的同名字段在领取及成功续租事务中同步；非 RUNNING 时置空。`last_heartbeat` 仅在当前 Attempt 的身份与 lease token 校验成功后更新，重新排队时置空。`failure_reason` 只在终态 `FAILED` 写入稳定错误码，尝试级失败留在 `job_attempts`。相同用户同一幂等键、相同摘要返回原 Job；摘要不同返回 409。唯一键不自动过期，以免旧键在数据保留期内指向另一个任务。

### job_attempts — Worker 执行租约（为可靠重试补充）

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；对外作为 `attempt_id` |
| job_id | UUID | 否 | — | FK → `inference_jobs.id`；UNIQUE `(job_id, attempt_no)` |
| attempt_no | SMALLINT | 否 | — | CHECK `attempt_no >= 1` |
| worker_node_id | UUID | 否 | — | FK → `worker_nodes.id`；INDEX |
| claim_key | UUID | 否 | — | UNIQUE `(worker_node_id, claim_key)`；领取请求的幂等键 |
| claim_request_digest | CHAR(64) | 否 | — | 规范化 Claim 请求摘要；同键异请求返回 409 |
| lease_token_hash | CHAR(64) | 否 | — | 每次领取生成；明文不落库 |
| leased_at | TIMESTAMPTZ | 否 | `now()` | — |
| lease_expire_time | TIMESTAMPTZ | 否 | — | INDEX `(outcome, lease_expire_time)` |
| last_heartbeat | TIMESTAMPTZ | 是 | `NULL` | 最近一次有效续租时间 |
| finished_at | TIMESTAMPTZ | 是 | `NULL` | — |
| outcome | TEXT | 否 | `'CLAIMED'` | CHECK `CLAIMED,SUCCEEDED,FAILED,EXPIRED`；同一 `job_id` 至多一个 `CLAIMED` 的部分 UNIQUE 索引 |
| failure_reason | VARCHAR(64) | 是 | `NULL` | 该次尝试的稳定、脱敏失败码 |
| submission_digest | CHAR(64) | 是 | `NULL` | 首次结果提交的摘要 |
| accepted_response_json | JSONB | 是 | `NULL` | 重复提交时原样返回的脱敏响应 |

### inference_results — InferenceResult

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK；对外 `result_id` 为带前缀的此随机 UUID 编码 |
| job_id | UUID | 否 | — | UNIQUE；复合 FK `(job_id, case_id)` → `inference_jobs(id, case_id)` |
| case_id | UUID | 否 | — | FK → `cases.id`；INDEX `inference_results(case_id)` |
| accepted_attempt_id | UUID | 否 | — | FK → `job_attempts.id`；UNIQUE |
| model_version_id | UUID | 否 | — | FK → `model_versions.id` |
| source | TEXT | 否 | `'LIVE_CASE'` | CHECK `source='LIVE_CASE'`；Mock/冻结统计不混入此表 |
| result_json | JSONB | 否 | — | 版本化、白名单结果，不含 PHI 或原始像素 |
| asset_manifest | JSONB | 否 | `'[]'::jsonb` | 私有对象键、MIME、大小、SHA-256；不含公开 URL |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| retention_until | TIMESTAMPTZ | 是 | `NULL` | INDEX；默认长期保存，不按 DICOM TTL 清理 |

提交事务须校验 Job、Attempt、Case、ModelVersion 四者一致；仅 `COMPLETED` Job 可见结果。结果 JSON 和资产在同一接收流程校验后发布，失败时不可出现“完成 Job 但缺图层”。

### api_idempotency — Case 与上传请求的幂等记录（为 API v2 补充）

| 字段 | 类型 | Nullable | 默认值 | 索引/约束 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | `gen_random_uuid()` | PK |
| actor_user_id | UUID | 否 | — | FK → `users.id`；INDEX |
| scope | TEXT | 否 | — | CHECK `CASE_CREATE,CASE_UPLOAD` |
| idempotency_key | VARCHAR(128) | 否 | — | UNIQUE `(actor_user_id, scope, idempotency_key)` |
| request_digest | CHAR(64) | 否 | — | — |
| state | TEXT | 否 | `'PENDING'` | CHECK `PENDING,COMPLETE` |
| response_status | SMALLINT | 是 | `NULL` | — |
| response_json | JSONB | 是 | `NULL` | 不含临时签名 URL |
| created_at | TIMESTAMPTZ | 否 | `now()` | — |
| expires_at | TIMESTAMPTZ | 是 | `NULL` | INDEX；关联实体受控删除后设为删除时间 +24 小时 |

同键同摘要已完成时重放响应；同键不同摘要或未完成占位返回 409。过期占位只能由审计过的恢复任务处理，不能静默重做上传。

## 删除、保留与匿名策略

1. 外键默认 `ON DELETE RESTRICT`。仅层级元数据 `studies → series → slices` 可在受控 Case 删除事务中 `ON DELETE CASCADE`；`users → patients/cases`、`cases → jobs/results`、`workers/model_versions → attempts/jobs/results` 均 `RESTRICT`。停用用户、Worker、模型优先软禁用；不能通过删除父行抹去来源。
2. 删除 Case：先拒绝存在 `CREATED/QUEUED/RUNNING` Job 的请求；将 Case 原子标为 `DELETING` 并写 `deletion_requested_at`，立即禁止新派单和用户读取，再撤销输入签名、按对象清单幂等删除私有原始对象及结果资产。只有外部对象确认清除后，才删除结果、Attempt、Job、Slice 层级，最后删除 Case。任何步骤失败均保留墓碑并重试，不报告删除成功。Patient 无剩余 Case 时可删除；User 删除需先完成所拥有 Case 的受控删除。数据库与对象存储使用同一清单核对。
3. **Original DICOM**：云端私有对象临时保存，默认上传后 **7 天**到期；部署参数 `DICOM_RETENTION_DAYS` 可配置为有限的正整数天，变更需记录生效时间，既有对象保持上传时写入的 `staging_expires_at`，不得隐式延长。到期清除原始对象并置空 `staging_object_key/staging_expires_at`；尚未领取的 Job 进入 `FAILED INPUT_EXPIRED`，不再发起重试。已下载输入且租约有效的 RUNNING Attempt 可完成，但不能重新下载过期对象；其后失败则直接 `FAILED INPUT_EXPIRED`。云端不作为长期 DICOM 存储，备份也不得延长原始 DICOM 的有效期。
4. **Inference Result**：结果 JSON、图层资产、Job 与保持解释所需的匿名 Case/Patient/Study/Series/Slice 元数据默认长期保存，`retention_until=NULL` 表示无自动 TTL；仅在经批准的删除请求或另行批准的保留政策到期时通过受控流程删除。长期保存不等于永久不可删除，也不授予对原始 DICOM 的长期访问。`experiments` 元数据同样默认无自动 TTL。`api_idempotency` 至少保留对应实体生命周期，删除实体后再保留 24 小时；Worker 心跳仅保留最新时间。运行日志默认 30 天，备份默认 30 天，均不得含 PHI、token 或原始影像。
5. **Worker Cache**：原始输入、解码像素及中间图层只在 Worker 临时目录存在；推理结束且结果提交得到 Backend 接受后立即清理，失败或租约失效也立即清理。异常退出后的残留由 Worker 启动清理器在 24 小时内删除，不能作为可重试任务的权威输入。
6. 公共 ID 用加密安全随机源生成并在唯一冲突时重试。仅所有者可按 Case/Patient ID 访问，管理员操作须单独审计；仅知道 ID 不构成权限。Worker 只收到当前租约所需的匿名引用和限时输入地址。不会把 Mock、在线真实结果或冻结验证统计合并为同一来源。

## 迁移边界

P0 `gradio_service/gradio_debug/storage.py` 的五表 SQLite 与本设计不同；不做原地 `ALTER` 或隐式数据导入。v2 首个迁移应从空 PostgreSQL 建表、装载经核验的 `model_versions` 和预配 Worker；P0 数据迁移需另出映射、脱敏、双向核对和回滚方案。保留现有冻结模型/协议哈希与 sealed test 边界。
