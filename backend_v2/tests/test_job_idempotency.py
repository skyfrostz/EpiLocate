"""Accepted job replay remains recoverable without readmitting expired work."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend_v2.api.app import app
from backend_v2.models.entities import Case, InferenceJob, ModelVersion, Slice
from backend_v2.services.common import now
from backend_v2.services.retention import expire_inputs
from backend_v2.tests.test_phase1 import USER_TOKEN, ctx, seeded_case


PROTOCOL = "stage1-occlusion-instability-v1"
HEADERS = {"Authorization": f"Bearer {USER_TOKEN}", "Idempotency-Key": "accepted-job-key"}


def request_body(case_id, slice_id, kind):
    body = {"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18"}
    if kind == "occlusion":
        body.update(protocol_id=PROTOCOL, scales=[16, 32, 64])
    return body


def endpoint(kind):
    return "/api/v2/jobs/occlusion" if kind == "occlusion" else "/api/v2/predictions"


def invalidate(factory, store, ids, slice_id, condition):
    with factory.begin() as db:
        if condition in {"expired", "purged"}:
            db.scalar(select(Slice).where(Slice.slice_ref == slice_id)).staging_expires_at = now() - timedelta(seconds=1)
            db.flush()
            if condition == "purged":
                expire_inputs(db, store)
        else:
            db.get(ModelVersion, ids[2]).lifecycle_state = "RETIRED"
            if condition == "replaced":
                db.add(ModelVersion(model_id="baseline_resnet18", version="v2", checkpoint_sha256="c" * 64, preprocessing_version="prep-v2", protocol_id="next-protocol"))


@pytest.mark.parametrize("kind", ["prediction", "occlusion"])
@pytest.mark.parametrize("condition", ["expired", "purged", "retired", "replaced"])
def test_accepted_job_replays_after_admission_conditions_change(ctx, kind, condition):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    client = TestClient(app)
    body = request_body(case_id, slice_id, kind)
    first = client.post(endpoint(kind), json=body, headers=HEADERS)
    assert first.status_code == 202, first.text
    invalidate(factory, store, ids, slice_id, condition)
    with factory() as db:
        original = db.scalar(select(InferenceJob))
        original_state = (original.status, original.failure_reason, original.model_version_id, original.request_digest)
    replay = client.post(endpoint(kind), json=body, headers=HEADERS)
    assert replay.status_code == 202, replay.text
    assert replay.json() == first.json()
    with factory() as db:
        saved = db.scalars(select(InferenceJob)).all()
        assert len(saved) == 1
        assert (saved[0].status, saved[0].failure_reason, saved[0].model_version_id, saved[0].request_digest) == original_state


@pytest.mark.parametrize("condition", ["expired", "purged", "retired"])
@pytest.mark.parametrize("change", ["case", "slice", "model", "kind", "protocol", "empty_protocol", "scales"])
def test_accepted_key_rejects_changed_request_even_after_expiry_or_retirement(ctx, condition, change):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    other_case, other_slice = seeded_case(factory, ids)
    client = TestClient(app)
    body = request_body(case_id, slice_id, "occlusion")
    assert client.post(endpoint("occlusion"), json=body, headers=HEADERS).status_code == 202
    invalidate(factory, store, ids, slice_id, condition)
    path = endpoint("occlusion")
    if change == "case":
        body.update(case_id=other_case, slice_id=other_slice)
    elif change == "slice":
        # Keep a valid Case/Slice relationship while changing the selected Slice.
        with factory.begin() as db:
            source = db.scalar(select(Slice).where(Slice.slice_ref == slice_id))
            db.add(Slice(series_id=source.series_id, case_id=source.case_id, slice_ref="slice_alternate", ordinal=1, width_px=32, height_px=32, source_sha256=source.source_sha256, staging_object_key=source.staging_object_key, staging_expires_at=source.staging_expires_at))
        body["slice_id"] = "slice_alternate"
    elif change == "model":
        body["model_id"] = "unknown-model"
    elif change == "kind":
        body = request_body(case_id, slice_id, "prediction")
        path = endpoint("prediction")
    elif change in {"protocol", "empty_protocol"}:
        body["protocol_id"] = "different-protocol" if change == "protocol" else ""
    else:
        body["scales"] = [16]
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    with factory() as db:
        assert len(db.scalars(select(InferenceJob)).all()) == 1


@pytest.mark.parametrize("kind", ["prediction", "occlusion"])
@pytest.mark.parametrize("condition, status, code", [("expired", 410, "INPUT_EXPIRED"), ("purged", 410, "INPUT_EXPIRED"), ("retired", 422, "MODEL_UNAVAILABLE")])
def test_unaccepted_new_key_still_requires_valid_input_and_active_model(ctx, kind, condition, status, code):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    client = TestClient(app)
    body = request_body(case_id, slice_id, kind)
    assert client.post(endpoint(kind), json=body, headers=HEADERS).status_code == 202
    invalidate(factory, store, ids, slice_id, condition)
    response = client.post(endpoint(kind), json=body, headers={**HEADERS, "Idempotency-Key": "unaccepted-new-key"})
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    with factory() as db:
        assert len(db.scalars(select(InferenceJob)).all()) == 1


@pytest.mark.parametrize("restriction", ["foreign_owner", "deleting", "wrong_slice"])
def test_replay_does_not_bypass_case_and_slice_authorization(ctx, restriction):
    factory, _, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    client = TestClient(app)
    body = request_body(case_id, slice_id, "prediction")
    assert client.post(endpoint("prediction"), json=body, headers=HEADERS).status_code == 202
    with factory.begin() as db:
        case = db.scalar(select(Case).where(Case.anonymous_id == case_id))
        if restriction == "foreign_owner":
            case.owner_user_id = ids[1]
        elif restriction == "deleting":
            case.status = "DELETING"
        else:
            _, other_slice = seeded_case(factory, ids)
            body["slice_id"] = other_slice
    response = client.post(endpoint("prediction"), json=body, headers=HEADERS)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("mutation", ["input_hash", "checkpoint", "preprocessing"])
def test_replay_still_checks_frozen_request_digest(ctx, mutation):
    factory, _, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    client = TestClient(app)
    body = request_body(case_id, slice_id, "prediction")
    assert client.post(endpoint("prediction"), json=body, headers=HEADERS).status_code == 202
    with factory.begin() as db:
        if mutation == "input_hash":
            db.scalar(select(Slice).where(Slice.slice_ref == slice_id)).source_sha256 = "d" * 64
        elif mutation == "checkpoint":
            db.get(ModelVersion, ids[2]).checkpoint_sha256 = "d" * 64
        else:
            db.get(ModelVersion, ids[2]).preprocessing_version = "different-preprocessing"
    response = client.post(endpoint("prediction"), json=body, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_same_key_is_scoped_to_requesting_user(ctx, monkeypatch):
    import hashlib
    import json

    factory, _, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    other_ids = (ids[1], ids[0], *ids[2:])
    other_case, other_slice = seeded_case(factory, other_ids)
    other_token = "other-test-token-0123456789"
    monkeypatch.setenv("EPILOCATE_V2_USER_TOKEN_HASHES", json.dumps({
        "test-subject": hashlib.sha256(USER_TOKEN.encode()).hexdigest(),
        "other": hashlib.sha256(other_token.encode()).hexdigest(),
    }))
    client = TestClient(app)
    body = request_body(case_id, slice_id, "prediction")
    first = client.post(endpoint("prediction"), json=body, headers=HEADERS)
    assert first.status_code == 202
    other_headers = {**HEADERS, "Authorization": f"Bearer {other_token}"}
    assert client.post(endpoint("prediction"), json=body, headers=other_headers).status_code == 404
    other = client.post(endpoint("prediction"), json=request_body(other_case, other_slice, "prediction"), headers=other_headers)
    assert other.status_code == 202, other.text
    assert other.json()["job_id"] != first.json()["job_id"]
    assert client.post(endpoint("prediction"), json=body, headers=HEADERS).json() == first.json()
    with factory() as db:
        assert len(db.scalars(select(InferenceJob)).all()) == 2


@pytest.mark.parametrize("invalid", [{"protocol_id": "wrong-protocol"}, {"scales": [16, 16]}, {"scales": [8]}, {"scales": []}])
def test_unaccepted_occlusion_still_rejects_invalid_parameters(ctx, invalid):
    factory, _, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    body = {**request_body(case_id, slice_id, "occlusion"), **invalid}
    response = TestClient(app).post(endpoint("occlusion"), json=body, headers=HEADERS)
    assert response.status_code == 422, response.text
    with factory() as db:
        assert db.scalar(select(InferenceJob)) is None
