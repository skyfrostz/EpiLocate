from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import gradio as gr
from PIL import Image

from .inference import InferenceAdapter
from .jobs import JobManager, QueueFullError
from .storage import InputError, Storage
from algorithm.service import FrozenBaseline, validate_dicom


def build_ui(storage: Storage, adapter: InferenceAdapter, jobs: JobManager, baseline: FrozenBaseline | None = None) -> gr.Blocks:
    mode_label = "MOCK PNG/JPG + REAL DICOM" if baseline and baseline.ready() else "MOCK / DEVELOPMENT MODE"
    mode_notice = (
        "⚠️ **MOCK RESULT：仅用于接口开发，不得用于科研指标或临床判断。**"
        if adapter.mode == "mock"
        else "真实算法模式；系统仅用于科研与竞赛演示，不用于临床诊断。"
    )

    def run_image(image_path: str | None, progress=gr.Progress()):
        if not image_path:
            raise gr.Error("请先上传 PNG 或 JPG 图片。")
        if adapter.mode == "real" and not adapter.real_ready:
            raise gr.Error("真实算法尚未接入。请以 APP_MODE=mock 重启服务。")
        progress(0.05, desc="Validating input")
        try:
            data = Path(image_path).read_bytes()
            temporary_case = f"TEMP-{time.time_ns()}"
            relative_path, _ = storage.save_image_bytes(data, temporary_case)
            progress(0.2, desc="Queued")
            job = jobs.submit(relative_path)
        except InputError as exc:
            raise gr.Error(str(exc)) from exc
        except QueueFullError as exc:
            raise gr.Error(str(exc)) from exc

        while True:
            current = jobs.get(job.job_id)
            if current is None:
                raise gr.Error("任务记录不存在。")
            progress(current.progress / 100, desc=current.stage)
            if current.status in {"success", "failed"}:
                break
            time.sleep(0.1)

        _, result = jobs.result(job.job_id)
        if result is None:
            raise gr.Error("任务已结束但结果文件不存在。")
        payload = result.model_dump(by_alias=True, mode="json")
        result_file = jobs.result_file(job.job_id)
        if result.status == "failed":
            raise gr.Error(result.error.message if result.error else "推理失败。")
        return (
            result.prediction.predicted_class,
            result.prediction.probability,
            result.model_version,
            result.runtime_ms,
            "\n".join(result.warnings),
            payload,
            str(result_file) if result_file else None,
        )

    def run_dicom(path: str | None, with_occlusion: bool, progress=gr.Progress()):
        if not path:
            raise gr.Error("请先上传已去标识的单切片 CT DICOM。")
        if baseline is None or not baseline.ready():
            raise gr.Error("冻结 Baseline checkpoint 不可用。")
        data = Path(path).read_bytes()
        if len(data) > storage.max_upload_bytes:
            raise gr.Error("DICOM 文件超过上传限制。")
        try:
            rows, columns = validate_dicom(data, storage.max_image_pixels)
        except ValueError as exc:
            raise gr.Error("DICOM 格式或去标识检查失败。") from exc
        case_id, slice_id = "CASE-" + uuid.uuid4().hex[:16], "SLICE-" + uuid.uuid4().hex[:16]
        storage.save_dicom_bytes(data, case_id, slice_id, rows, columns, datetime.now(UTC).isoformat())
        try:
            stages = baseline.stages(storage.absolute_input_path(storage.get_case(case_id=case_id)["input_path"]))
        except Exception as exc:
            storage.delete_case(case_id)
            raise gr.Error("DICOM 预处理失败。") from exc
        preview = Image.fromarray((stages.normalized * 255).round().astype("uint8"))
        job = jobs.submit_analysis(case_id, slice_id, "occlusion" if with_occlusion else "prediction",
                                   [16, 32, 64] if with_occlusion else [])
        while True:
            current = jobs.get(job.job_id)
            progress(current.progress / 100, desc=current.stage)
            if current.status in {"success", "failed"}:
                break
            time.sleep(0.1)
        _, result = jobs.result(job.job_id)
        if current.status == "failed" or result is None:
            raise gr.Error("真实算法运行失败，请检查服务端日志。")
        return preview, {k: v for k, v in result.items() if k != "positions"}, result["source"]

    with gr.Blocks(title="新发传染病影像智能辅助诊断系统") as demo:
        gr.Markdown("# 新发传染病影像智能辅助诊断系统\n弱监督可解释病灶定位研究原型")
        gr.Markdown(
            f"**MODE:** {mode_label}　 **Contract:** 0.1　 **API:** `/api/health`",
        )
        gr.Markdown(mode_notice)
        with gr.Tab("DICOM / Frozen Baseline"):
            gr.Markdown("**真实冻结 Baseline：仅接受已去标识的单切片 CT DICOM。** 结果来源为 `LIVE_CASE`，候选图是模型遮挡响应假设。")
            dicom_input = gr.File(label="单切片 DICOM", file_types=[".dcm"], type="filepath")
            occlusion_toggle = gr.Checkbox(label="同时运行冻结 Stage 1 三尺度遮挡（耗时）", value=False)
            dicom_button = gr.Button("运行真实算法", variant="primary")
            dicom_preview = gr.Image(label="原始像素尺寸的窗宽窗位预览", interactive=False)
            dicom_source = gr.Textbox(label="结果来源", interactive=False)
            dicom_json = gr.JSON(label="真实算法结果")
            dicom_button.click(run_dicom, inputs=[dicom_input, occlusion_toggle],
                               outputs=[dicom_preview, dicom_json, dicom_source], api_name="run_dicom")
        with gr.Row():
            with gr.Column(scale=1):
                image_input = gr.Image(
                    label="上传 PNG/JPG",
                    type="filepath",
                    sources=["upload"],
                    height=420,
                )
                with gr.Row():
                    run_button = gr.Button("运行分析", variant="primary")
                    clear_button = gr.ClearButton(value="清空", components=[image_input])
            with gr.Column(scale=1):
                predicted_class = gr.Textbox(label="Class", interactive=False)
                probability = gr.Number(label="Probability", interactive=False)
                model_version = gr.Textbox(label="Model Version", interactive=False)
                runtime_ms = gr.Number(label="Runtime (ms)", interactive=False)
                warnings = gr.Textbox(label="Warnings", lines=4, interactive=False)

        with gr.Tabs():
            with gr.Tab("Classification"):
                gr.Markdown("分类结果显示在右侧结果区。")
            with gr.Tab("Occlusion Analysis"):
                gr.Markdown("真实 DICOM 单切片的 16/32/64 遮挡已接入；请在 DICOM 页勾选运行。PNG/JPG Mock 不产生遮挡结果。")
            with gr.Tab("Progressive Coarse Localization"):
                gr.Markdown("模块尚未接入（unavailable）。")
            with gr.Tab("LIME"):
                gr.Markdown("模块尚未接入（unavailable）。")
            with gr.Tab("Technical / JSON"):
                result_json = gr.JSON(label="InferenceResult v0.1")
                result_download = gr.File(label="下载 result.json", interactive=False)

        outputs = [
            predicted_class,
            probability,
            model_version,
            runtime_ms,
            warnings,
            result_json,
            result_download,
        ]
        run_button.click(run_image, inputs=[image_input], outputs=outputs, api_name="run_inference")
        clear_button.add(outputs)
    return demo
