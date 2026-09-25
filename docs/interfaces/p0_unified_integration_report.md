# EpiLocate P0 统一集成报告

日期：2026-09-26。状态：**P0 UNIFIED INTEGRATION READY FOR INDEPENDENT QA**。本报告记录集成方的本机验证；`EPILOCATE P0 REAL INTEGRATION QA PASSED` 仍须由独立 QA 针对最终固定提交复验后判定。

## 固定基线与提交

| 角色 | 提交 |
| --- | --- |
| 统一开发基线 `codex/p0-real-algorithm` | `3b3c270869663293769f99ab3cbc180904185a1f` |
| 后端代码 | `3b400c39437ec6685b5f056fb039f9dcfe0bedb6` |
| 后端报告 | `3aabb79803b318229740ec899c1eca524b1c1184` |
| 前端代码 | `93d2e8f013d64979972bc88e7cbdba71007ca6b7` |
| QA 代码与旧基线证据 | `7366dd3cf4dbc030864c230817ba52604e348cdf` |
| 已测试的统一集成代码 | `a15159768fc621b9fe606b08427cc08581d6c4ac` |
| 固定交付点 | 本报告所在的 `p0/integration` HEAD；独立 QA 应使用交付消息中的完整 SHA，而非移动分支名 |

从指定基线创建独立工作树 `/Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0-integration`，依次以 `--no-ff` 合并后端、前端、QA 分支，再提交集成修正。三个 Git 合并均无文本冲突，原分支和原工作树未修改；原始 `main` 有既存未提交内容，未参与集成。没有合并 `main`、强制推送、重置或清理其他工作树。

QA 分支原有的 31 PASS/1 FAIL 针对固定开发基线；唯一 FAIL 是无认证的热图资产读取。它不是本轮统一代码的验收结果。修正后的受保护模式资产边界见下方重新执行的 HTTP 证据。

## 接口与兼容性处理

现行真实 API：`GET /api/health`、`GET /api/v1/capabilities`、`POST /api/v1/cases`、`GET /api/v1/cases/{case_id}`、`GET /api/v1/cases/{case_id}/slices`、`GET /api/v1/slices/{slice_id}/preview`、`POST /api/v1/predictions`、`POST /api/v1/jobs/occlusion`、`GET /api/v1/jobs/{job_id}`、`GET /api/v1/jobs/{job_id}/result`、`GET /api/v1/occlusion-results/{result_id}/positions`、`GET /api/v1/assets/{asset_id}?result_id=...`。旧 `POST /api/v1/jobs/inference` 保留 PNG/JPG Mock。队列中尚未运行的真实分析任务可经 `POST /api/v1/jobs/{job_id}/cancel` 取消；运行中/已完成返回 409，前端未提供真实取消按钮。其他保留模块继续返回 501。

真实 Job 状态统一为 `PENDING/RUNNING/COMPLETED/FAILED/CANCELLED`。上传的 HTTP 202 与 `status=PENDING` 仅表示接受请求；本版同步解析产生的 `CASE_PARSE` Job 和病例预处理状态另行报告 `COMPLETED`，前端不会因上传响应为 `PENDING` 持续等待。前端只在真实 Job `COMPLETED` 后查询结果；浏览器刷新后通过保存的匿名 case/slice/job ID 重查。真实 DICOM 为 `source=LIVE_CASE`；旧 PNG/JPG 为 `source=MOCK`，真实错误没有 Mock 降级。

`P0Client` 在 Gradio Python 服务端读取 `EPILOCATE_API_BASE_URL` 与 `EPILOCATE_API_BEARER_TOKEN`，每次受保护请求以 Authorization 头发送；401/403 形成脱敏的 `AUTH_REQUIRED/ACCESS_DENIED` 页面错误。集成运行显式指定 API 地址，端口 8877 并非唯一地址。浏览器配置与响应不含服务端 Bearer 值；实测登录后 `/gradio/config` 也不含 Bearer 值或 UI 密码。

固定后端服务的 `/gradio` 在 Token 模式仍要求 Bearer，普通浏览器不能直接导航。集成增加独立本机 `ui_server.py`：它不加载模型、不建算法 Job，只运行真实 DICOM Gradio 页；页面以独立登录密码保护，Python 回调用服务端 Bearer 调用受保护 API。API 进程与 UI 进程使用不同端口及数据目录，只有 API 进程加载冻结模型。该 UI 是本机原型，**没有多用户逐对象授权**。

