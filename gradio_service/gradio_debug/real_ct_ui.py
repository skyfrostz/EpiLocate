"""Gradio presentation for the real, single-slice P0 HTTP workflow."""
from __future__ import annotations

import io
import re
from pathlib import Path

import gradio as gr
from PIL import Image

from .api_client import APIError, P0Client
from .spatial import aligned_overlay


IDENTIFIER = re.compile(r"^[A-Za-z0-9-]{1,80}$")
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _id(value: str, label: str) -> str:
    if not value or not IDENTIFIER.fullmatch(value):
        raise APIError("INVALID_REQUEST", f"{label} 无效。")
    return value


def _source(result: dict, case_id: str, slice_id: str) -> None:
    if result.get("source") != "LIVE_CASE" or result.get("case_id") != case_id or result.get("slice_id") != slice_id:
        raise APIError("SOURCE_MISMATCH", "结果来源或切片 ID 不匹配，已拒绝展示。")
    prediction = result.get("prediction")
    if prediction and (prediction.get("source") != "LIVE_CASE" or prediction.get("unit") != "slice"
                       or prediction.get("slice_id") != slice_id):
        raise APIError("SOURCE_MISMATCH", "分类结果不是当前真实单切片预测。")


class RealCTController:
    def __init__(self, client: P0Client | None = None):
        self.client = client or P0Client()

    def upload(self, path: str):
        if not path or Path(path).suffix.lower() != ".dcm":
            raise APIError("INVALID_REQUEST", "请选择单个 .dcm 文件。")
        caps = self.client.capabilities()["capabilities"]
        if caps["baseline_slice_prediction"]["state"] != "available":
            raise APIError("MODEL_UNAVAILABLE", "冻结 Baseline 在当前服务不可用。")
        accepted = self.client.upload(path)
        case_id = _id(accepted["case_id"], "case_id")
        parse_job = self.client.job(_id(accepted["job_id"], "解析 Job ID"))
        case = self.client.case(case_id)
        records = self.client.slices(case_id)["slices"]
        if len(records) != 1 or records[0]["case_id"] != case_id:
            raise APIError("CASE_MISMATCH", "服务未返回恰好一个匹配的切片。")
        record = records[0]
        slice_id = _id(record["slice_id"], "slice_id")
        preview = Image.open(io.BytesIO(self.client.preview(slice_id))).copy()
        if preview.size != (record["geometry"]["raw_width"], record["geometry"]["raw_height"]):
            raise APIError("GEOMETRY_MISMATCH", "CT 预览尺寸与空间元数据不一致。")
        return case_id, slice_id, preview, record["geometry"], (
            f"上传：{accepted['status']} · 解析 Job：{parse_job['status']} · "
            f"预处理：{case['preprocessing_status']} · 来源：{case['source']}"
        )

    def submit(self, kind: str, case_id: str, slice_id: str):
        case_id, slice_id = _id(case_id, "case_id"), _id(slice_id, "slice_id")
        records = self.client.slices(case_id)["slices"]
        if len(records) != 1 or records[0]["slice_id"] != slice_id:
            raise APIError("CASE_MISMATCH", "case_id 与 slice_id 不匹配。")
        caps = self.client.capabilities()["capabilities"]
        capability = "baseline_slice_prediction" if kind == "prediction" else "single_slice_occlusion"
        if caps[capability]["state"] != "available":
            raise APIError("MODEL_UNAVAILABLE", "此功能在当前服务不可用。")
        accepted = self.client.predict(case_id, slice_id) if kind == "prediction" else self.client.occlude(case_id, slice_id)
        if accepted.get("case_id") != case_id:
            raise APIError("CASE_MISMATCH", "Job 所属病例不匹配。")
        return _id(accepted["job_id"], "Job ID")

    def inspect_job(self, job_id: str, case_id: str, slice_id: str):
        job = self.client.job(_id(job_id, "Job ID"))
        if job.get("case_id") != _id(case_id, "case_id") or job.get("job_type") not in {"PREDICTION", "OCCLUSION"}:
            raise APIError("JOB_MISMATCH", "Job 不属于当前病例或不是单切片分析任务。")
        status = job.get("status")
        if status not in {"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}:
            raise APIError("INVALID_STATUS", "服务返回未知 Job 状态。")
        message = f"{job['job_type']} · {status} · 进度 {job['progress']:.0%} · 已处理 {job['processed_slices']}/{job['total_slices']} 切片"
        if status in {"FAILED", "CANCELLED"}:
            message += f" · {job.get('error_code') or status}: {job.get('error_message') or '任务未产生结果。'}"
            return message, None
        if status != "COMPLETED":
            return message, None
        result = self.client.result(job_id)
        _source(result, case_id, slice_id)
        return message, result

    def scale_view(self, result: dict, case_id: str, slice_id: str, scale: int):
        if not result:
            raise APIError("RESULT_NOT_FOUND", "请先完成三尺度遮挡任务。")
        _source(result, case_id, slice_id)
        summaries = {s["block_size"]: s for s in result.get("scale_summaries", [])}
        if scale not in summaries:
            raise APIError("RESULT_NOT_FOUND", "此结果没有所选尺度。")
        summary = summaries[scale]
        record = self.client.slices(case_id)["slices"][0]
        if record["slice_id"] != slice_id:
            raise APIError("CASE_MISMATCH", "切片已变化，拒绝复用热力图。")
        layer = summary.get("response_layer")
        if not layer:
            raise APIError("RESULT_NOT_FOUND", "此尺度没有响应图资产。")
        preview_bytes = self.client.preview(slice_id)
        response_bytes = self.client.asset(result["result_id"], layer["asset_id"])
        response = Image.open(io.BytesIO(response_bytes)).copy()
        overlay = aligned_overlay(preview_bytes, response_bytes, record["geometry"], layer)
        candidate = None
        if summary["candidate_status"] == "valid" and summary.get("candidate_layer"):
            candidate_layer = summary["candidate_layer"]
            if candidate_layer["coordinate_space"] != "ALGORITHM_224":
                raise APIError("GEOMETRY_MISMATCH", "候选图坐标空间不匹配。")
            candidate = Image.open(io.BytesIO(self.client.asset(result["result_id"], candidate_layer["asset_id"]))).copy()
        cursor, count, max_drop = 0, 0, None
        while True:
            page = self.client.positions(result["result_id"], scale, cursor)
            values = page["positions"]
            count += len(values)
            if values:
                maximum = max(p["decision_confidence_drop"] for p in values)
                max_drop = maximum if max_drop is None else max(max_drop, maximum)
            cursor = page["next_cursor"]
            if cursor is None:
                break
        note = (
            f"**{scale} px** · 候选响应有效性：`{summary['candidate_status']}` · "
            f"遮挡步长：{summary['stride']} px · 遮挡前正类概率：{summary['baseline_positive_probability']:.6f} · "
            f"中位绝对正类概率变化：{summary['median_absolute_probability_change']:.6f} · "
            f"预测翻转率：{summary['flip_rate']:.4f} · 遮挡位置：{count} · "
            f"最大同类决策置信度变化：{max_drop if max_drop is not None else '不可用'} · "
            f"候选面积占比：{summary['candidate_area_fraction'] if summary['candidate_area_fraction'] is not None else '不可用'}。\n\n"
            f"图层值域：{layer['value_min']:.6f}–{layer['value_max']:.6f}；"
            "橙色仅表示模型遮挡响应假设，并非真实病灶。响应 PNG 为单图显示归一化；"
            "定量值来自位置 API。原始 CT、算法输入、响应图和显示坐标按后端空间元数据映射；叠加图仅作显示插值。"
        )
        return response, overlay, candidate, note


def prediction_text(result: dict | None) -> str:
    if not result:
        return "单切片分类：等待真实 Job 结果。"
    p = result["prediction"]
    return (f"**单切片预测（非患者级）** · 来源：`{result['source']}` · 推理状态：`{p['inference_status']}`  \n"
            f"类别：**{p['class_label']}**（{p['predicted_class']}） · 正类概率：**{p['positive_probability']:.6f}**  \n"
            f"模型：`{p['model_version']}` · 预处理：`{p['preprocessing_version']}`")


def build_real_ct_tab():
    controller = RealCTController()
    with gr.Tab("真实单切片 DICOM"):
        gr.Markdown("### 真实单切片 DICOM · 冻结 Baseline / Stage 1\n研究用途，非临床诊断。仅上传已去标识的单张 CT DICOM。")
        saved = gr.BrowserState(default_value={}, storage_key="epilocate-p0-real-job-v1")
        current_result = gr.State(None)
        geometry = gr.State(None)
        with gr.Row():
            dicom = gr.File(label="单切片 .dcm", file_types=[".dcm"], type="filepath")
            upload_button = gr.Button("上传并预处理", variant="primary")
        upload_status = gr.Markdown("上传：等待文件。")
        with gr.Row():
            case_box = gr.Textbox(label="匿名 case_id", interactive=False)
            slice_box = gr.Textbox(label="slice_id", interactive=False)
            job_box = gr.Textbox(label="Job ID（刷新后可从浏览器恢复，也可手动填入）")
        preview = gr.Image(label="原始 CT 窗宽窗位预览 · 单切片", interactive=False, height=300)
        with gr.Row():
            predict_button = gr.Button("运行 Baseline 单切片分类")
            occlude_button = gr.Button("运行 16 / 32 / 64 px 遮挡")
            query_button = gr.Button("查询 Job")
        job_status = gr.Markdown("Job：尚未提交。")
        classification = gr.Markdown(prediction_text(None))
        gr.Markdown("PLANNED / UNAVAILABLE：NIfTI、多切片及患者级汇总、Robust、稳定粗定位、LIME、医生反馈。")
        scale = gr.Radio([16, 32, 64], value=16, label="遮挡尺度（像素）")
        with gr.Row():
            response_image = gr.Image(label="224×224 响应图", interactive=False)
            overlay_image = gr.Image(label="CT + 模型响应叠加 · 显示插值", interactive=False)
            candidate_image = gr.Image(label="Top-10% 候选响应（无效时不绘制）", interactive=False)
        scale_note = gr.Markdown("等待遮挡结果。")

        def upload_action(path, state):
            try:
                case, slice_id, image, geom, message = controller.upload(path)
            except (APIError, OSError, ValueError) as exc:
                raise gr.Error(str(exc)) from exc
            return (case, slice_id, image, geom, message, "", "Job：尚未提交。",
                    prediction_text(None), None, None, None, "等待遮挡结果。", None,
                    {"case_id": case, "slice_id": slice_id})

        upload_button.click(upload_action, [dicom, saved],
                            [case_box, slice_box, preview, geometry, upload_status, job_box, job_status,
                             classification, response_image, overlay_image, candidate_image, scale_note,
                             current_result, saved])

        def submit_action(kind, case, slice_id, state):
            try:
                job_id = controller.submit(kind, case, slice_id)
            except APIError as exc:
                raise gr.Error(str(exc)) from exc
            return job_id, f"{kind.upper()} · PENDING · Job ID {job_id}", {**(state or {}), "case_id": case,
                                                                           "slice_id": slice_id, "job_id": job_id}

        predict_button.click(lambda c, s, st: submit_action("prediction", c, s, st),
                             [case_box, slice_box, saved], [job_box, job_status, saved])
        occlude_button.click(lambda c, s, st: submit_action("occlusion", c, s, st),
                             [case_box, slice_box, saved], [job_box, job_status, saved])

        def query_action(job_id, case, slice_id, state):
            if not job_id:
                return "Job：尚未提交。", gr.skip(), gr.skip(), state
            if (state or {}).get("completed_job") == job_id:
                return gr.skip(), gr.skip(), gr.skip(), state
            try:
                message, result = controller.inspect_job(job_id, case, slice_id)
            except APIError as exc:
                return f"**查询失败：{exc}**", gr.skip(), gr.skip(), state
            if result:
                return message, prediction_text(result), result, {**(state or {}), "job_id": job_id,
                                                                   "case_id": case, "slice_id": slice_id,
                                                                   "completed_job": job_id}
            return message, gr.skip(), gr.skip(), state

        query_button.click(query_action, [job_box, case_box, slice_box, saved],
                           [job_status, classification, current_result, saved])
        timer = gr.Timer(2)
        timer.tick(query_action, [job_box, case_box, slice_box, saved],
                   [job_status, classification, current_result, saved], show_progress="hidden")

        def restore_action(state):
            if not state or not state.get("case_id") or not state.get("slice_id"):
                return "", "", "", None, "上传：等待文件。", "Job：尚未提交。", prediction_text(None), None
            case, slice_id, job_id = state["case_id"], state["slice_id"], state.get("job_id", "")
            try:
                records = controller.client.slices(_id(case, "case_id"))["slices"]
                if len(records) != 1 or records[0]["slice_id"] != slice_id:
                    raise APIError("CASE_MISMATCH", "保存的切片已失效。")
                image = Image.open(io.BytesIO(controller.client.preview(slice_id))).copy()
                if job_id:
                    message, result = controller.inspect_job(job_id, case, slice_id)
                else:
                    message, result = "Job：尚未提交。", None
                return case, slice_id, job_id, image, "已恢复当前单切片。", message, prediction_text(result), result
            except (APIError, OSError, ValueError) as exc:
                return case, slice_id, job_id, None, f"恢复失败：{exc}", f"查询失败：{exc}", prediction_text(None), None

        def scale_action(result, case, slice_id, selected):
            if not result or not result.get("scale_summaries"):
                return None, None, None, "等待遮挡结果。"
            try:
                return controller.scale_view(result, case, slice_id, selected)
            except (APIError, ValueError, OSError) as exc:
                return None, None, None, f"图层加载失败：{exc}"

        scale.change(scale_action, [current_result, case_box, slice_box, scale],
                     [response_image, overlay_image, candidate_image, scale_note])
        current_result.change(scale_action, [current_result, case_box, slice_box, scale],
                              [response_image, overlay_image, candidate_image, scale_note])
    return restore_action, saved, [case_box, slice_box, job_box, preview, upload_status,
                                   job_status, classification, current_result]
