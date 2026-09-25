# EpiLocate P0 后端集成报告（2026-09-26）

## 范围与版本

- 分支：`feat/p0-backend-real`；独立 worktree：`infectious-ct-ai-p0-backend-real`。
- 冻结开发基线：`3b3c270869663293769f99ab3cbc180904185a1f`。
- 后端实现提交：`3b400c39437ec6685b5f056fb039f9dcfe0bedb6`。
- 本报告仅说明该分支的后端行为与本机测试；不代表统一集成或独立 QA 通过。未合并 `main`。

## 实际 API 与状态

| 方法 | 路径 | 当前状态 |
| --- | --- | --- |
| GET | `/api/health`, `/api/v1/capabilities`, `/api/v1/contract` | 可用；能力由冻结模型实际可加载性决定，旧契约入口保持 v0.1 |
| POST | `/api/v1/cases` | 可用；仅一个已去标识 CT DICOM，解析后返回匿名 ID 与解析 job |
| GET | `/api/v1/cases/{case_id}`, `/api/v1/cases/{case_id}/slices`, `/api/v1/slices/{slice_id}/preview` | 可用；单切片、白名单几何和原图 PNG |
| POST | `/api/v1/predictions`, `/api/v1/jobs/occlusion` | 可用；冻结 Baseline 分类与 16/32/64 遮挡，后台单工作线程运行 |
| GET | `/api/v1/jobs/{job_id}`, `/api/v1/jobs/{job_id}/result` | 可用；v1 状态 `PENDING/RUNNING/COMPLETED/FAILED/CANCELLED` |
| POST | `/api/v1/jobs/{job_id}/cancel` | 仅队列中、未开始的 v1 分析任务可安全取消；运行中或已完成返回 409 |
| GET | `/api/v1/occlusion-results/{result_id}/positions`, `/api/v1/assets/{asset_id}?result_id=...` | 可用；分页和图层，结果须属于已完成 job 与对应 case/slice |
| POST | `/api/v1/jobs/inference` | 原 PNG/JPG Mock 兼容入口；`source=MOCK`，保持 v0.1 小写状态；`APP_MODE=real` 未接入该旧入口时返回 503 |
| POST | `/api/v1/comparisons`, `/api/v1/jobs/coarse-localization`, `/api/v1/jobs/lime`, `/api/v1/feedback` | 501 `NOT_IMPLEMENTED` |

NIfTI、多切片、患者级汇总、Robust、稳定粗定位、LIME、医生反馈和冻结 validation 摘要均未开放为可用能力。真实分析结果为 `source=LIVE_CASE`；合成向量概率只作该 fixture 的核验值，不用于其他病例响应。

## 本轮改动

| 文件 | 作用 |
| --- | --- |
| `gradio_service/gradio_debug/app.py` | loopback 或可配置 Bearer 访问边界、v1 取消接口、幂等占位接线、能力状态 |
| `gradio_service/gradio_debug/storage.py` | SQLite 原子幂等占位与释放、已完成结果的 case/slice/job 归属校验 |
| `gradio_service/gradio_debug/jobs.py`, `contracts.py` | 队列任务安全取消和 `CANCELLED` 状态；继续复用现有单线程后台执行 |
| `gradio_service/tests/test_api.py`, `test_real_integration.py`, `test_backend_boundaries.py` | 模型不可用、Schema、能力、资产边界、跨实例幂等、取消、失败脱敏与令牌测试 |
| `docs/interfaces/p0_backend_contract_diff.md` | 修改前的契约差异记录 |

`algorithm/service.py`、冻结协议/配置/checkpoint、正式 validation 结果与共享 OpenAPI Schema 均未修改。模型由 `FrozenBaseline` 的进程内锁和缓存统一加载；不存在请求级重复 checkpoint 加载或 Mock 自动降级。

## 启动与隔离

在后端 worktree 执行；`EPILOCATE_FROZEN_ROOT` 指向只读的冻结实验根目录，`APP_DATA_ROOT` 使用本会话独立的可写目录。已验证端口为 `8893`，仅绑定 loopback，单 Uvicorn worker。

