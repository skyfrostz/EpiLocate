# P0 真实算法集成验证记录（2026-09-26）

## 判定

**通过本机 P0 单切片真实算法接入验收。** 真实 DICOM 已经由 HTTP `POST /api/v1/cases`、`POST /api/v1/predictions` 和 `POST /api/v1/jobs/occlusion` 完成冻结 Baseline 推理并返回结果；Gradio `run_dicom` 也实际调用同一服务。此判定只覆盖本机单切片原型，不覆盖多切片、NIfTI、外网授权或临床用途。

## 运行证据

- OpenAPI 3.1 `algorithm_api_contract.yaml` 经 `openapi-spec-validator` 验证；真实 API 响应另经 JSON Schema 验证。Schema 检查是补充证据，不单独构成真实接入验收。
- `PYTHONPATH=.:gradio_service .venv-p0/bin/python -m pytest -q gradio_service/tests /absolute/path/to/original/tests/test_occlusion_runner.py`：**21 passed**。含 B 分支原有 Mock/job 测试、新增真实 DICOM HTTP/空间/幂等/冻结目录写入保护测试和原冻结遮挡函数 8 项测试。
- 使用 `scripts/smoke_p0_http_gradio.py` 对运行在 `127.0.0.1:8877` 的 Uvicorn 发真实请求：健康 200，Gradio 200，单 DICOM 上传 202，分类和三尺度遮挡 job 完成，位置数 729/169/36，原图预览 112×80，热图 224×224。Gradio `run_dicom` 的三尺度遮挡也实际完成并返回 `LIVE_CASE`。HTTP 与 Gradio 正类概率同为 `0.025618407875299454`，绝对误差 0。原始输出写入本机 `/tmp/epilocate-p0-http-gradio-final.json`，仓库只保留去标识的合成向量与此摘要。
- 使用 `scripts/verify_p0_offline_consistency.py` 只读冻结 smoke 的 **train** 固定切片 `f0` 及其 `raw_responses.csv`，在临时目录做去标识拷贝，断言 `PixelData` 字节不变，再经 HTTP 跑同一 Baseline 和三尺度遮挡。分类 `p0` 绝对误差 **0**；16/32/64 尺度 `(x=0,y=0)` masked 正类概率绝对误差分别为 **1.11e-16**。容差 1e-5。结果在本机 `/tmp/epilocate-p0-offline-consistency-final.json`。未读取 formal test 像素或 manifest。
- 合成 DICOM SHA-256 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`；冻结 checkpoint SHA-256 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`、epoch 2；协议、Stage 1 配置和 Baseline 配置哈希分别为 `204e34ae2474ab91076cbe3d2fb8ba5ad6f5affb631274c3feed57ed2da7160b`、`6a9d1b011250e59956f443add621e786e04ceb6716a8329bc08df1e1e12f2b8a` 和 `7c456065fbff126d25417ad4580c8f8ac58a2b80f5e8fde1356bd6d92a021e17`。模型严格加载，无权重下载、训练、反向传播或 optimizer。
- 原图像素边界到算法 224 边界的仿射为 `[2,0,0,0,2.8,0,0,0,1]`。自动化测试逐像素比对原图预览与冻结窗宽窗位结果；用 API 分页遮挡分数重新栅格化，逐像素比对热图 PNG，并比对 14×14 面积平均网格。显示 PNG 每张独立按最大响应归一化，科研数值须读位置与比较网格。

## 实际可用 API

| 方法 | 路径 | P0 范围 |
| --- | --- | --- |
| GET | `/api/health`, `/api/v1/capabilities`, `/api/v1/contract` | 健康、真实能力、v0.1 兼容 schema |
| POST | `/api/v1/cases` | 一个已去标识 CT DICOM，返回匿名 case 和解析 job |
| GET | `/api/v1/cases/{case_id}`, `/api/v1/cases/{case_id}/slices`, `/api/v1/slices/{slice_id}/preview` | 单片状态、几何、窗宽窗位原图 PNG |
| POST | `/api/v1/predictions` | 冻结 Baseline 单切片分类 job |
| POST | `/api/v1/jobs/occlusion` | 冻结 Stage 1 的指定 16/32/64 尺度遮挡 job |
| GET | `/api/v1/jobs/{job_id}`, `/api/v1/jobs/{job_id}/result` | 状态与结果；Mock 旧入口仍为 v0.1 |
| GET | `/api/v1/occlusion-results/{result_id}/positions`, `/api/v1/assets/{asset_id}?result_id=...` | 位置分页、响应/候选 PNG 与 14×14 JSON |
| POST | `/api/v1/jobs/inference` | **仅 PNG/JPG Mock**，`mode=mock,source=MOCK`；`APP_MODE=real` 时不用于真实推理 |

## 未完成接口与边界

`POST /comparisons`、`/jobs/coarse-localization`、`/jobs/lime`、`/feedback` 和 `/jobs/{job_id}/cancel` 明确返回 501 `NOT_IMPLEMENTED`。NIfTI、多 DICOM 序列、患者级预测、冻结 validation 只读汇总端点、用户认证/对象授权、上传保留期限和可恢复任务尚未实现。`aid_site` 未代理该服务。候选区域是模型遮挡响应假设，不是病灶标注。

当前服务只应绑定 loopback。P0 去标识入口检查 `PatientIdentityRemoved=YES`、`BurnedInAnnotation=NO`、常见身份字段和 private tags；这不是完整 DICOM 去标识审计。服务运行时读 checkpoint、协议和配置，不读或写冻结 validation 产物。原工作区的 `main` 和未提交科研文件保持原样，远端 `main` 与 B 分支未改写。
