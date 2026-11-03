# E2 / CT-FM 应用接缝 v1（INT 文件交接）

本契约归 INTEGRATION，算法 handler 归 LOCALIZATION / ENCODER。状态为开发接缝，生成注入测试不得写成真实 M1/M2。M0/v16 不改。路由追加到 `/api/v2/jobs/algorithm`；任务类型 `ALGORITHM` 独立于旧 PREDICTION/OCCLUSION。复用原 Job/Attempt/Lease/提交幂等/存储与认证，不新建队列或调度器。扩展结果 `contract_version=next-1`，原 2.0 结果校验保持原分支。

共享机器契约在 `epilocate_next/contracts.py`，可由 Pydantic `model_json_schema()` 导出。固定调用：

```python
handler(request: ApplicationRequest, input_path: Path,
        output_dir: Path, context: HandlerContext) -> HandlerOutput
```

request 绑定 Case/Study/Series/display slice、模型组件 SHA、算法/预处理/config SHA、任务标签与单位、输入维数、原生 shape/LPS affine/空间 ledger、预算、LIVE/PRECOMPUTED/SYNTHETIC 模式。E2 必须 E2-CT + SINGLE_SLICE + 二维分类器；CTFM 必须 CTFM-VOLUME-HEAD + VOLUME + encoder/head 两个 SHA，不允许 repeat/reshape 把体积分类器伪装二维函数。CTFM 的模型输入由后端受控 volume resolver 提供，原 CT display slice 是单独绑定；缺体积交付即拒绝，不偷偷用当前片代替体积。

handler 返回原始 logits/类别、候选区域与响应、算法状态、实际 F/B/update、运行时间、证据类型及 PNG 字节。E2 连续 Mask、CPF gap 与最终 CPF/PSMI patch 支持图层分别为 OPTIMIZED_INPUT_MASK / HSPI_CPF_GAP / HSPI_CPF_PSMI_PATCH_SUPPORT；CTFM 粗图为 SIGNED_FEATURE_CONTRIBUTION，保留原始有符号数值与显示范围，不叫病灶概率。空间回映归算法/DATA；INT 不复制 HSPI/CTFM 数学或临时猜映射。

原生图层必须已经回映为 display SOP 的 RAW_PIXEL_EDGE，尺寸等于原图；逐图层绑定 display DICOM SHA、空间 ledger SHA、映射 QA 收据 SHA。未验证映射、NO_RELIABLE_RESPONSE、PARTIAL_BUDGET、FAILED、BLOCKED、NOT RUN 可保存原数值/状态，但不启用叠加，不解释成正常 CT。算法终态与 Job 传输完成分别记录。超时触发后允许在途完成/退出延迟；保存真实 runtime 和 stop_events，停止后不再新增计算，PARTIAL_BUDGET 不截短时间。运行预算须在 handler 每次真实计算前使用 context.forward/backward/update，由现有 supervisor 注入守卫；接口后的实际计数要一致，不另造 GPU 锁。

仅默认关闭的显式应用配置可注册 handler 和模型/输入 binding。未知提交先查询持久化接受收据，不重新运算；ALGORITHM 单次 attempt，不自动重投。资产名、SHA、PNG 尺寸和身份前后核验，结果页面刷新只 GET。PRECOMPUTED 和 SYNTHETIC 始终明确显示，不标 LIVE。

完整 canonical request digest 派生服务器幂等键；同用户刷新或换客户端 UUID 仍返回同一 Job，不能用新 UUID 增加模型计算。另一次计算需要总控重新绑定完整版本化 request。`app.state.next_algorithms_enabled` 默认 false，`next_algorithm_request_digests` / `next_algorithm_worker_ids` 默认空。只有显式绑定的应用 Worker 领取 ALGORITHM，旧 Worker 不会误领；应用 Worker 不领取旧类型任务。模型注册沿用 ModelVersion，避免覆盖历史模型行。LIVE context 必须提供现有 ChildGuard 的 before_forward/before_backward/check；不创建第二锁。

薄 E2 adapter 在 `epilocate_next/e2_adapter.py`。PreparedBinding 分开绑定源输入 SHA 和预处理数组 SHA：原 DICOM 文件摘要不会冒充 Prepared2DInput.image 的字节摘要。LOC提供完整二维 f 和空间 ledger，INT只校验/保存，不解码 CT、加载权重或复刻 HSPI。trace/stage/checkpoint 每次写入前计容量并保全，异常不删除 partial。完成的在途更新仍计数；backward 超时完成后，阻止新的 optimizer step。未获准 LIVE provider/监督/输入时没有真实 launcher。

LOC原始整参考 patch union 另存为 HSPI_PSMI_WHOLE_PATCH_SUPPORT；HSPI_CPF_PSMI_PATCH_SUPPORT 是其与 valid_support 相交后的 native reliable。候选仅在完整 SUCCESS 且映射验证后导出；原生 bbox按 array_zyx_to_LPS_mm affine回映，PNG灰度只为显示，数值仍独立保存。

`epilocate_next/e2_replay.py` 提供 E2PrecomputedAdapter，加载总控供应的 ReplayBinding，一次验证源结果 SHA、config/core/model/preprocess/数组/native QA 摘要后转换保存。预算必须 F0/B0/update0，不调用模型/core；新任务 source=PRECOMPUTED，原证据类型与原计算耗时/计数放 diagnostics，不能伪称 LIVE 或将合成原结果升级为医学证据。真实 E2-Q 未运行前没有可填的真实 replay 文件；缺口保持 NOT_READY。应用升级可复用同一 E2-Q 结果，不重复科学模型计算。

导出的两份 JSON schema 和可执行合成入口见 `hospital-release/20261011-next-application-v17/`；`qa/next_algorithm_application_smoke.py` 只能生成测试，不接受真实 CT 或模型参数。CTFM现阶段仅接口及注入测试；未实现真实 volume resolver/head/handler，不标已接入真实模型。原 E1/F0/F1 sidecar及医院 gate继续使用既有独立契约，不由CTFM模式暗中代替。

LOC/ENC 文件交接请提供：本契约版本、完整模块/配置/模型 SHA、handler 入口、同一模式的输入要求、逐调用预算 hooks、原生映射证据、终态/原数值和 assets 字节。仅论文配置/CLI/研究结果文件不等于已装进应用。CTFM 实际 head/体积 resolver，E2 实际 handler/config 及独立新增应用执行批准仍由各线/总控交付。
