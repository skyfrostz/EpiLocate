# P0 独立 QA 测试矩阵

被测固定提交：`3b3c270869663293769f99ab3cbc180904185a1f`。Phase A 仅使用 synthetic fixture；Phase B 需固定集成提交。

| 测试编号 | 范围与断言 | 状态 | 证据 |
| --- | --- | --- | --- |
| ALG-01 | 既有 P0 与上游遮挡函数 21 项测试 | PASS | `evidence/phase_a_pytest.txt` |
| UI-LEGACY-01 | 旧 Gradio `run_dicom` 与 HTTP 概率、来源一致 | PASS | `evidence/http_smoke.json` |
| MOCK-01 | Mock 单元测试明确 `source=MOCK` | PASS | 21 项测试 |
| HTTP-01 | `real_health` | PASS | `evidence/http_probe.json` |
| HTTP-02 | `real_capabilities` | PASS | `evidence/http_probe.json` |
| HTTP-03 | `planned_capabilities` | PASS | `evidence/http_probe.json` |
| HTTP-04 | `upload_http` | PASS | `evidence/http_probe.json` |
| HTTP-05 | `upload_idempotency` | PASS | `evidence/http_probe.json` |
| HTTP-06 | `case_parse_job` | PASS | `evidence/http_probe.json` |
| HTTP-07 | `case_source` | PASS | `evidence/http_probe.json` |
| HTTP-08 | `single_slice` | PASS | `evidence/http_probe.json` |
| HTTP-09 | `geometry` | PASS | `evidence/http_probe.json` |
| HTTP-10 | `preview_size` | PASS | `evidence/http_probe.json` |
| HTTP-11 | `prediction_submit` | PASS | `evidence/http_probe.json` |
| HTTP-12 | `prediction_idempotency` | PASS | `evidence/http_probe.json` |
| HTTP-13 | `idempotency_conflict` | PASS | `evidence/http_probe.json` |
| HTTP-14 | `prediction_job` | PASS | `evidence/http_probe.json` |
| HTTP-15 | `prediction_source_unit` | PASS | `evidence/http_probe.json` |
| HTTP-16 | `golden_probability_within_declared_tolerance` | PASS | `evidence/http_probe.json` |
| HTTP-17 | `model_identity` | PASS | `evidence/http_probe.json` |
| HTTP-18 | `occlusion_submit` | PASS | `evidence/http_probe.json` |
| HTTP-19 | `occlusion_job` | PASS | `evidence/http_probe.json` |
| HTTP-20 | `occlusion_source_slice` | PASS | `evidence/http_probe.json` |
| HTTP-21 | `future_modules` | PASS | `evidence/http_probe.json` |
| HTTP-22 | `mask_position_counts` | PASS | `evidence/http_probe.json` |
| HTTP-23 | `fixed_decision_class_q0_qg_formula` | PASS | `evidence/http_probe.json` |
| HTTP-24 | `independent_heatmap_pixels_all_scales` | PASS | `evidence/http_probe.json` |
| HTTP-25 | `independent_14x14_grid_all_scales` | PASS | `evidence/http_probe.json` |
| HTTP-26 | `invalid_dicom` | PASS | `evidence/http_probe.json` |
| HTTP-27 | `unsupported_format` | PASS | `evidence/http_probe.json` |
| HTTP-28 | `missing_idempotency_key` | PASS | `evidence/http_probe.json` |
| HTTP-29 | `identity_field_rejected` | PASS | `evidence/http_probe.json` |
| HTTP-30 | `missing_result` | PASS | `evidence/http_probe.json` |
| HTTP-31 | `asset_traversal_rejected` | PASS | `evidence/http_probe.json` |
| HTTP-32 | `asset_requires_authorization` | FAIL | `evidence/http_probe.json` |
| NEG-01 | 超限上传返回 413 | PASS | `qa/tests/test_api_negative.py`，2 passed |
| NEG-02 | 注入 FAILED Job 后状态与结果错误、无 Mock | PASS | `qa/tests/test_api_negative.py`，2 passed |
| NEG-03 | 模型不可用时能力 unavailable、真实上传及旧兼容入口返回 503 | PASS | `evidence/model_unavailable_http.json` |
| FREEZE-01 | 161 项冻结产物与固定输入测试前哈希 | PASS | `evidence/freeze_before.json` |
| FREEZE-02 | 161 项冻结产物与固定输入测试后哈希 | PASS | `evidence/freeze_after.json` |
| JOB-01 | PENDING 提交响应、RUNNING/COMPLETED 轮询 | PASS | `evidence/http_probe.json` |
| JOB-02 | CANCELLED 真实迁移 | BLOCKED | P0 cancel API 为 501 |
| ERR-01 | 真实计算异常注入后的 HTTP 失败链路 | BLOCKED | 仅完成隔离数据库 FAILED Job 检查 |
| ERR-02 | 受控服务端超时与重试 | BLOCKED | 未提供可控慢请求环境 |
| AUTH-01 | 身份/跨病例授权矩阵 | BLOCKED | 固定提交无认证体系；HTTP-32 已观察匿名 200 |
| AUTH-02 | 可选 Bearer Token 开启时 401、合法访问及跨病例边界 | BLOCKED | 固定后端与集成提交及启用配置未提供 |
| FE-AUTH-01 | 前端服务端传递 Token、浏览器不泄露密钥、401 提示 | BLOCKED | 固定前端/后端提交未提供 |
| JOB-03 | 固定后端 Job 状态语义与前端显示一致 | BLOCKED | 固定集成提交未提供 |
| FE-01 | 固定前端提交的上传、分类、三尺度、叠加与截图 | BLOCKED | 前端固定提交未提供 |
| FE-02 | 新页面刷新、断网与错误显示 | BLOCKED | 前端固定提交未提供 |
| E2E-01 | 固定 integration commit 的完整真实浏览器链路 | BLOCKED | 集成提交与环境未提供 |

HTTP-32 的 `asset_requires_authorization` 失败归入 QA-BE-001。测试矩阵中的 BLOCKED 均未计作通过。
