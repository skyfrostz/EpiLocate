"""Explicit separate research factory. Never installed into the base MVP app."""
import json
from fastapi import Depends, FastAPI, File, Form, UploadFile
from sqlalchemy.orm import Session
from backend_v2.api import app as base
from backend_v2.services.common import fail
from epilocate_next.contracts import ApplicationRequest
from epilocate_next.research_contract import validate_research_wire_result


def create_research_app(binding_provider):
    """Same auth/storage/submit APIs, with additional research result rejection."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # Retain error handlers and dependencies, not another account/job system.
    app.exception_handlers.update(base.app.exception_handlers)

    def validate(wire):
        if wire.get('kind') != 'ALGORITHM':
            return
        try:
            req = ApplicationRequest.model_validate(wire['application_request'])
            validate_research_wire_result(wire, binding_provider(req))
        except (ValueError, KeyError, TypeError):
            fail('RESEARCH_RESULT_CONTRACT_REJECTED', 422)

    async def submit(manifest, assets, db, worker, job_id=None):
        if len(manifest.encode()) > 64*1024*1024:
            fail('RESULT_TOO_LARGE', 413)
        try:
            value = json.loads(manifest)
            if value.get('outcome') == 'SUCCEEDED':
                validate(value['result'])
        except (ValueError, KeyError, TypeError, AttributeError):
            fail('RESEARCH_RESULT_CONTRACT_REJECTED', 422)
        return await base._submit(manifest, assets, db, worker, job_id)

    @app.post('/api/v2/workers/jobs/{job_id}/result')
    async def result_by_job(job_id: str, manifest: str = Form(...),
        assets: list[UploadFile] | None = File(None, alias='assets[]'),
        db: Session = Depends(base.get_db), worker=Depends(base.current_worker)):
        return await submit(manifest, assets, db, worker, job_id)

    @app.post('/api/v2/workers/results')
    async def result_submit(manifest: str = Form(...),
        assets: list[UploadFile] | None = File(None, alias='assets[]'),
        db: Session = Depends(base.get_db), worker=Depends(base.current_worker)):
        return await submit(manifest, assets, db, worker)

    @app.get('/api/v2/results/{result_id}')
    def result_read(result_id: str, db: Session = Depends(base.get_db), user=Depends(base.current_user)):
        body = base.result_detail(result_id, db, user)
        validate(body)
        return body

    app.mount('/', base.app)
    return app
