import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epilocate_review_server.app.bundle import ReviewBundle
from epilocate_review_server.app.config import EXPECTED_PROTOCOL_ID, EXPECTED_PROTOCOL_SHA256, Settings
from epilocate_review_server.app.db import Database, VersionConflict
from epilocate_review_server.app.main import CSRF_COOKIE, create_app
from epilocate_review_server.app.security import hash_password, new_token, token_hash, verify_password


def make_bundle(tmp_path: Path) -> ReviewBundle:
    assets = {}
    cases = []
    for index in range(1, 14):
        candidates = []
        count = 2 if index <= 12 else 1
        for candidate_index in range(count):
            asset_id = f"asset-{index}-{candidate_index}"
            relative = f"frames/{asset_id}.png"
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic png fixture")
            import hashlib
            assets[asset_id] = {
                "path": relative,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
            candidates.append(
                {
                    "candidate_key": f"candidate-{index}-{candidate_index}",
                    "series_uid": f"1.2.840.synthetic.{index}.{candidate_index}",
                    "role": "eligible_top_tied" if index <= 12 else "review_candidate",
                    "frame_asset_ids": [asset_id],
                }
            )
        cases.append(
            {
                "case_id": f"TIE-{index:03d}" if index <= 12 else "DIAG-001",
                "case_type": "technical_tie" if index <= 12 else "diagnostic_type_uncertain",
                "patient_id": f"SYNTHETIC-P{index:03d}",
                "candidates": candidates,
            }
        )
    manifest = {
        "format": "epilocate-review-bundle",
        "version": 1,
        "protocol_id": EXPECTED_PROTOCOL_ID,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "assets": assets,
        "cases": cases,
    }
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return ReviewBundle.load(path)


def test_argon2id_and_session_hash_do_not_store_secrets(tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    database = Database(tmp_path / "review.sqlite3")
    database.initialize()
    password = "correct horse battery staple"
    password_hash = hash_password(password)
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, password)
    user_id = database.create_user("reviewer", password_hash, "reviewer", bundle)
    session_token = new_token()
    csrf_token = new_token()
    database.create_session(user_id, token_hash(session_token), token_hash(csrf_token), 8)
    raw_database = (tmp_path / "review.sqlite3").read_bytes()
    assert password.encode() not in raw_database
    assert session_token.encode() not in raw_database
    assert csrf_token.encode() not in raw_database


def test_reviewer_queries_and_optimistic_lock_are_scoped_by_user(tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    database = Database(tmp_path / "review.sqlite3")
    database.initialize()
    first = database.create_user("first", hash_password("first password long enough"), "reviewer", bundle)
    second = database.create_user("second", hash_password("second password long enough"), "reviewer", bundle)
    case = bundle.cases[0]
    assert database.assignment(first, case.case_id)["left_candidate_key"] != database.assignment(
        second, case.case_id
    )["left_candidate_key"]
    saved = database.save_review(
        user_id=first,
        case_id=case.case_id,
        expected_version=0,
        observations={},
        decision="PENDING",
        selected_series_uid="",
        reason="",
        image_evidence_reviewed=False,
        metadata_evidence_reviewed=False,
    )
    assert database.review(second, case.case_id) is None
    with pytest.raises(VersionConflict):
        database.save_review(
            user_id=first,
            case_id=case.case_id,
            expected_version=saved["version"] - 1,
            observations={},
            decision="PENDING",
            selected_series_uid="",
            reason="",
            image_evidence_reviewed=False,
            metadata_evidence_reviewed=False,
        )


def test_bundle_rejects_path_traversal(tmp_path):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    manifest = {
        "format": "epilocate-review-bundle",
        "version": 1,
        "protocol_id": EXPECTED_PROTOCOL_ID,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "assets": {"bad": {"path": "../escape.png", "sha256": "0" * 64}},
        "cases": [],
    }
    path = bundle_dir / "bundle.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe asset path"):
        ReviewBundle.load(path, verify_files=False, expected_case_count=0)


def test_http_security_csrf_roles_and_version_conflict(tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    settings = Settings(
        database_path=tmp_path / "review.sqlite3",
        bundle_path=bundle.manifest_path,
        environment="production",
        allowed_hosts=("testserver",),
        allowed_origins=("http://testserver",),
        secure_cookies=False,
    )
    database = Database(settings.database_path)
    database.initialize()
    database.create_user("reviewer", hash_password("reviewer password long enough"), "reviewer", bundle)
    database.create_user("admin", hash_password("admin password long enough"), "admin", bundle)
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "reviewer", "password": "reviewer password long enough"},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert "/admin" not in login.headers["location"]
        assert client.get("/admin").status_code == 403
        assert client.get("/media/asset-1-0").status_code == 200
        case_id = bundle.cases[0].case_id
        payload = {
            "version": 0,
            "observations": {},
            "decision": "PENDING",
            "selected_series_uid": "",
            "reason": "",
            "image_evidence_reviewed": False,
            "metadata_evidence_reviewed": False,
        }
        assert client.patch(
            f"/api/reviews/{case_id}/draft",
            json=payload,
            headers={"Origin": "http://testserver"},
        ).status_code == 403
        csrf = client.cookies[CSRF_COOKIE]
        saved = client.patch(
            f"/api/reviews/{case_id}/draft",
            json=payload,
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert saved.status_code == 200
        assert saved.json()["version"] == 1
        stale = client.patch(
            f"/api/reviews/{case_id}/draft",
            json=payload,
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert stale.status_code == 409
        assert client.get("/docs").status_code == 404

    with TestClient(app) as anonymous:
        assert anonymous.get("/media/asset-1-0").status_code == 401
        assert anonymous.post(
            "/login",
            data={"username": "reviewer", "password": "reviewer password long enough"},
        ).status_code == 403


def test_two_independent_submissions_admin_final_and_final_read_only(tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    settings = Settings(
        database_path=tmp_path / "review.sqlite3",
        bundle_path=bundle.manifest_path,
        environment="testing",
        allowed_hosts=("testserver",),
        allowed_origins=("http://testserver",),
        secure_cookies=False,
    )
    database = Database(settings.database_path)
    database.initialize()
    database.create_user("first", hash_password("first reviewer password"), "reviewer", bundle)
    database.create_user("second", hash_password("second reviewer password"), "reviewer", bundle)
    database.create_user("admin", hash_password("admin password long enough"), "admin", bundle)
    app = create_app(settings)
    case = bundle.cases[0]
    reason = "该 Series 胸部解剖覆盖完整，图像噪声较低且运动伪影较少，适合作为研究输入。"
    review_clients = []
    for username, password in (
        ("first", "first reviewer password"),
        ("second", "second reviewer password"),
    ):
        client = TestClient(app)
        client.__enter__()
        review_clients.append(client)
        assert client.post(
            "/login",
            data={"username": username, "password": password},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        ).status_code == 303
        csrf = client.cookies[CSRF_COOKIE]
        response = client.post(
            f"/api/reviews/{case.case_id}/submit",
            json={
                "version": 0,
                "observations": {"texture": "A", "noise": "A", "artifact": "SAME", "coverage": "SAME"},
                "decision": "SELECT_ONE_CANDIDATE",
                "selected_series_uid": case.selectable_uids[0],
                "reason": reason,
                "image_evidence_reviewed": True,
                "metadata_evidence_reviewed": True,
            },
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        duplicate_submit = client.post(
            f"/api/reviews/{case.case_id}/submit",
            json={
                "version": response.json()["version"],
                "observations": {"texture": "A", "noise": "A", "artifact": "SAME", "coverage": "SAME"},
                "decision": "SELECT_ONE_CANDIDATE",
                "selected_series_uid": case.selectable_uids[0],
                "reason": reason,
                "image_evidence_reviewed": True,
                "metadata_evidence_reviewed": True,
            },
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert duplicate_submit.status_code == 409

    with TestClient(app) as admin:
        assert admin.post(
            "/login",
            data={"username": "admin", "password": "admin password long enough"},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        ).status_code == 303
        csrf = admin.cookies[CSRF_COOKIE]
        finalized = admin.post(
            f"/api/admin/final-decisions/{case.case_id}",
            json={
                "decision": "SELECT_ONE_CANDIDATE",
                "selected_series_uid": case.selectable_uids[0],
                "reason": reason,
                "image_evidence_reviewed": True,
                "metadata_evidence_reviewed": True,
            },
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert finalized.status_code == 200
        assert finalized.json()["final_decision"]["reviewer"] == "admin"
        update_without_version = admin.post(
            f"/api/admin/final-decisions/{case.case_id}",
            json={
                "decision": "SELECT_ONE_CANDIDATE",
                "selected_series_uid": case.selectable_uids[0],
                "reason": reason,
                "image_evidence_reviewed": True,
                "metadata_evidence_reviewed": True,
            },
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert update_without_version.status_code == 409

    first_client = review_clients[0]
    csrf = first_client.cookies[CSRF_COOKIE]
    assert first_client.post(
        f"/api/reviews/{case.case_id}/reopen",
        json={},
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    ).status_code == 409
    for client in review_clients:
        client.__exit__(None, None, None)
