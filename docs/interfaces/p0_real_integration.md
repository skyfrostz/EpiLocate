# P0 真实 DICOM 接入与复现

本工作树从 `origin/main` 的 `14c114a` 建立 `codex/p0-real-algorithm`；B 分支 `f153b9b` 的 `gradio_service/` 按文件引入。原本地 `main`、远端 `main` 和原工作区的未提交文件未改写。`scripts/occlusion_runner.py`、两份冻结配置和接口契约是从原工作区逐字复制的只读算法/协议来源；本分支未调用训练入口，也未打开 formal test。

## 启动

运行环境需安装根 `requirements.txt` 及 `gradio_service/requirements-gradio.txt`。设置 `EPILOCATE_FROZEN_ROOT` 为存有冻结 checkpoint、Stage 1 协议和配置的原实验根目录，服务只读访问它们。设置独立的 `APP_DATA_ROOT`，不要指向 `outputs/experiments/`。仅绑定 loopback，不能直接公开；P0 尚无用户认证、授权资产和上传保留策略。

```sh
export EPILOCATE_FROZEN_ROOT=/absolute/path/to/infectious-ct-ai
export APP_DATA_ROOT=/tmp/epilocate-p0-service
export APP_MODE=real
export PYTHONPATH=/absolute/path/to/infectious-ct-ai-p0
python -m uvicorn gradio_service.gradio_debug.app:app --host 127.0.0.1 --port 8877
```

若本机 `NO_PROXY` 包含未加方括号的 `::1`，Gradio 6 / httpx 0.28 初始化可能报 `Invalid port ':1'`。本机验证时设 `NO_PROXY=127.0.0.1,localhost` 和同值 `no_proxy`。

启动时或首次请求严格核验 checkpoint SHA-256 `548b39…cad734`、epoch 2、Stage 1 协议与配置 SHA-256，模型使用 CPU `eval/inference_mode`，不下载权重。缺失或篡改时能力报告为 `unavailable`，真实端点返回 503。

## 前端联调

合成 DICOM 在 `docs/interfaces/fixtures/p0_synthetic_ct.dcm`；向量请求及预期值在 `p0_http_vector.json`。亦可运行 `python scripts/generate_p0_synthetic_vector.py /tmp/p0_synthetic_ct.dcm` 再生成完全相同的文件。此向量没有患者标识，须保留 `PatientIdentityRemoved=YES` 与 `BurnedInAnnotation=NO`。生产影像不应通过这一无认证本机原型上传。

先 `POST /api/v1/cases`，再 `GET /api/v1/cases/{case_id}/slices` 取动态 `slice_id`，然后提交预测或遮挡 job；轮询 `/api/v1/jobs/{job_id}` 到 `COMPLETED`，从 `/result` 取结果。遮挡位置经 `/api/v1/occlusion-results/{result_id}/positions?scale=16&cursor=0&limit=1000` 分页获取。结果的 `source=LIVE_CASE`，原 PNG/JPG 兼容入口的 `source=MOCK`。

原图预览是原始 112×80 窗宽窗位像素，算法输入及遮挡热图是 224×224。此向量边界仿射为 `[2,0,0,0,2.8,0,0,0,1]`；例如原图右下边界 `(112,80)` 映射到 `(224,224)`。热图、二值候选图和算法输入均使用左上原点、向右 x、向下 y。热图 PNG 是按该图最大值归一化的显示图；定量数值以位置分页和 14×14 JSON 比较网格为准。

## 当前边界

单 DICOM 切片、Baseline 分类、16/32/64 Stage 1 遮挡、job 查询、结果、位置分页及图层可用。`dicom_series` 在 P0 仅允许一个文件。NIfTI、多切片病例、患者级汇总、取消、历史 validation 只读摘要、Robust、逐级粗定位、LIME 和医生反馈尚未接入。候选图是模型遮挡响应假设，不是病灶金标准。`POST /cases` 在 P0 同步完成解析并返回已完成的 CASE_PARSE job；结果和预览仅供本机联调。
