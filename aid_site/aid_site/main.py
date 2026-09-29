"""Presentation site with a deliberately disconnected, authenticated API."""

import hmac
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic.json_schema import models_json_schema

from . import schemas
from .db import SESSION_SECONDS, delete_session, find_session, initialize, new_session, verify_user

BASE = Path(__file__).resolve().parent
app = FastAPI(title="辅助诊断项目网站接口", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.on_event("startup")
def startup():
    initialize()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def page_auth(request: Request):
    session = find_session(request.cookies.get("__Host-aid-session"))
    if session:
        return session, None
    next_path = request.url.path
    if request.url.query:
        next_path += "?" + request.url.query
    return None, RedirectResponse("/login?next=" + quote(next_path, safe=""), status_code=303)


def api_auth(request: Request):
    session = find_session(request.cookies.get("__Host-aid-session"))
    if session:
        return session, None
    return None, JSONResponse({"code": "UNAUTHENTICATED", "message": "请先登录。"}, status_code=401)


def valid_next(value: str):
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value and "\n" not in value else "/"


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin == str(request.base_url).rstrip("/")


def csrf_ok(request: Request, expected: str | None, supplied: str | None):
    return bool(expected and supplied and same_origin(request) and hmac.compare_digest(expected, supplied))


def page(request: Request, template: str, title: str, nav: str, **extra):
    session, redirect = page_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, template, {"title": title, "nav": nav, "username": session["username"], "csrf_token": session["csrf_token"], **extra})


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/"):
    if find_session(request.cookies.get("__Host-aid-session")):
        return RedirectResponse(valid_next(next), status_code=303)
    token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(request, "login.html", {"title": "登录", "csrf_token": token, "next": valid_next(next), "error": None})
    response.set_cookie("__Host-aid-login-csrf", token, max_age=600, secure=True, httponly=True, samesite="strict", path="/")
    return response


@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))[:64]
    password = str(form.get("password", ""))
    next_path = valid_next(str(form.get("next", "/")))
    submitted = str(form.get("csrf_token", ""))
    cookie_token = request.cookies.get("__Host-aid-login-csrf")
    if not csrf_ok(request, cookie_token, submitted):
        return JSONResponse({"code": "CSRF_REJECTED", "message": "页面已过期，请刷新后重试。"}, status_code=403)
    user = verify_user(username, password)
    if not user:
        response = templates.TemplateResponse(request, "login.html", {"title": "登录", "csrf_token": cookie_token, "next": next_path, "error": "账号或密码不正确。"}, status_code=401)
        return response
    token, _ = new_session(user["id"])
    response = RedirectResponse(next_path, status_code=303)
    response.set_cookie("__Host-aid-session", token, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="strict", path="/")
    response.delete_cookie("__Host-aid-login-csrf", path="/")
    return response


@app.post("/logout", include_in_schema=False)
async def logout(request: Request):
    session, redirect = page_auth(request)
    if redirect:
        return redirect
    form = await request.form()
    if not csrf_ok(request, session["csrf_token"], str(form.get("csrf_token", ""))):
        return JSONResponse({"code": "CSRF_REJECTED"}, status_code=403)
    delete_session(request.cookies.get("__Host-aid-session"))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("__Host-aid-session", path="/")
    return response


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def overview(request: Request):
    return page(request, "overview.html", "项目概览", "overview")


@app.get("/route", response_class=HTMLResponse, include_in_schema=False)
def route(request: Request):
    return page(request, "route.html", "技术路线", "route")


@app.get("/system", response_class=HTMLResponse, include_in_schema=False)
def system(request: Request):
    return page(request, "system.html", "系统规划", "system")


@app.get("/evaluation", response_class=HTMLResponse, include_in_schema=False)
def evaluation(request: Request):
    return page(request, "evaluation.html", "评测计划", "evaluation")


@app.get("/progress", response_class=HTMLResponse, include_in_schema=False)
def progress(request: Request):
    return page(request, "progress.html", "项目进度", "progress")


@app.get("/api-guide", response_class=HTMLResponse, include_in_schema=False)
def api_guide(request: Request):
    return page(request, "api_guide.html", "接口说明", "api")


@app.get("/api/v1/openapi.json", include_in_schema=False)
def openapi_document(request: Request):
    _, denied = api_auth(request)
    if denied:
        return denied
    return JSONResponse(app.openapi())


