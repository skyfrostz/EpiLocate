# Phase A：算法与 HTTP API 独立 QA 报告

被测提交：`3b3c270869663293769f99ab3cbc180904185a1f`。证据见 `evidence/phase_a_pytest.txt`、`evidence/http_smoke.json`、`evidence/http_probe.json`、`evidence/model_unavailable_http.json` 和 `qa/tests/test_api_negative.py`。

## 已通过

- **Real Algorithm QA — PASS：**固定提交的 21 项测试通过；synthetic DICOM 可读取。HTTP 与 Gradio 均返回 `LIVE_CASE`，正类概率同为 `0.025618407875299454`，差为 0；该值只适用于本 fixture。
- **Backend API QA — PASS：**能力、单片上传/解析、病例与切片、112×80 预览、分类、三尺度遮挡、Job/result、分页、224×224 响应图和 14×14 网格均通过实际 HTTP。三尺度位置数为 729/169/36。上传及预测幂等重试返回同一响应；不同请求复用键返回 409。
- **算法语义 — PASS：**独立从每个位置的 `p0/pg` 和原预测类别重算 `q0/qg`，934/934 个位置的决策置信度变化、候选响应及 flip 一致。独立栅格化逐像素核对三张响应 PNG；三张比较网格与独立 16×16 面积均值一致。原图 112×80 到算法 224×224 的边界仿射来自 API，未将 14×14 视为 CT 坐标。
- **负向路径 — PASS：**非法 DICOM 422、身份字段 422、不支持格式 415、缺少幂等键 422、结果不存在 404、资产路径遍历 404、超限上传 413、失败 Job 的状态与错误结果、模型不可用 503。`APP_MODE=real` 且模型不可用时，旧 `/jobs/inference` 也返回 503，未回退 Mock。
- **Mock QA — PASS（单元测试）：**Mock 适配器结果为 `source=MOCK`，含显著 `MOCK RESULT`。未把 Mock 输出纳入真实算法指标。
- **科研冻结完整性 — PASS：**测试前后均为 161/161 项 SHA-256 一致；manifest 在冻结清单中，protocol、Stage 1 config、checkpoint 哈希一致，freeze JSON 哈希前后同为 `ffe8c227361c877ba1ced0764b7b53f1f152526151241fd9a3b229e63f333d3c`。此检查只验证字节完整性，不等于重跑 formal validation。

## 失败与阻塞

- **权限 — FAIL（QA-BE-001）：**匿名请求通过有效 `result_id` 与 `asset_id` 读取 synthetic 热力图时返回 200；期望受保护资产为 401/403。固定提交明示只适合 loopback，本项是外部部署前的后端/集成阻塞。
- **超时 — BLOCKED：**没有受控慢请求或固定超时注入环境；未将普通网络连接失败冒充服务端超时测试。
- **取消 — BLOCKED：**`/jobs/{id}/cancel` 为 501 `NOT_IMPLEMENTED`；无法验证 `CANCELLED` 转换。P0 不宣称可取消。
- **HTTP 实际执行失败注入 — BLOCKED：**QA 在隔离数据库注入 `FAILED` Job 并验证公开状态及无 Mock 结果；没有修改算法或模拟真实计算崩溃来制造失败。
- **认证与对象授权 — FAIL/BLOCKED：**当前固定提交没有身份体系；无法通过真实角色验证 401/403 和跨病例资产隔离。见 QA-BE-001。

## 状态范围

上传响应给出 `PENDING`，随后解析 Job 可查询为 `COMPLETED`。轮询中观察到预测和遮挡的 `RUNNING → COMPLETED`；`PENDING` 的轮询瞬态可能未采样到。`FAILED` 由隔离数据库注入测试。`CANCELLED` 未实现。没有凭状态枚举推断未观察到的迁移已通过。
