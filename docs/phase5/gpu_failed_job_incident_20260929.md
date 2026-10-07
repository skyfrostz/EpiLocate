# GPU JPEG Lossless 解码失败与恢复

**日期：** 2026-09-29
**范围：** Phase 5 RTX 3090 Engineering MVP；此交接版只记录故障机制与运维结论，不包含原病例引用、对象哈希、Job/Case/Slice ID 或患者影像。完整原始调查材料留在受控本地记录中，不作为公开发布资产。

## 已确认事实

GPU Worker 曾在读取 JPEG Lossless Transfer Syntax `1.2.840.10008.1.2.4.70` 的 DICOM 像素时失败。上传阶段的 DICOM 头部检查允许 Case 到达 `READY`，但该状态不证明 Worker 可以解码 `pixel_array`。当时 GPU Python 缺少 `pylibjpeg` 和 `pylibjpeg-libjpeg`，导致两个历史 Job 以 `INFERENCE_FAILED` 结束；失败记录没有被改写为成功。

在同一隔离 Python 环境中安装 `pylibjpeg==2.1.0` 与 `pylibjpeg-libjpeg==2.4.0` 后，受控复核确认 JPEG Lossless 像素可解码，随后新建的 GPU Prediction 和 Occlusion Job 完成。PyTorch/CUDA 版本、冻结 checkpoint、FrozenBaseline 代码与 CPU/GPU 数值容差未改变。公开交接仅保留不关联原病例的 synthetic 浏览器与展示证据。

## 防止复发

`deploy/gpu/requirements-gpu-worker.txt` 固定 RTX 3090 MVP 观察到的直接运行依赖，包括两个解码包。新 GPU 节点必须在**最终启动 Worker 的同一 Python**中安装并执行 `pip check`、CUDA 检查，再使用获批准的 synthetic JPEG Lossless fixture 验证 `pydicom.dcmread(...).pixel_array`。当前仓库尚无该压缩 synthetic fixture，因此解码验收在新节点实测前保持 OPEN。具体步骤见 [GPU Worker Operations Guide](gpu_worker_mvp_operations.md)。

## 用户与运维边界

前端目前对失败 Job 主要显示通用 `Job failed.`，未向用户提供稳定错误分类或可执行建议；此 UX 仍为 OPEN。Worker 的安全异常类型和 traceback 观测也仍为 OPEN。日志不得输出凭据、签名 URL、原病例标识或像素数据。Case `READY`、Worker 存活与新 Job 完成应分别验证；它们不能相互替代。

CPU/GPU 固定数值一致性仍是 `FAIL / OPEN`。此次依赖修复及功能性 CUDA 完成不构成生产或临床验收。