@app.get("/api/v1/capabilities", tags=["Capabilities"], summary="查询当前能力状态", response_model=schemas.CapabilityReport)
def capabilities(request: Request):
    session, denied = api_auth(request)
    if denied:
        return denied
    return {
        "api_version": "v1",
        "site_mode": "PROJECT_PRESENTATION",
        "capabilities": {
            "image_submission": "NOT_CONNECTED",
            "analysis_tasks": "NOT_CONNECTED",
            "results": "NOT_CONNECTED",
            "doctor_feedback": "NOT_CONNECTED",
        },
        "accepts_real_images": False,
        "stores_business_payloads": False,
        "csrf_token": session["csrf_token"],
    }


def not_connected(request: Request, capability: str):
    session, denied = api_auth(request)
    if denied:
        return denied
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not csrf_ok(request, session["csrf_token"], request.headers.get("x-csrf-token")):
        return JSONResponse({"code": "CSRF_REJECTED", "message": "缺少或无效的 CSRF 令牌。"}, status_code=403)
    payload = schemas.NotConnectedError(capability=capability)
    return JSONResponse(payload.model_dump(), status_code=503, headers={"Retry-After": "86400"})


NOT_CONNECTED_RESPONSE = {503: {"model": schemas.NotConnectedError, "description": "Capability is not connected; no business payload is read or stored."}}


@app.post("/api/v1/images", tags=["Future integration"], summary="提交影像（预留）", responses=NOT_CONNECTED_RESPONSE,
          openapi_extra={"requestBody": {"description": "Future ImageSubmission metadata contract. Real image upload is disabled.", "content": {"application/json": {"schema": {"type": "object", "properties": {"metadata": {"type": "object"}}}}}}})
def submit_image(request: Request):
    return not_connected(request, "image_submission")


@app.post("/api/v1/analysis-tasks", tags=["Future integration"], summary="创建分析任务（预留）", responses=NOT_CONNECTED_RESPONSE,
          openapi_extra={"requestBody": {"description": "Future AnalysisTaskCreate contract", "content": {"application/json": {"schema": {"type": "object", "properties": {"image_id": {"type": "string"}, "requested_stages": {"type": "array", "items": {"type": "string"}}}}}}}})
def create_task(request: Request):
    return not_connected(request, "analysis_tasks")


@app.get("/api/v1/analysis-tasks/{task_id}", tags=["Future integration"], summary="查询分析任务（预留）", responses=NOT_CONNECTED_RESPONSE)
def get_task(request: Request, task_id: str):
    return not_connected(request, "analysis_tasks")


@app.get("/api/v1/results/{result_id}", tags=["Future integration"], summary="查询分析结果（预留）", responses=NOT_CONNECTED_RESPONSE)
def get_result(request: Request, result_id: str):
    return not_connected(request, "results")


@app.post("/api/v1/doctor-feedback", tags=["Future integration"], summary="提交医生反馈（预留）", responses=NOT_CONNECTED_RESPONSE,
          openapi_extra={"requestBody": {"description": "Future DoctorFeedback contract", "content": {"application/json": {"schema": {"type": "object", "properties": {"result_id": {"type": "string"}, "corrections": {"type": "array", "items": {"type": "object"}}}}}}}})
def doctor_feedback(request: Request):
    return not_connected(request, "doctor_feedback")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


_fastapi_openapi = app.openapi


def contract_openapi():
    """Include future type definitions while keeping placeholder handlers body-free."""
    document = _fastapi_openapi()
    models = [
        schemas.ImageMetadata, schemas.ImageSubmission, schemas.AnalysisTaskCreate,
        schemas.AnalysisTask, schemas.LocalizationRegion, schemas.Explanation,
        schemas.AnalysisResult, schemas.DoctorCorrection, schemas.DoctorFeedback,
    ]
    _, definitions = models_json_schema(
        [(model, "validation") for model in models],
        ref_template="#/components/schemas/{model}",
    )
    document.setdefault("components", {}).setdefault("schemas", {}).update(definitions["$defs"])
    for path, model in [
        ("/api/v1/images", "ImageSubmission"),
        ("/api/v1/analysis-tasks", "AnalysisTaskCreate"),
        ("/api/v1/doctor-feedback", "DoctorFeedback"),
    ]:
        operation = document["paths"][path]["post"]
        operation["requestBody"]["content"]["application/json"]["schema"] = {"$ref": f"#/components/schemas/{model}"}
        operation["x-current-state"] = "NOT_CONNECTED"
    for path in ["/api/v1/analysis-tasks/{task_id}", "/api/v1/results/{result_id}"]:
        document["paths"][path]["get"]["x-current-state"] = "NOT_CONNECTED"
    app.openapi_schema = document
    return document


app.openapi = contract_openapi
