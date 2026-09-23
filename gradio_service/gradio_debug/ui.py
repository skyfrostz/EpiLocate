from __future__ import annotations

import time
from pathlib import Path

import gradio as gr
from PIL import Image

from .inference import InferenceAdapter
from .jobs import JobManager, QueueFullError
from .storage import InputError, Storage


def build_ui(storage: Storage, adapter: InferenceAdapter, jobs: JobManager) -> gr.Blocks:
    mode_label = "MOCK / DEVELOPMENT MODE" if adapter.mode == "mock" else "REAL MODE"
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

    with gr.Blocks(title="新发传染病影像智能辅助诊断系统") as demo:
        gr.Markdown("# 新发传染病影像智能辅助诊断系统\n弱监督可解释病灶定位研究原型")
        gr.Markdown(
            f"**MODE:** {mode_label}　 **Contract:** 0.1　 **API:** `/api/health`",
        )
        gr.Markdown(mode_notice)
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
                gr.Markdown("模块尚未接入（unavailable）。")
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
