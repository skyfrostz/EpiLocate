from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .config import EXPECTED_PROTOCOL_ID, EXPECTED_PROTOCOL_SHA256


class BundleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    asset_id: str
    relative_path: str
    sha256: str
    kind: str = "frame"
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class Candidate:
    candidate_key: str
    series_uid: str
    role: str
    metadata: Mapping[str, Any]
    montage_asset_id: str | None
    frame_asset_ids: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        return self.role not in {"excluded_bone_only_context", "context", "non_selectable_context"}


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    case_type: str
    patient_id: str
    candidates: tuple[Candidate, ...]
    required_judgment: str = ""
    declared_candidate_uids: tuple[str, ...] = ()
    declared_context_uids: tuple[str, ...] = ()

    @property
    def selectable_candidates(self) -> tuple[Candidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.selectable)

    @property
    def selectable_uids(self) -> tuple[str, ...]:
        return tuple(candidate.series_uid for candidate in self.selectable_candidates)


class ReviewBundle:
    def __init__(
        self,
        manifest_path: Path,
        protocol_id: str,
        protocol_sha256: str,
        cases: Sequence[ReviewCase],
        assets: Mapping[str, Asset],
        raw: Mapping[str, Any],
    ) -> None:
        self.manifest_path = manifest_path
        self.root = manifest_path.parent.resolve()
        self.protocol_id = protocol_id
        self.protocol_sha256 = protocol_sha256
        self.cases = tuple(cases)
        self.assets = dict(assets)
        self.raw = raw
        self.case_by_id = {case.case_id: case for case in cases}

    @classmethod
    def load(cls, path: str | Path, *, verify_files: bool = True, expected_case_count: int = 13) -> "ReviewBundle":
        manifest_path = Path(path).expanduser().resolve()
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleValidationError(f"cannot read bundle manifest: {exc}") from exc
        if not isinstance(raw, dict):
            raise BundleValidationError("bundle manifest must be an object")
        if raw.get("format") != "epilocate-review-bundle" or raw.get("version") != 1:
            raise BundleValidationError("unsupported bundle format or version")

        protocol = raw.get("protocol") if isinstance(raw.get("protocol"), dict) else {}
        protocol_id = str(raw.get("protocol_id") or protocol.get("id") or "")
        protocol_hash = str(
            raw.get("protocol_sha256") or raw.get("protocol_hash") or protocol.get("sha256") or ""
        ).lower()
        if protocol_id != EXPECTED_PROTOCOL_ID:
            raise BundleValidationError("bundle protocol_id does not match the frozen protocol")
        if protocol_hash != EXPECTED_PROTOCOL_SHA256:
            raise BundleValidationError("bundle protocol_sha256 does not match the frozen protocol")

        assets = cls._load_assets(raw.get("assets", {}))
        raw_cases = raw.get("cases")
        if isinstance(raw_cases, dict):
            raw_cases = [dict(value, case_id=key) for key, value in raw_cases.items()]
        if not isinstance(raw_cases, list):
            raise BundleValidationError("bundle cases must be a list or object")
        cases = [cls._load_case(item) for item in raw_cases]
        bundle = cls(manifest_path, protocol_id, protocol_hash, cases, assets, raw)
        bundle.validate(verify_files=verify_files, expected_case_count=expected_case_count)
        return bundle

    @staticmethod
    def _load_assets(raw_assets: Any) -> dict[str, Asset]:
        if isinstance(raw_assets, dict):
            rows = [dict(value, asset_id=key) if isinstance(value, dict) else value for key, value in raw_assets.items()]
        elif isinstance(raw_assets, list):
            rows = raw_assets
        else:
            raise BundleValidationError("bundle assets must be a list or object")
        assets: dict[str, Asset] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise BundleValidationError("asset entry must be an object")
            asset_id = str(row.get("asset_id") or row.get("id") or "")
            relative_path = str(row.get("path") or row.get("relative_path") or "")
            sha256 = str(row.get("sha256") or "").lower()
            if not asset_id or asset_id in assets:
                raise BundleValidationError("asset IDs must be nonempty and unique")
            assets[asset_id] = Asset(
                asset_id=asset_id,
                relative_path=relative_path,
                sha256=sha256,
                kind=str(row.get("kind") or row.get("type") or "frame"),
                width=_optional_int(row.get("width")),
                height=_optional_int(row.get("height")),
            )
        return assets

    @staticmethod
    def _load_case(row: Any) -> ReviewCase:
        if not isinstance(row, dict):
            raise BundleValidationError("case entry must be an object")
        candidates_raw: list[Any] = []
        if isinstance(row.get("candidates"), list):
            candidates_raw.extend(row["candidates"])
        if isinstance(row.get("context"), list):
            for item in row["context"]:
                item = dict(item)
                item.setdefault("role", "context")
                candidates_raw.append(item)
        if isinstance(row.get("context_candidates"), list):
            for item in row["context_candidates"]:
                item = dict(item)
                item.setdefault("role", "context")
                candidates_raw.append(item)
        candidates = tuple(_load_candidate(item) for item in candidates_raw)
        return ReviewCase(
            case_id=str(row.get("case_id") or row.get("id") or ""),
            case_type=str(row.get("case_type") or row.get("type") or ""),
            patient_id=str(row.get("patient_id") or ""),
            candidates=candidates,
            required_judgment=str(row.get("required_judgment") or ""),
            declared_candidate_uids=tuple(_string_list(row.get("candidate_series_uids"))),
            declared_context_uids=tuple(_string_list(row.get("context_series_uids"))),
        )

    def validate(self, *, verify_files: bool, expected_case_count: int) -> None:
        if expected_case_count and len(self.cases) != expected_case_count:
            raise BundleValidationError(f"bundle must contain exactly {expected_case_count} cases")
        if len(self.case_by_id) != len(self.cases):
            raise BundleValidationError("case IDs must be unique")
        patient_ids = [case.patient_id for case in self.cases]
        if any(not value for value in patient_ids) or len(set(patient_ids)) != len(patient_ids):
            raise BundleValidationError("patient IDs must be nonempty and unique")
        referenced_assets: set[str] = set()
        candidate_keys: set[str] = set()
        for case in self.cases:
            if not case.case_id or case.case_type not in {"technical_tie", "diagnostic_type_uncertain"}:
                raise BundleValidationError("case ID or case type is invalid")
            expected_selectable = 2 if case.case_type == "technical_tie" else 1
            if len(case.selectable_candidates) != expected_selectable:
                raise BundleValidationError(f"{case.case_id}: unexpected selectable candidate count")
            uids = [candidate.series_uid for candidate in case.candidates]
            if any(not uid for uid in uids) or len(set(uids)) != len(uids):
                raise BundleValidationError(f"{case.case_id}: candidate UIDs must be nonempty and unique")
            selectable_uids = tuple(item.series_uid for item in case.candidates if item.selectable)
            context_uids = tuple(item.series_uid for item in case.candidates if not item.selectable)
            if case.declared_candidate_uids and (
                len(case.declared_candidate_uids) != len(selectable_uids)
                or set(case.declared_candidate_uids) != set(selectable_uids)
            ):
                raise BundleValidationError(
                    f"{case.case_id}: candidate_series_uids disagree with candidate entries"
                )
            if case.declared_context_uids and (
                len(case.declared_context_uids) != len(context_uids)
                or set(case.declared_context_uids) != set(context_uids)
            ):
                raise BundleValidationError(
                    f"{case.case_id}: context_series_uids disagree with context entries"
                )
            for candidate in case.candidates:
                if not candidate.candidate_key or candidate.candidate_key in candidate_keys:
                    raise BundleValidationError("candidate keys must be nonempty and globally unique")
                candidate_keys.add(candidate.candidate_key)
                if candidate.montage_asset_id:
                    referenced_assets.add(candidate.montage_asset_id)
                referenced_assets.update(candidate.frame_asset_ids)
                if not candidate.frame_asset_ids:
                    raise BundleValidationError(f"{case.case_id}: candidate has no frame assets")
        missing = referenced_assets - self.assets.keys()
        if missing:
            raise BundleValidationError(f"unknown referenced assets: {sorted(missing)[:3]}")
        for asset in self.assets.values():
            rel = PurePosixPath(asset.relative_path)
            if not asset.relative_path or rel.is_absolute() or ".." in rel.parts or "\\" in asset.relative_path:
                raise BundleValidationError(f"unsafe asset path for {asset.asset_id}")
            if not re_full_sha256(asset.sha256):
                raise BundleValidationError(f"invalid asset hash for {asset.asset_id}")
            target = (self.root / Path(*rel.parts)).resolve()
            try:
                target.relative_to(self.root)
            except ValueError as exc:
                raise BundleValidationError(f"asset escapes bundle root: {asset.asset_id}") from exc
            if verify_files:
                if not target.is_file():
                    raise BundleValidationError(f"missing asset file: {asset.asset_id}")
                if sha256_file(target) != asset.sha256:
                    raise BundleValidationError(f"asset hash mismatch: {asset.asset_id}")

    def get_case(self, case_id: str) -> ReviewCase | None:
        return self.case_by_id.get(case_id)

    def asset_for_case(self, case_id: str, asset_id: str) -> Asset | None:
        case = self.case_by_id.get(case_id)
        if not case:
            return None
        allowed: set[str] = set()
        for candidate in case.candidates:
            if candidate.montage_asset_id:
                allowed.add(candidate.montage_asset_id)
            allowed.update(candidate.frame_asset_ids)
        return self.assets.get(asset_id) if asset_id in allowed else None

    def case_for_asset(self, asset_id: str) -> ReviewCase | None:
        for case in self.cases:
            if self.asset_for_case(case.case_id, asset_id):
                return case
        return None