后端 Gradio 的 `allowed_paths` 不再包括结果目录，并显式封锁上传与结果目录。旧 Mock 下载改为从结果文件复制到该进程独立临时目录，以维持下载功能。前述为合并后发现的语义兼容与文件路由问题，均以最小范围修改，未覆盖任一开发分支文件。

本轮新增/修改文件：`gradio_service/gradio_debug/app.py`、`ui.py`、`ui_server.py`、`gradio_service/tests/test_backend_boundaries.py`、`qa/probe_http.py`、本报告和 `qa/evidence/p0_unified/`。三个开发分支的其他文件按原提交保留。`algorithm/service.py`、冻结协议/配置/checkpoint 与正式 validation 输出未修改。

## 启动与配置

以下是本轮验证过的双进程 Token 模式。使用两个终端和相同的服务端 Bearer 值；示例密码须由运行者另行设置，不应写入仓库或浏览器代码。两进程仅绑定 `127.0.0.1`，工作目录均为集成工作树。

```sh
cd /Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0-integration
export PYTHONPATH=.:gradio_service
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
export APP_MODE=real
export APP_DATA_ROOT=/tmp/epilocate-p0-unified-api
export EPILOCATE_FROZEN_ROOT=/Users/skyfrost/Documents/Techniques/infectious-ct-ai
export EPILOCATE_API_TOKEN='<server-side-bearer>'
/Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0/.venv-p0/bin/python -m uvicorn gradio_service.gradio_debug.app:app --host 127.0.0.1 --port 8897 --workers 1
```

```sh
cd /Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0-integration
export PYTHONPATH=.:gradio_service
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
export APP_DATA_ROOT=/tmp/epilocate-p0-unified-ui
export EPILOCATE_API_BASE_URL=http://127.0.0.1:8897
export EPILOCATE_API_BEARER_TOKEN='<same-server-side-bearer>'
export EPILOCATE_UI_PASSWORD='<separate-local-ui-password>'
/Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0/.venv-p0/bin/python -m uvicorn gradio_service.gradio_debug.ui_server:app --host 127.0.0.1 --port 8898 --workers 1
```

浏览器打开 `http://127.0.0.1:8898/gradio/`，使用本机 UI 用户 `local` 和所设 UI 密码。API base URL 仅在 UI 进程设置；若 API 端口变化，更新 `EPILOCATE_API_BASE_URL`。无 Token 本机模式可只启动 `gradio_service.gradio_debug.app:app` 于独立端口（本轮为 8896），不设置 `EPILOCATE_API_TOKEN`，并将 `EPILOCATE_API_BASE_URL` 指向该端口。所有本轮运行目录位于独立 `/tmp/epilocate-p0-unified-integration-20260926/` 根下，上传、SQLite、临时文件、日志和证据未落入冻结科研目录。实际推理使用现有 CPU 路径，未竞争 MPS 长实验；本轮启动的服务均已停止。

## 实际验证结果