```sh
cd /Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0-backend-real
export EPILOCATE_FROZEN_ROOT=/path/to/read-only/frozen-experiment-root
export APP_DATA_ROOT=/tmp/epilocate-p0-backend-real-http-20260926
export APP_MODE=mock
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
PYTHONPATH=.:gradio_service python -m uvicorn gradio_service.gradio_debug.app:app --host 127.0.0.1 --port 8893 --workers 1
```

本机 HTTP/Gradio 测试时未设置 `EPILOCATE_API_TOKEN`，因而仅允许 loopback 访问影像相关 API 与 Gradio。若设置该变量，请求需携带 `Authorization: Bearer <token>`；缺失或错误时统一返回 401 `UNAUTHENTICATED`。服务端密钥不得下发给浏览器。当前 Gradio 普通浏览器导航不能附加此头，因此令牌模式下 Gradio 页面会返回 401；需要集成层在服务端完成认证/转发。`/api/v1/capabilities` 与 `/api/v1/contract` 可公开读取。此前端联调基础地址为 `http://127.0.0.1:8893`，实际集成端口以集成负责人配置为准。

## 测试证据

- 原有 21 项与新增 4 项：`25 passed, 7 warnings`（警告为 Starlette/httpx 和 jsonschema 旧解析器弃用提示）。运行命令：`PYTHONPATH=.:gradio_service python -m pytest -q -p no:cacheprovider gradio_service/tests /path/to/original/tests/test_occlusion_runner.py`；本机使用该算法分支现有 `.venv-p0` 解释器只读运行，并将上传、日志、Job SQLite、pytest 临时文件置于本任务独立 `/tmp` 根。
- 独立端口 `8893` 上运行 `scripts/smoke_p0_http_gradio.py`：`PASS`。synthetic DICOM SHA-256 为 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`；HTTP/Gradio 均返回 `LIVE_CASE`，正类概率 `0.025618407875299454`，两入口绝对误差 `0`；三尺度位置数 `729/169/36`，预览 `112×80`，响应资产 `224×224`。
- 测试未读取 formal test 像素，未运行训练、Robust、LIME、Grad-CAM 或 MPS 长任务。

## 契约差异、前端与算法依赖

详见 `p0_backend_contract_diff.md`。既有字段、类型、null 语义、错误码与共享 `algorithm_api_contract.yaml` 未更改。新增的能力键为向后兼容扩展；前端仍须只启用状态为 `available` 的功能。

前端需按 v1 大写 Job 状态轮询真实任务，从 `/result` 取得结果，从位置分页取得定量数值；PNG 热图仅用于显示。v0.1 Mock 入口仍采用小写状态并返回 `source=MOCK`。401 应提示认证状态并停止重试；不得在浏览器包内放置服务端令牌。使用外网入口前，集成层还需完成用户身份、逐对象授权和服务端令牌转发。

算法依赖是只读冻结 checkpoint、协议与配置的完整哈希校验，以及现有 `FrozenBaseline` 预处理、分类、遮挡与空间结果。后端不定义 `candidate_response` 或坐标映射语义，也没有第二套推理实现。

## 未解决问题

- 当前仅有部署级 Bearer 或 loopback 边界，没有多用户逐对象 ACL；不能接收真实临床数据或公开部署。
- 在线上传和结果缺少保留期限与清理策略；服务重启将排队/运行任务标记失败，未实现断点恢复。
- 幂等键在进程异常退出且响应尚未登记时可能保留 pending 占位；不会重复执行，但需要运维级恢复流程。
- 运行中的遮挡不能安全中断；进度只有排队、执行、完成三段，尚无算法内部细粒度进度。
- 令牌模式的 Gradio 浏览器访问尚需受控代理；前端 API Client 对令牌的完整适配由集成方协调。
- 冻结 validation 摘要、NIfTI、多切片、患者级汇总及 P1/P2 模块未实现。完整 P0 仍待统一集成和独立 QA。
