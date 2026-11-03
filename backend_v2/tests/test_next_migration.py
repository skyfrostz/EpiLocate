"""Generated database only; migration must retain legacy rows and constraints."""
import importlib
import pytest
pytest.importorskip('alembic',reason='Existing environment has no Alembic; no installation authorized')
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select
from backend_v2.tests.test_phase1 import ctx, seeded_case, create_job
from backend_v2.models.entities import InferenceJob


def test_sqlite_constraint_upgrade_retains_legacy_rows_indexes_and_keys(ctx,monkeypatch):
    factory,_,ids=ctx
    migration=importlib.import_module('backend_v2.migrations.versions.0004_algorithm_application')
    engine=factory.kw['bind']
    with engine.begin() as connection:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        migration.downgrade()
    cid,sid=seeded_case(factory,ids);jid=create_job(factory,ids,cid,sid)
    before=inspect(engine)
    indices=before.get_indexes('inference_jobs');keys=before.get_foreign_keys('inference_jobs')
    with engine.begin() as connection:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        migration.upgrade()
    after=inspect(engine)
    assert after.get_indexes('inference_jobs')==indices
    import json
    normalize=lambda items:sorted(json.dumps(item,sort_keys=True) for item in items)
    assert normalize(after.get_foreign_keys('inference_jobs'))==normalize(keys)
    checks=after.get_check_constraints('inference_jobs')
    assert any('ALGORITHM' in c['sqltext'] for c in checks)
    assert any('QUEUED' in c['sqltext'] for c in checks)
    with factory.begin() as db:
        job=db.scalar(select(InferenceJob).where(InferenceJob.public_id==jid))
        assert job.kind=='PREDICTION' and job.case_id and job.slice_id
        job.kind='ALGORITHM'
    with engine.begin() as connection:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError,match='Preserve new algorithm results'):migration.downgrade()