def _load_candidate(row: Any) -> Candidate:
    if not isinstance(row, dict):
        raise BundleValidationError("candidate entry must be an object")
    montage = row.get("montage_asset_id") or row.get("montage")
    if isinstance(montage, dict):
        montage = montage.get("asset_id") or montage.get("id")
    raw_frames = row.get("frame_asset_ids") or row.get("frames") or row.get("assets") or []
    frame_ids = []
    for item in raw_frames:
        if isinstance(item, str):
            frame_ids.append(item)
        elif isinstance(item, dict):
            frame_ids.append(str(item.get("asset_id") or item.get("id") or ""))
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    # Flat candidate fields remain available to templates without trusting client input.
    metadata = {
        **{key: value for key, value in row.items() if key not in {"frames", "frame_asset_ids", "assets", "metadata"}},
        **metadata,
    }
    metadata.setdefault("slice_count", metadata.get("declared_slice_count") or row.get("frame_count"))
    return Candidate(
        candidate_key=str(row.get("candidate_key") or row.get("key") or ""),
        series_uid=str(row.get("series_uid") or row.get("series_instance_uid") or ""),
        role=str(row.get("role") or row.get("candidate_role") or "eligible_top_tied"),
        metadata=metadata,
        montage_asset_id=str(montage) if montage else None,
        frame_asset_ids=tuple(frame_ids),
    )


def _optional_int(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise BundleValidationError("canonical candidate UID fields must be lists of nonempty strings")
    if len(value) != len(set(value)):
        raise BundleValidationError("canonical candidate UID fields must not contain duplicates")
    return value


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
