# 可复制到飞书的接口交接消息

## 发给前端开发同事的接口交接说明

EpiLocate 接口已按真实仓库完成审查。当前 B 的 `feat/gradio-demo-p0` 分支可用于本地 PNG/JPG Mock 调试，能提交 job、轮询状态并读取 Mock 分类 JSON；真实 CT 分类、遮挡热力图、切片浏览、Robust、逐级粗定位、LIME 和医生修正页面尚未接入。展示站点 `aid_site` 的影像/分析 API 仍返回 `NOT_CONNECTED`。请不要把 Mock 数字或候选遮挡响应标成临床结果/真实病灶。

请以 `docs/interfaces/frontend_handoff.md` 的九页映射与 `docs/interfaces/algorithm_api_contract.yaml`、`algorithm_api_contract.md` 为开发输入。近期先保留 B 的 P0 Mock 页面，接 capability 状态、job 轮询、source/版本提示；随后准备 CT 切片浏览、分类、遮挡和三尺度比较 UI。热力图按 `slice_id` 对齐固定窗预览，区分原始 CT、224×224 算法图与 14×14 比较网格；`object-fit: contain` 留白要计入变换，插值只用于显示。候选状态无效时不画区域；未实现模块禁用并写明原因。

交付物：页面/组件、API 调用清单、synthetic fixture 截图与坐标叠加验证记录、加载/错误/断网重试状态说明。验收：Mock 和真实来源清楚分开，页面不暴露本机路径/患者信息，长任务刷新后可按 job_id 继续查询，三尺度图层没有错位。依赖 B 后端提供病例、资产、job 与 capability 接口；依赖 A 确认算法口径与图层坐标。当前不需要 formal test 数据。

## 发给后端开发同事的接口交接说明

EpiLocate 的正式 Stage 1 validation 已冻结并通过独立 QA：28 名患者、5,637 个切片、三尺度遮挡结果可只读展示。B 分支 `gradio_service` 现有 FastAPI + Gradio P0 只支持 PNG/JPG Mock；`APP_MODE=real` 的 `algorithm.inference_pipeline.run_case` 尚不存在。主线另有人工 Series 复核服务和项目展示站点，不能用 B 的旧分支树覆盖它们。

请按 `docs/interfaces/backend_handoff.md`、`algorithm_api_contract.yaml` 和 `algorithm_api_contract.md` 开发。近期先在最新主线的独立集成工作树保留 B P0，新增真实 DICOM 单片 Baseline adapter、模型缓存和 checkpoint/hash 校验、匿名 case/slice ID、能力查询、统一 job/错误结构，再接冻结遮挡定义与只读 validation 汇总。`candidate_response=max(q0-qg,0)`，qg 始终是原预测类别在遮挡后的置信度；候选不足是有效状态且 region/layer 为 null。原始 PatientID/UID/绝对路径不得出 API。在线 job/资产存储必须与冻结正式结果分离。

交付物：接口代码与迁移、启动说明、OpenAPI 实现、synthetic fixture 契约测试和受控开发数据测试记录。验收：旧 P0 Mock 不回归，真实模式不可用时 503 而非假结果；切片/患者概率口径清晰；幂等重试不重复建任务；三尺度和空间坐标与冻结定义一致；正式 checkpoint、protocol/config 与 161 项 validation 产物哈希不变。依赖 A 提供并审核真实算法 adapter 的测试向量与方法版本，依赖前端反馈图层/任务状态需求。Robust、LIME 和医生反馈目前只预留，待方法及治理条件确认后再实现。
