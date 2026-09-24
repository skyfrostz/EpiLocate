from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import hmac
from typing import Any, Mapping, Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .bundle import Candidate, ReviewBundle, ReviewCase
from .config import Settings
from .db import Database, VersionConflict
from .export import FinalExportNotReady, build_export_rows, render_csv
from .review_logic import consensus_status, recommendation, validate_decision
from .security import new_token, token_hash, verify_password, verify_token_hash


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
CSRF_COOKIE = "epilocate_csrf"


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=0, ge=0)
    observations: dict[str, str] = Field(default_factory=dict)
    decision: str = "PENDING"
    selected_series_uid: str = ""
    reason: str = ""
    image_evidence_reviewed: bool = False
    metadata_evidence_reviewed: bool = False


class FinalDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Optional[int] = Field(default=None, ge=1)
    decision: str
    selected_series_uid: str = ""
    reason: str
    image_evidence_reviewed: bool
    metadata_evidence_reviewed: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.bundle = ReviewBundle.load(settings.bundle_path, verify_files=True)
        application.state.db.initialize()
        yield

    app = FastAPI(
        title="EpiLocate Review Server",
        docs_url=None if settings.production else "/docs",
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
        debug=False,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = Database(settings.database_path)
    app.state.bundle = None
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def origin_and_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in settings.allowed_origins:
                return JSONResponse({"detail": "origin is not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def db(request: Request) -> Database:
        return request.app.state.db

    def bundle(request: Request) -> ReviewBundle:
        loaded = request.app.state.bundle
        if loaded is None:
            raise HTTPException(503, "bundle is not loaded")
        return loaded

    def current_user(request: Request, database: Database = Depends(db)) -> dict[str, Any]:
        raw_token = request.cookies.get(settings.session_cookie_name, "")
        if not raw_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        user = database.user_by_session_hash(token_hash(raw_token))
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
        return user

    async def csrf_user(
        request: Request,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        request_token = request.headers.get("X-CSRF-Token", "")
        if not request_token and request.headers.get("content-type", "").startswith(
            "application/x-www-form-urlencoded"
        ):
            form = await request.form()
            request_token = str(form.get("_csrf", ""))
        if (
            not cookie_token
            or not request_token
            or not hmac.compare_digest(cookie_token, request_token)
            or not verify_token_hash(str(user["csrf_token_hash"]), request_token)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
        return user

    def reviewer_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] != "reviewer":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "reviewer role required")
        return user

    def csrf_reviewer(user: dict[str, Any] = Depends(csrf_user)) -> dict[str, Any]:
        if user["role"] != "reviewer":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "reviewer role required")
        return user

    def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
        return user

    def csrf_admin(user: dict[str, Any] = Depends(csrf_user)) -> dict[str, Any]:
        if user["role"] != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
        return user

    @app.exception_handler(VersionConflict)
    async def version_conflict_handler(_request: Request, exc: VersionConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        loaded = request.app.state.bundle is not None
        return {"status": "ok" if loaded else "starting"}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False)
    def index(request: Request):
        raw_token = request.cookies.get(settings.session_cookie_name, "")
        user = db(request).user_by_session_hash(token_hash(raw_token)) if raw_token else None
        if not user:
            return RedirectResponse("/login", status_code=303)
        return RedirectResponse("/admin" if user["role"] == "admin" else "/review", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return _template(request, "login.html", {"error": None})

    @app.post("/login")
    async def login(request: Request, database: Database = Depends(db)):
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        source_ip = _source_ip(request, settings)
        if database.login_is_rate_limited(username, source_ip):
            return _template(request, "login.html", {"error": "登录尝试过多，请稍后重试。"}, 429)
        user = database.user_by_username(username)
        valid = bool(user and verify_password(str(user["password_hash"]), password))
        database.record_login_attempt(username, source_ip, valid)
        if not valid:
            return _template(request, "login.html", {"error": "用户名或密码错误。"}, 401)
        session_token = new_token()
        csrf_token = new_token()
        database.create_session(
            int(user["id"]), token_hash(session_token), token_hash(csrf_token), settings.session_hours
        )
        response = RedirectResponse("/admin" if user["role"] == "admin" else "/review", status_code=303)
        response.set_cookie(
            settings.session_cookie_name,
            session_token,
            max_age=settings.session_hours * 3600,
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            max_age=settings.session_hours * 3600,
            secure=settings.secure_cookies,
            httponly=False,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/logout")
    def logout(
        request: Request,
        database: Database = Depends(db),
        _user: dict[str, Any] = Depends(csrf_user),
    ):
        raw_token = request.cookies.get(settings.session_cookie_name, "")
        if raw_token:
            database.revoke_session(token_hash(raw_token))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(settings.session_cookie_name, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return response

    @app.get("/review", response_class=HTMLResponse)
    def review_index(
        request: Request,
        user: dict[str, Any] = Depends(reviewer_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        assignment_rows = database.assignments(int(user["id"]))
        cases = []
        for row in assignment_rows:
            case = review_bundle.get_case(str(row["case_id"]))
            if case:
                cases.append({**_case_dict(case), **row})
        progress = {
            "submitted": sum(row.get("status") == "SUBMITTED" for row in assignment_rows),
            "drafts": sum(row.get("status") == "DRAFT" for row in assignment_rows),
            "total": len(assignment_rows),
        }
        progress["percent"] = round(100 * progress["submitted"] / progress["total"]) if progress["total"] else 0
        return _template(
            request,
            "review.html",
            {"user": _public_user(user), "csrf_token": request.cookies.get(CSRF_COOKIE, ""), "cases": cases, "progress": progress},
        )

    @app.get("/review/{case_id}", response_class=HTMLResponse)
    def review_case(
        case_id: str,
        request: Request,
        user: dict[str, Any] = Depends(reviewer_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        assignment = database.assignment(int(user["id"]), case_id)
        case = review_bundle.get_case(case_id)
        if not assignment or not case:
            raise HTTPException(404, "case not found")
        review = database.review(int(user["id"]), case_id) or _empty_review()
        ordered = _ordered_candidates(case, assignment, review_bundle)
        case_context = _case_dict(case)
        case_index = next(
            (index for index, item in enumerate(review_bundle.cases) if item.case_id == case_id), 0
        )
        case_context.update(
            {
                "index": case_index + 1,
                "total": len(review_bundle.cases),
                "previous_id": review_bundle.cases[case_index - 1].case_id if case_index > 0 else None,
                "next_id": (
                    review_bundle.cases[case_index + 1].case_id
                    if case_index + 1 < len(review_bundle.cases)
                    else None
                ),
                "duplicate_warning": case_id == "TIE-012",
            }
        )
        rec = recommendation(case.case_type, review["observations"], case_id=case_id).as_dict(
            [item["series_uid"] for item in ordered if item["selectable"]]
        )
        return _template(
            request,
            "review_case.html",
            {
                "user": _public_user(user),
                "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "case": case_context,
                "candidates": ordered,
                "review": review,
                "assignment": assignment,
                "read_only": bool(database.final_decision(case_id)),
                "recommendation": rec,
            },
        )

    @app.get("/review/{case_id}/viewer", response_class=HTMLResponse)
    def reviewer_viewer(
        case_id: str,
        request: Request,
        user: dict[str, Any] = Depends(reviewer_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        assignment = database.assignment(int(user["id"]), case_id)
        case = review_bundle.get_case(case_id)
        if not assignment or not case:
            raise HTTPException(404, "case not found")
        return _template(
            request,
            "viewer.html",
            {
                "user": _public_user(user),
                "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "case": _case_dict(case),
                "candidates": _ordered_candidates(case, assignment, review_bundle),
                "return_url": f"/review/{case_id}",
            },
        )

    @app.patch("/api/reviews/{case_id}/draft")
    def save_draft(
        case_id: str,
        payload: ReviewPayload,
        user: dict[str, Any] = Depends(csrf_reviewer),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        return _save_review_payload(database, review_bundle, user, case_id, payload, submit=False)

    @app.post("/api/reviews/{case_id}/submit")
    def submit_review(
        case_id: str,
        payload: ReviewPayload,
        user: dict[str, Any] = Depends(csrf_reviewer),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        return _save_review_payload(database, review_bundle, user, case_id, payload, submit=True)

    @app.post("/api/reviews/{case_id}/reopen")
    def reopen_review(
        case_id: str,
        user: dict[str, Any] = Depends(csrf_reviewer),
        database: Database = Depends(db),
    ):
        try:
            review = database.reopen_review(int(user["id"]), case_id)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True, "review": review, "version": review["version"]}

    @app.get("/media/{asset_id}")
    def media(
        asset_id: str,
        user: dict[str, Any] = Depends(current_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        asset = review_bundle.assets.get(asset_id)
        case = review_bundle.case_for_asset(asset_id)
        if not asset or not case:
            raise HTTPException(404, "asset not found")
        if user["role"] == "reviewer" and not database.assignment(int(user["id"]), case.case_id):
            raise HTTPException(404, "asset not found")
        if user["role"] not in {"reviewer", "admin"}:
            raise HTTPException(403, "role not allowed")
        response = Response(status_code=200, media_type="image/png")
        response.headers["X-Accel-Redirect"] = "/__epilocate_media/" + quote(
            asset.relative_path, safe="/"
        )
        response.headers["Content-Disposition"] = "inline"
        return response

    @app.get("/admin", response_class=HTMLResponse)
    def admin_index(
        request: Request,
        user: dict[str, Any] = Depends(admin_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        summary_by_case = {row["case_id"]: row for row in database.all_review_summaries()}
        final_by_case = database.all_final_decisions()
        case_summaries = []
        status_counts = {"CONSENSUS": 0, "CONFLICT": 0, "WAITING": 0}
        has_defer_count = 0
        for case in review_bundle.cases:
            reviews = database.submitted_reviews_for_case(case.case_id)
            consensus = consensus_status(reviews)
            status_counts[consensus["status"]] += 1
            has_defer_count += int(consensus["has_defer"])
            final = final_by_case.get(case.case_id)
            submitted_count = int(summary_by_case.get(case.case_id, {}).get("submitted_count") or 0)
            case_summaries.append(
                {
                    **_case_dict(case),
                    **summary_by_case.get(case.case_id, {"submitted_count": 0, "defer_count": 0}),
                    "consensus": consensus,
                    "status": consensus["status"],
                    "has_defer": consensus["has_defer"],
                    "finalized": bool(final),
                    "reviewer_1_submitted": submitted_count >= 1,
                    "reviewer_2_submitted": submitted_count >= 2,
                    "final_decision": final,
                }
            )
        summary = {
            "finalized": len(final_by_case),
            "total": len(review_bundle.cases),
            "consensus": status_counts["CONSENSUS"],
            "conflict": status_counts["CONFLICT"],
            "waiting": status_counts["WAITING"],
            "has_defer": has_defer_count,
        }
        final_export_ready = len(final_by_case) == len(review_bundle.cases) and all(
            value.get("decision") != "DEFER" for value in final_by_case.values()
        )
        return _template(
            request,
            "admin.html",
            {
                "user": _public_user(user), "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "case_summaries": case_summaries, "summary": summary,
                "final_export_ready": final_export_ready,
            },
        )

    @app.get("/admin/cases/{case_id}", response_class=HTMLResponse)
    def admin_case(
        case_id: str,
        request: Request,
        user: dict[str, Any] = Depends(admin_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        case = review_bundle.get_case(case_id)
        if not case:
            raise HTTPException(404, "case not found")
        reviews = database.submitted_reviews_for_case(case_id)
        consensus = consensus_status(reviews)
        final = database.final_decision(case_id)
        prefill = {
            "decision": consensus.get("decision") or "",
            "selected_series_uid": consensus.get("selected_series_uid") or "",
            "reason": "",
        }
        return _template(
            request,
            "admin_case.html",
            {
                "user": _public_user(user), "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "case": _case_dict(case),
                "candidates": [
                    _candidate_dict(item, review_bundle, display_position=index)
                    for index, item in enumerate(case.candidates)
                ],
                "reviews": reviews, "consensus": consensus, "final_decision": final, "prefill": prefill,
            },
        )

    @app.get("/admin/cases/{case_id}/viewer", response_class=HTMLResponse)
    def admin_viewer(
        case_id: str,
        request: Request,
        user: dict[str, Any] = Depends(admin_user),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        case = review_bundle.get_case(case_id)
        if not case:
            raise HTTPException(404, "case not found")
        return _template(
            request,
            "viewer.html",
            {
                "user": _public_user(user),
                "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "case": _case_dict(case),
                "candidates": [
                    _candidate_dict(item, review_bundle, display_position=index)
                    for index, item in enumerate(case.candidates)
                ],
                "return_url": f"/admin/cases/{case_id}",
            },
        )

    @app.post("/api/admin/final-decisions/{case_id}")
    def save_final(
        case_id: str,
        payload: FinalDecisionPayload,
        user: dict[str, Any] = Depends(csrf_admin),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        case = review_bundle.get_case(case_id)
        if not case:
            raise HTTPException(404, "case not found")
        submitted = [
            item for item in database.submitted_reviews_for_case(case_id) if item["status"] == "SUBMITTED"
        ]
        if len(submitted) < 2:
            raise HTTPException(409, "both independent reviewer submissions are required")
        errors = validate_decision(
            case.case_type, payload.decision, payload.selected_series_uid, payload.reason,
            case.selectable_uids, payload.image_evidence_reviewed, payload.metadata_evidence_reviewed,
        )
        if errors:
            raise HTTPException(422, detail=errors)
        try:
            final = database.save_final_decision(
                admin_user_id=int(user["id"]), case_id=case_id, decision=payload.decision,
                selected_series_uid=payload.selected_series_uid, reason=payload.reason,
                image_evidence_reviewed=payload.image_evidence_reviewed,
                metadata_evidence_reviewed=payload.metadata_evidence_reviewed,
                expected_version=payload.version,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {"ok": True, "final_decision": final}

    @app.get("/admin/export")
    def export_decisions(
        kind: str = "snapshot",
        _user: dict[str, Any] = Depends(admin_user),
        database: Database = Depends(db),
        review_bundle: ReviewBundle = Depends(bundle),
    ):
        try:
            rows = build_export_rows(review_bundle, database.all_final_decisions(), kind=kind)
        except (ValueError, FinalExportNotReady) as exc:
            raise HTTPException(409 if isinstance(exc, FinalExportNotReady) else 400, str(exc)) from exc
        content = render_csv(rows)
        filename = f"manual_review_decisions_{kind}.csv"
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


def _save_review_payload(
    database: Database,
    bundle: ReviewBundle,
    user: Mapping[str, Any],
    case_id: str,
    payload: ReviewPayload,
    *,
    submit: bool,
) -> dict[str, Any]:
    case = bundle.get_case(case_id)
    assignment = database.assignment(int(user["id"]), case_id)
    if not case or not assignment:
        raise HTTPException(404, "case not found")
    if database.final_decision(case_id):
        raise HTTPException(409, "finalized case is read-only")
    ordered = _ordered_candidates(case, assignment, bundle)
    ordered_uids = [item["series_uid"] for item in ordered if item["selectable"]]
    rec = recommendation(case.case_type, payload.observations, case_id=case_id).as_dict(ordered_uids)
    _validate_observations(case.case_type, payload.observations)
    if submit:
        errors = validate_decision(
            case.case_type, payload.decision, payload.selected_series_uid, payload.reason,
            case.selectable_uids, payload.image_evidence_reviewed, payload.metadata_evidence_reviewed,
        )
        if errors:
            raise HTTPException(422, detail=errors)
    else:
        _validate_draft_choice(case, payload)
    try:
        saved = database.save_review(
            user_id=int(user["id"]), case_id=case_id, expected_version=payload.version,
            observations=payload.observations, decision=payload.decision,
            selected_series_uid=payload.selected_series_uid, reason=payload.reason,
            image_evidence_reviewed=payload.image_evidence_reviewed,
            metadata_evidence_reviewed=payload.metadata_evidence_reviewed, submit=submit,
        )
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "review": saved, "version": saved["version"], "recommendation": rec}


def _validate_draft_choice(case: ReviewCase, payload: ReviewPayload) -> None:
    allowed = (
        {"PENDING", "SELECT_ONE_CANDIDATE", "EXCLUDE_PATIENT", "DEFER"}
        if case.case_type == "technical_tie"
        else {"PENDING", "INCLUDE_REVIEW_SERIES", "EXCLUDE_PATIENT", "DEFER"}
    )
    if payload.decision not in allowed:
        raise HTTPException(422, "invalid decision for case type")
    needs_uid = payload.decision in {"SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES"}
    if needs_uid and payload.selected_series_uid not in case.selectable_uids:
        raise HTTPException(422, "selected_series_uid is not an allowed candidate")
    if not needs_uid and payload.selected_series_uid:
        raise HTTPException(422, "selected_series_uid is not allowed for this decision")


def _validate_observations(case_type: str, observations: Mapping[str, str]) -> None:
    if case_type == "technical_tie":
        allowed_keys = {"texture", "noise", "artifact", "coverage"}
        allowed_values = {"A", "B", "SAME", "UNSURE"}
    else:
        allowed_keys = {"diag_coverage", "diag_artifact", "diag_use"}
        allowed_values = {"YES", "NO", "UNSURE"}
    if not set(observations).issubset(allowed_keys):
        raise HTTPException(422, "observations contain an unknown field")
    if any(not isinstance(value, str) or value not in allowed_values for value in observations.values()):
        raise HTTPException(422, "observations contain an invalid value")


def _ordered_candidates(
    case: ReviewCase, assignment: Mapping[str, Any], bundle: ReviewBundle
) -> list[dict[str, Any]]:
    by_key = {item.candidate_key: item for item in case.candidates}
    ordered: list[Candidate] = []
    for key in (assignment.get("left_candidate_key"), assignment.get("right_candidate_key")):
        if key and key in by_key:
            ordered.append(by_key.pop(str(key)))
    ordered.extend(item for item in case.candidates if item.candidate_key in by_key)
    return [_candidate_dict(item, bundle, display_position=index) for index, item in enumerate(ordered)]


def _candidate_dict(
    candidate: Candidate, bundle: ReviewBundle, display_position: int | None = None
) -> dict[str, Any]:
    value = {
        **dict(candidate.metadata),
        "candidate_key": candidate.candidate_key,
        "series_uid": candidate.series_uid,
        "role": candidate.role,
        "selectable": candidate.selectable,
        "montage_asset_id": candidate.montage_asset_id,
        "montage_url": f"/media/{candidate.montage_asset_id}" if candidate.montage_asset_id else None,
        "frame_asset_ids": list(candidate.frame_asset_ids),
        "frame_urls": [f"/media/{asset_id}" for asset_id in candidate.frame_asset_ids],
        "slice_count": len(candidate.frame_asset_ids),
    }
    if display_position is not None:
        value["display_position"] = "A" if display_position == 0 else "B" if display_position == 1 else "CONTEXT"
        value["alias"] = (
            "候选 A" if display_position == 0 else "候选 B" if display_position == 1 else "对照项"
        )
    return value


def _case_dict(case: ReviewCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "case_type": case.case_type,
        "patient_id": case.patient_id,
        "required_judgment": case.required_judgment,
        "selectable_uids": list(case.selectable_uids),
    }


def _empty_review() -> dict[str, Any]:
    return {
        "status": "DRAFT", "version": 0, "observations": {}, "decision": "PENDING",
        "selected_series_uid": "", "reason": "", "image_evidence_reviewed": False,
        "metadata_evidence_reviewed": False,
    }


def _template(request: Request, name: str, context: dict[str, Any], status_code: int = 200):
    full_context = {"request": request, **context}
    return request.app.state.templates.TemplateResponse(name, full_context, status_code=status_code)


def _public_user(user: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def _source_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if settings.trust_proxy_headers and peer in {"127.0.0.1", "::1"}:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return peer


app = create_app()
