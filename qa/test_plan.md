# EpiLocate P0 独立 QA 测试计划

## 固定范围与环境

- 被测提交：`3b3c270869663293769f99ab3cbc180904185a1f`，分支 `test/p0-real-qa` 从该提交建立。所有 Phase A 产品断言均针对该提交。
- 输入：仅 `docs/interfaces/fixtures/p0_synthetic_ct.dcm`，SHA-256 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`。不读取 formal test pixels。
- 运行：本机 loopback `127.0.0.1:8893`；缺失模型探针短时使用 `8894`。QA 数据、SQLite、上传、日志、结果分别置于 QA 专用临时根的子目录，未复用其他会话服务。两个 QA 服务均已停止。
- Python：现有 P0 虚拟环境，只读复用；`NO_PROXY=127.0.0.1,localhost`，避免本机 `::1` 代理解析问题。真实服务为 CPU 模式，未启动 MPS 长驻进程。
- 科研冻结核验：仅读取 freeze JSON、协议/config/checkpoint 与冻结清单中产物的字节哈希；不打开 formal test 像素，不运行训练或 formal test 推理。

## Phase A：固定提交

1. 运行现有 `gradio_service/tests` 与 QA 复制的上游遮挡函数测试，预期 21 项通过。
2. 启动独立真实服务；以 synthetic DICOM 通过 HTTP 上传、病例/切片/预览、Baseline、三尺度遮挡、Job、位置分页和资产。
3. 用独立计算核对 `q0/qg` 原预测类别语义、`max(q0-qg,0)`、三尺度位置数、224 响应图逐像素值和 14×14 面积均值。Golden 概率只用于指定 synthetic fixture，容差沿用向量的 `1e-6`。
4. 以 Gradio API 调用既有 `run_dicom`，对照 HTTP 概率与来源；单独核对 Mock 结果标识。
5. 测异常输入、幂等冲突、结果缺失、路径遍历、权限、模型不可用、失败 Job 与超大文件；无法受控注入的网络超时和取消列 BLOCKED。
6. 在所有 Phase A 测试前后分别进行冻结产物哈希核验，并比较结果。

复现命令（先在 QA worktree 设置自己的临时目录与冻结根；端口须重新检查空闲）：

```sh
export QA_PYTHON=/absolute/path/to/p0-venv/bin/python
export EPILOCATE_FROZEN_ROOT=/absolute/path/to/frozen-experiment-root
export APP_DATA_ROOT=/tmp/epilocate-p0-qa-local
export APP_MODE=real
export PYTHONPATH=.:gradio_service
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
"$QA_PYTHON" -m pytest -q gradio_service/tests qa/tests/test_occlusion_runner_upstream.py
"$QA_PYTHON" -m pytest -q qa/tests/test_api_negative.py
"$QA_PYTHON" qa/check_freeze.py --frozen-root "$EPILOCATE_FROZEN_ROOT" --output /tmp/qa-freeze.json
"$QA_PYTHON" -m uvicorn gradio_service.gradio_debug.app:app --host 127.0.0.1 --port 8893
# 在另一个终端中，保持相同的 QA 虚拟环境和独立数据根：
"$QA_PYTHON" scripts/smoke_p0_http_gradio.py --url http://127.0.0.1:8893 --output /tmp/qa-http-smoke.json
"$QA_PYTHON" qa/probe_http.py --url http://127.0.0.1:8893 --output /tmp/qa-http-probe.json
```

`qa/probe_http.py` 的资产授权断言在固定提交上预期记录 **FAIL**，这是 QA-BE-001，不应通过改低预期消除。服务只绑定 loopback；每次测试后仅停止自己启动的进程。模型不可用探针需使用另一个独立数据根和缺失的冻结根短时启动服务，其实际结果已保存于 `evidence/model_unavailable_http.json`。

## Phase B：固定集成提交

需要集成负责人给出固定 frontend、backend、integration commit、实际启动方式及统一测试环境。还需明确 API 基础地址、Bearer Token 是否启用、服务端安全传递方式以及 Job 状态映射；QA 不把服务端密钥写入浏览器、测试证据或仓库。Token 开启时分别验证无凭据/错误凭据 401、合法凭据同病例资产 200、跨病例访问拒绝；Token 关闭时仅验证 loopback 范围并记录限制。只对固定 integration commit 重跑完整真实 UI 链路：DICOM 上传 → Baseline → 三尺度遮挡 → 热图叠加 → Job 刷新/断网恢复，并复核来源与冻结完整性。缺少任一固定输入时，前端及端到端判定保持 BLOCKED。

## 判定规则

`PASS` 表示本计划对应的实际运行断言通过；`FAIL` 表示观察结果与预期不符；`BLOCKED` 表示固定代码或受控环境尚未提供。Schema 验证不替代真实 HTTP 或浏览器验收。只有 Phase B 固定集成提交通过完整真实链路后，才可给出整个 P0 集成 QA 通过的结论。
