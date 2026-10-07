# P0 真实单切片前端集成报告

日期：2026-09-26。分支：`feat/p0-frontend-real`。固定基线与开发前 HEAD：`3b3c270869663293769f99ab3cbc180904185a1f`。本报告只判定本分支前端的本机 synthetic 向量验收；不代表整个 P0 已完成统一集成或独立 QA。

## 实现范围

| 状态 | 内容 |
| --- | --- |
| REAL_IMPLEMENTED | Gradio 单切片 DICOM 页通过独立 `P0Client` 调用 `POST /api/v1/cases`、病例/切片/预览、`POST /api/v1/predictions`、`POST /api/v1/jobs/occlusion`、Job/result、位置分页和资产 API。显示匿名 ID、预处理状态、单切片分类、模型/预处理版本、`LIVE_CASE` 来源、16/32/64 px 响应与候选有效性。 |
| REAL_IMPLEMENTED | 预览采用后端 `raw_to_algorithm_edge_affine` 的逆变换投影到算法输入尺寸，再和响应图合成一张显示图；切片、来源、尺寸或坐标空间不匹配则拒绝叠加。BrowserState 保存匿名 case/slice/job ID，页面刷新后重新查询 Job。 |
| MOCK_IMPLEMENTED | 原 PNG/JPG v0.1 兼容页保留在单独的 `PNG/JPG Mock · legacy` 标签，明确标注 `MOCK RESULT`；不进入真实 CT 结果页。旧 Gradio DICOM 调试页也保留为 legacy。 |
| PLANNED | NIfTI、多切片 CT 浏览、患者级汇总、Robust、稳定粗定位、LIME、医生反馈。界面明确列出，不产生结果或候选区域。 |
| BLOCKED | 外网发布需后端对象授权、认证和上传保留策略；当前算法 API 仅按基线文档绑定 loopback。取消、可恢复任务与患者级接口尚不存在。 |

## 联调证据

使用 `fixtures/p0_synthetic_ct.dcm`，其 SHA-256 与 `fixtures/p0_http_vector.json` 相符。独立服务监听 `127.0.0.1:8882`，运行数据在 `/tmp/epilocate-p0-frontend-20260926`；未占用基线示例端口 `8877`，未启动另一套长期 MPS 模型服务。服务 `/api/health` 返回 `real_ready=true`。浏览器通过新 Gradio 页上传并预处理，结果 `source=LIVE_CASE`；Baseline 正类概率显示 `0.025618`，与向量期望值 `0.025618407875299454` 一致。三尺度位置分页计数为 729 / 169 / 36，响应资产为 224×224，原始预览为 112×80。浏览器切换 16、32、64 px 后叠加、摘要和位置计数同步变化。

浏览器刷新后重新显示同一个 `OCCLUSION · COMPLETED` Job、单切片分类和热力图。无效合成 DICOM 上传由真实 API 返回 `IMAGE_PARSE_FAILED`，未生成 Mock 预测。前端单元测试覆盖，覆盖 PENDING / RUNNING / COMPLETED / FAILED / CANCELLED、网络断开、503 模型不可用、`MOCK` 来源拒显、跨切片拒显、几何尺寸/仿射校验和候选无效时不绘制。FAILED/CANCELLED 与断网为受控前端测试，未人为破坏真实模型服务来制造线上失败。

截图均来自 synthetic 向量，无患者影像：

- [真实 DICOM 与分类](screenshots/p0_real_dicom_classification.png)
- [16 px 响应与叠加](screenshots/p0_occlusion_16px.png)
- [32 px 响应与叠加](screenshots/p0_occlusion_32px.png)
- [64 px 响应与叠加](screenshots/p0_occlusion_64px.png)

## 启动与测试

从本分支根目录运行；先安装根 `requirements.txt` 和 `gradio_service/requirements-gradio.txt`。`EPILOCATE_FROZEN_ROOT` 指向持有已核验冻结 checkpoint/协议/配置的实验根目录，只读使用。端口和数据目录须独立于其他会话：

```sh
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
export EPILOCATE_FROZEN_ROOT=/absolute/path/to/frozen-experiment-root
export APP_DATA_ROOT=/tmp/epilocate-p0-frontend-local
export EPILOCATE_API_BASE_URL=http://127.0.0.1:8882
# 仅在后端启用 Bearer Token 时，在 Gradio 服务端设置同一密钥：
# export EPILOCATE_API_BEARER_TOKEN=<server-side-secret>
export APP_MODE=real
export PYTHONPATH=.:gradio_service
python -m uvicorn gradio_service.gradio_debug.app:app --host 127.0.0.1 --port 8882
```

打开 `http://127.0.0.1:8882/gradio/`，选择“真实单切片 DICOM”，依次上传、分类、遮挡、切换尺度。`EPILOCATE_API_BASE_URL` 是前端唯一 API 地址配置；如果接入同机已有服务，可指向其 loopback 地址。Token 未启用时不设置 `EPILOCATE_API_BEARER_TOKEN`；启用时只在 Gradio 服务器环境设置，客户端对每个 API 请求发送 `Authorization: Bearer <token>`。浏览器只收到业务状态，不收到密钥。401 显示 `AUTH_REQUIRED`，403 显示 `ACCESS_DENIED`；服务端所需 Token 配置名和具体密钥由后端/集成负责人在部署时核对。Job 状态使用 API 的 `PENDING → RUNNING → COMPLETED|FAILED|CANCELLED`；只在 `COMPLETED` 读取结果，失败和取消仅显示状态及脱敏错误。运行测试：

```sh
PYTHONPATH=.:gradio_service python -m pytest -q gradio_service/tests/test_frontend_real.py gradio_service/tests/test_api.py gradio_service/tests/test_contract.py gradio_service/tests/test_jobs.py gradio_service/tests/test_mock_inference.py
```

## 契约差异与未解决问题

- 可选 Bearer Token 是后端尚未合并的实现信息；本分支只添加标准 Authorization 请求头与 401/403 显示。未修改共享 API 契约字段，实际受保护服务的端到端验证留给固定集成提交与 QA。
- `POST /api/v1/cases` 的 202 响应写 `status=PENDING`，但当前服务同步完成解析；页面同时展示响应状态、CASE_PARSE Job 的 `COMPLETED` 和病例预处理 `COMPLETED`，未改动字段。
- 响应 PNG 由后端逐图按最大值归一化，跨尺度颜色强度不能直接比较；页面显示图层值域，并从位置分页读取定量变化。研究统计仍应使用原始位置/14×14 网格。
- 浏览器刷新恢复依赖当前浏览器的 Gradio BrowserState；服务重启时其临时加密密钥可能变化，跨服务重启自动恢复尚未验收。Job 和结果仍由后端持久保存。
- Gradio 文件组件会显示用户所选的原始文件名；使用者须先去标识文件名。页面结果区和报告不展示 DICOM 身份字段或本机绝对路径。
- 本分支未改动 `app.py`、后端 Job/存储、算法、冻结产物或其他工作树。若后端后续修改响应字段或认证/资产方式，应由集成负责人审核契约与共享入口修改。

结论：**本分支前端本机 synthetic P0 验收通过**。仍需统一集成与独立 QA，才可判断整个 P0 系统状态。
