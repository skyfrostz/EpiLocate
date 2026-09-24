from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping, Sequence

from .bundle import ReviewBundle


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_after(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class VersionConflict(RuntimeError):
    pass


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self, migration_path: str | Path | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        migration = Path(migration_path) if migration_path else Path(__file__).parents[1] / "migrations/001_init.sql"
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(migration.read_text(encoding="utf-8"))
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create_user(self, username: str, password_hash: str, role: str, bundle: ReviewBundle) -> int:
        if role not in {"reviewer", "admin"}:
            raise ValueError("role must be reviewer or admin")
        username = username.strip()
        if not username or len(username) > 64:
            raise ValueError("username must be 1-64 characters")
        with self.transaction() as connection:
            reviewer_slot = None
            if role == "reviewer":
                reviewer_slot = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(reviewer_slot), -1) + 1 FROM users WHERE role = 'reviewer'"
                    ).fetchone()[0]
                )
                if reviewer_slot >= 2:
                    raise ValueError("review server v1 permits exactly two reviewer accounts")
            cursor = connection.execute(
                "INSERT INTO users(username,password_hash,role,reviewer_slot,created_at_utc) VALUES(?,?,?,?,?)",
                (username, password_hash, role, reviewer_slot, utc_now()),
            )
            user_id = int(cursor.lastrowid)
            if role == "reviewer":
                self._insert_assignments(connection, user_id, reviewer_slot or 0, bundle)
            return user_id

    @staticmethod
    def _insert_assignments(
        connection: sqlite3.Connection, user_id: int, reviewer_slot: int, bundle: ReviewBundle
    ) -> None:
        now = utc_now()
        for index, case in enumerate(bundle.cases):
            selectable = list(case.selectable_candidates)
            left = selectable[0].candidate_key
            right = selectable[1].candidate_key if len(selectable) > 1 else None
            # Mirror by case parity and stable reviewer identity; never inspect UID value.
            if right is not None and (index + reviewer_slot) % 2:
                left, right = right, left
            connection.execute(
                """INSERT INTO review_assignments
                   (user_id,case_id,case_order,left_candidate_key,right_candidate_key,created_at_utc)
                   VALUES(?,?,?,?,?,?)""",
                (user_id, case.case_id, index, left, right, now),
            )

    def user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND active = 1", (username,)
            ).fetchone()
        return dict(row) if row else None

    def user_by_session_hash(self, token_hash: str, now: str | None = None) -> dict[str, Any] | None:
        now = now or utc_now()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT u.*, s.id AS session_id, s.csrf_token_hash, s.expires_at_utc
                   FROM sessions s JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.revoked_at_utc IS NULL
                     AND s.expires_at_utc > ? AND u.active=1""",
                (token_hash, now),
            ).fetchone()
        return dict(row) if row else None

    def create_session(
        self, user_id: int, token_hash: str, csrf_token_hash: str, session_hours: int
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at_utc <= ? OR revoked_at_utc IS NOT NULL", (utc_now(),)
            )
            connection.execute(
                """INSERT INTO sessions(token_hash,csrf_token_hash,user_id,created_at_utc,expires_at_utc)
                   VALUES(?,?,?,?,?)""",
                (token_hash, csrf_token_hash, user_id, utc_now(), utc_after(session_hours)),
            )

    def revoke_session(self, token_hash: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at_utc=? WHERE token_hash=? AND revoked_at_utc IS NULL",
                (utc_now(), token_hash),
            )

    def login_is_rate_limited(self, username: str, source_ip: str, *, limit: int = 5, minutes: int = 15) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.connect() as connection:
            count = connection.execute(
                """SELECT COUNT(*) FROM auth_attempts
                   WHERE username=? COLLATE NOCASE AND source_ip=? AND success=0 AND attempted_at_utc >= ?""",
                (username, source_ip, cutoff),
            ).fetchone()[0]
        return int(count) >= limit

    def record_login_attempt(self, username: str, source_ip: str, success: bool) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO auth_attempts(username,source_ip,attempted_at_utc,success) VALUES(?,?,?,?)",
                (username[:64], source_ip[:128], utc_now(), int(success)),
            )

    def assignment(self, user_id: int, case_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM review_assignments WHERE user_id=? AND case_id=?", (user_id, case_id)
            ).fetchone()
        return dict(row) if row else None

    def assignments(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT a.*, r.status, r.version, r.decision, r.updated_at_utc
                   FROM review_assignments a
                   LEFT JOIN reviews r ON r.user_id=a.user_id AND r.case_id=a.case_id
                   WHERE a.user_id=? ORDER BY a.case_order""",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def review(self, user_id: int, case_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reviews WHERE user_id=? AND case_id=?", (user_id, case_id)
            ).fetchone()
        return _review_dict(row) if row else None

    def save_review(
        self,
        *,
        user_id: int,
        case_id: str,
        expected_version: int,
        observations: Mapping[str, str],
        decision: str,
        selected_series_uid: str,
        reason: str,
        image_evidence_reviewed: bool,
        metadata_evidence_reviewed: bool,
        submit: bool = False,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as connection:
            assignment = connection.execute(
                "SELECT 1 FROM review_assignments WHERE user_id=? AND case_id=?", (user_id, case_id)
            ).fetchone()
            if not assignment:
                raise PermissionError("case is not assigned to this reviewer")
            existing = connection.execute(
                "SELECT * FROM reviews WHERE user_id=? AND case_id=?", (user_id, case_id)
            ).fetchone()
            status = "SUBMITTED" if submit else "DRAFT"
            if existing:
                if int(existing["version"]) != expected_version:
                    raise VersionConflict("review version conflict")
                if existing["status"] == "SUBMITTED":
                    raise PermissionError("submitted review is read-only")
                new_version = expected_version + 1
                cursor = connection.execute(
                    """UPDATE reviews SET status=?,version=?,observations_json=?,decision=?,
                       selected_series_uid=?,reason=?,image_evidence_reviewed=?,metadata_evidence_reviewed=?,
                       updated_at_utc=?,submitted_at_utc=?
                       WHERE id=? AND version=?""",
                    (
                        status, new_version, _canonical_json(observations), decision, selected_series_uid,
                        reason, int(image_evidence_reviewed), int(metadata_evidence_reviewed), now,
                        now if submit else existing["submitted_at_utc"], existing["id"], expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise VersionConflict("review version conflict")
                review_id = int(existing["id"])
            else:
                if expected_version not in {0, 1}:
                    raise VersionConflict("review version conflict")
                new_version = 1
                cursor = connection.execute(
                    """INSERT INTO reviews
                       (user_id,case_id,status,version,observations_json,decision,selected_series_uid,reason,
                        image_evidence_reviewed,metadata_evidence_reviewed,created_at_utc,updated_at_utc,submitted_at_utc)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        user_id, case_id, status, new_version, _canonical_json(observations), decision,
                        selected_series_uid, reason, int(image_evidence_reviewed),
                        int(metadata_evidence_reviewed), now, now, now if submit else None,
                    ),
                )
                review_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO review_events(actor_user_id,case_id,event_type,review_id,payload_json,created_at_utc)
                   VALUES(?,?,?,?,?,?)""",
                (
                    user_id, case_id, "REVIEW_SUBMITTED" if submit else "DRAFT_SAVED", review_id,
                    _canonical_json({"version": new_version, "decision": decision}), now,
                ),
            )
            row = connection.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        return _review_dict(row)

    def reopen_review(self, user_id: int, case_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as connection:
            final = connection.execute(
                "SELECT 1 FROM final_decisions WHERE case_id=?", (case_id,)
            ).fetchone()
            if final:
                raise PermissionError("finalized case is read-only")
            row = connection.execute(
                "SELECT * FROM reviews WHERE user_id=? AND case_id=?", (user_id, case_id)
            ).fetchone()
            if not row or row["status"] != "SUBMITTED":
                raise ValueError("submitted review not found")
            connection.execute(
                "UPDATE reviews SET status='DRAFT',version=version+1,updated_at_utc=? WHERE id=?",
                (now, row["id"]),
            )
            connection.execute(
                "INSERT INTO review_events(actor_user_id,case_id,event_type,review_id,payload_json,created_at_utc) VALUES(?,?,?,?,?,?)",
                (user_id, case_id, "REVIEW_REOPENED", row["id"], "{}", now),
            )
            updated = connection.execute("SELECT * FROM reviews WHERE id=?", (row["id"],)).fetchone()
        return _review_dict(updated)

    def submitted_reviews_for_case(self, case_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.*, u.username FROM reviews r JOIN users u ON u.id=r.user_id
                   WHERE r.case_id=? AND u.role='reviewer' ORDER BY u.reviewer_slot, u.id""",
                (case_id,),
            ).fetchall()
        return [_review_dict(row) for row in rows]

    def all_review_summaries(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT case_id,
                   COUNT(*) AS review_count,
                   SUM(CASE WHEN status='SUBMITTED' THEN 1 ELSE 0 END) AS submitted_count,
                   SUM(CASE WHEN status='SUBMITTED' AND decision='DEFER' THEN 1 ELSE 0 END) AS defer_count
                   FROM reviews GROUP BY case_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def final_decision(self, case_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT f.*, u.username AS reviewer FROM final_decisions f
                   JOIN users u ON u.id=f.decided_by_user_id WHERE f.case_id=?""",
                (case_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_final_decision(
        self,
        *,
        admin_user_id: int,
        case_id: str,
        decision: str,
        selected_series_uid: str,
        reason: str,
        image_evidence_reviewed: bool,
        metadata_evidence_reviewed: bool,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as connection:
            actor = connection.execute("SELECT role FROM users WHERE id=?", (admin_user_id,)).fetchone()
            if not actor or actor["role"] != "admin":
                raise PermissionError("admin role required")
            existing = connection.execute(
                "SELECT * FROM final_decisions WHERE case_id=?", (case_id,)
            ).fetchone()
            if existing:
                if expected_version is None:
                    raise VersionConflict("final decision version is required for updates")
                if int(existing["version"]) != expected_version:
                    raise VersionConflict("final decision version conflict")
                version = int(existing["version"]) + 1
                connection.execute(
                    """UPDATE final_decisions SET decision=?,selected_series_uid=?,reason=?,
                       image_evidence_reviewed=?,metadata_evidence_reviewed=?,decided_by_user_id=?,
                       reviewed_at_utc=?,version=?,updated_at_utc=? WHERE id=?""",
                    (
                        decision, selected_series_uid, reason, int(image_evidence_reviewed),
                        int(metadata_evidence_reviewed), admin_user_id, now, version, now, existing["id"],
                    ),
                )
                final_id = int(existing["id"])
            else:
                version = 1
                cursor = connection.execute(
                    """INSERT INTO final_decisions
                       (case_id,decision,selected_series_uid,reason,image_evidence_reviewed,
                        metadata_evidence_reviewed,decided_by_user_id,reviewed_at_utc,version,created_at_utc,updated_at_utc)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        case_id, decision, selected_series_uid, reason, int(image_evidence_reviewed),
                        int(metadata_evidence_reviewed), admin_user_id, now, version, now, now,
                    ),
                )
                final_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO review_events(actor_user_id,case_id,event_type,payload_json,created_at_utc)
                   VALUES(?,?,?,?,?)""",
                (
                    admin_user_id, case_id, "FINAL_DECISION_SAVED",
                    _canonical_json({"version": version, "decision": decision, "selected_series_uid": selected_series_uid}),
                    now,
                ),
            )
            row = connection.execute(
                """SELECT f.*, u.username AS reviewer FROM final_decisions f
                   JOIN users u ON u.id=f.decided_by_user_id WHERE f.id=?""",
                (final_id,),
            ).fetchone()
        return dict(row)

    def all_final_decisions(self) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT f.*, u.username AS reviewer FROM final_decisions f
                   JOIN users u ON u.id=f.decided_by_user_id"""
            ).fetchall()
        return {str(row["case_id"]): dict(row) for row in rows}


def _review_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    value = dict(row)
    value["observations"] = json.loads(value.pop("observations_json", "{}"))
    value["image_evidence_reviewed"] = bool(value["image_evidence_reviewed"])
    value["metadata_evidence_reviewed"] = bool(value["metadata_evidence_reviewed"])
    value["reviewed_at_utc"] = value.get("submitted_at_utc") or value.get("updated_at_utc")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