| 检查 | 本轮结果与证据 |
| --- | --- |
| 原有仓库测试 | 41 passed、1 warning；随后统一命令重跑所有测试为 **82 passed、7 warnings**，见 [`unified_pytest.txt`](../../qa/evidence/p0_unified/unified_pytest.txt) |
| 固定代码 HTTP 探针 | 无 Token 32 PASS/0 FAIL；Token 32 PASS/0 FAIL，均在 `a15159768fc621b9fe606b08427cc08581d6c4ac` 上执行，见 [`fixed_no_token_http_probe.json`](../../qa/evidence/p0_unified/fixed_no_token_http_probe.json) 与 [`fixed_token_http_probe.json`](../../qa/evidence/p0_unified/fixed_token_http_probe.json) |
| Synthetic DICOM、分类及遮挡 | 上传 202；CASE_PARSE 与分类/遮挡 Job 完成；`LIVE_CASE` 正类概率 `0.025618407875299454`，符合原 fixture 的 `1e-6` 容差；16/32/64 px 为 729/169/36 位置，qg 取原预测类别置信度；热图像素与 14×14 网格独立重建匹配 |
| Job、幂等及错误 | 重复上传/预测键返回同一响应，冲突键 409；排队取消与运行中 409、失败无 Mock 回退有测试；错误 DICOM 422，模型不可用时 health degraded/能力 unavailable/上传 503 `MODEL_UNAVAILABLE`，见 [`model_unavailable_http.json`](../../qa/evidence/p0_unified/model_unavailable_http.json) |
| Mock 区分 | 旧 PNG HTTP 路径返回 `status=success`、`source=MOCK`，见 [`mock_http.json`](../../qa/evidence/p0_unified/mock_http.json) |
| Token 与文件边界 | API 热图无 Token/错 Token 各 401，正确 Token 200；API Gradio 文件路由无 Token 401、正确 Token 对结果目录 403；独立 UI 的 DICOM 上传临时文件、预览/图层缓存未登录均 401，见 [`token_asset_boundaries.json`](../../qa/evidence/p0_unified/token_asset_boundaries.json) 与 [`ui_file_boundaries.json`](../../qa/evidence/p0_unified/ui_file_boundaries.json) |
| 浏览器真实页面 | Playwright 浏览器登录独立 UI，上传 synthetic DICOM，页面分别显示“上传 PENDING / 解析 COMPLETED / 预处理 COMPLETED”、Baseline `0.025618`、遮挡 Job `COMPLETED`、16/32/64 px 图层与 729/169/36 位置；刷新后恢复原 case/slice/job 与结果。浏览器会话已关闭 |
| 冻结保护 | 前后哈希报告字节一致；161/161 正式产物、协议、配置与 checkpoint 均 PASS，freeze SHA `ffe8c227361c877ba1ced0764b7b53f1f152526151241fd9a3b229e63f333d3c`，见 [`freeze_before.json`](../../qa/evidence/p0_unified/freeze_before.json) 与 [`freeze_after.json`](../../qa/evidence/p0_unified/freeze_after.json) |

第一次运行前端/后端/QA 测试时，本机已有代理环境使 Gradio 导入阶段的 `httpx` 抛出 `InvalidURL: Invalid port: ':1'`，用例没有开始。完整收集 traceback 见 [`proxy_collection_failure.txt`](../../qa/evidence/p0_unified/proxy_collection_failure.txt)。在该主机保留现有代理变量，从集成工作树执行下列命令可复现收集失败：

```sh
APP_DATA_ROOT=/tmp/epilocate-p0-proxy-repro EPILOCATE_FROZEN_ROOT=/Users/skyfrost/Documents/Techniques/infectious-ct-ai APP_MODE=real PYTHONPATH=.:gradio_service /Users/skyfrost/Documents/Techniques/infectious-ct-ai-p0/.venv-p0/bin/python -m pytest -q -p no:cacheprovider gradio_service/tests/test_frontend_real.py
```

在本机测试命令里设置 `NO_PROXY/no_proxy=127.0.0.1,localhost` 并清空 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 及其小写形式后，统一测试通过。没有更改业务断言或数值容差。

## 边界、风险与独立 QA 清单

- 该原型仅支持本机 loopback。无 Token 模式下本机匿名资产请求仍返回 200；若要声称受保护访问，必须启用 Token 模式及本机 UI 登录。不得经外网反向代理公开此原型；当前没有用户级身份映射、病例/Job/资产逐对象 ACL 或真实临床数据准入。
- UI 登录是本机单凭据。Gradio 浏览器状态可在同一服务会话刷新恢复，跨 UI 服务重启的自动恢复仍需独立 QA 验证；后端 SQLite 中的 Job/结果可按匿名 ID 查询。在线文件尚无自动保留期和清理策略。
- 运行中的遮挡不能安全中断；仅排队分析可取消。真实页面没有取消按钮。服务重启会将队列中/运行中的 Job 标记失败；未实现续算。
- 独立 QA 应在交付消息的固定 HEAD 上重新运行完整测试与两种 HTTP 探针，验证 Token 401/403、Gradio 文件路由、正确 Token 资源访问、无 Token loopback 边界、真实浏览器上传/分类/三尺度/刷新/错误、Mock 与模型不可用路径，并再核对 161/161 冻结哈希。不得用本报告替代独立验收。

未读取 Formal Test 像素，未运行 Formal Test inference、Robust Training、LIME 或 Grad-CAM。科研候选响应仍是模型遮挡响应假设，不是病灶真值或临床结论。
