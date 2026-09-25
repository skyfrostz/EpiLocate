"""Loopback-only Gradio UI for a separately token-protected P0 API.

This process owns no DICOM jobs or frozen model. Its Python callbacks use
P0Client and the server-side EPILOCATE_API_BEARER_TOKEN to reach the API.
"""
from __future__ import annotations

import os
from pathlib import Path

ui_root = Path(os.environ["APP_DATA_ROOT"]).resolve()
ui_password = os.environ["EPILOCATE_UI_PASSWORD"]
os.environ["GRADIO_TEMP_DIR"] = str(ui_root / "storage" / "temp")

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .real_ct_ui import build_real_ct_tab


api = FastAPI(title="EpiLocate local P0 Gradio UI")


@api.middleware("http")
async def loopback_only(request: Request, call_next):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return JSONResponse(status_code=403, content={"code": "FORBIDDEN", "message": "Local UI only."})
    return await call_next(request)


@api.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/gradio")


with gr.Blocks(title="EpiLocate P0 · 本机真实 DICOM") as ui:
    gr.Markdown("# EpiLocate P0 · 真实单切片 DICOM\n仅限本机研究演示；API 令牌保存在 Python 服务端。")
    restore, saved, outputs = build_real_ct_tab()
    ui.load(fn=restore, inputs=saved, outputs=outputs)

app = gr.mount_gradio_app(
    api,
    ui,
    path="/gradio",
    auth=("local", ui_password),
    allowed_paths=[str(ui_root / "storage" / "temp")],
    blocked_paths=[str(ui_root / "storage" / "uploads"), str(ui_root / "storage" / "results")],
    max_file_size=f"{os.getenv('APP_MAX_UPLOAD_MIB', '20')}mb",
)
