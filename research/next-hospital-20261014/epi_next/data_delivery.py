"""Publish/verify the exact three-case, locally approved DATA-EVAL contract.

Metadata and byte hashes only. No annotation parsing or DICOM pixel access.
The unchanged pending proposal identifies membership; a separate human approval
receipt supplies permission. A candidate's authorization string grants nothing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

PROPOSAL_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
TRAIN_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
PERMITTED = ["listed_train_SOP_native_DICOM_headers", "listed_train_SOP_local_pixel_decode",
             "listed_train_SOP_official_annotation_bodies", "local_native_overlay_and_GT_vNext"]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_bound(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"SHA mismatch: {Path(path).name}")
    return json.loads(Path(path).read_text())


def check_receipt(receipt):
    if (receipt.get("status") != "APPROVED_EXACT_LOCAL_VALIDATION" or
            receipt.get("proposal_sha256") != PROPOSAL_SHA or
            receipt.get("approved_scope") != PERMITTED or
            receipt.get("approved_case_count") != 3 or receipt.get("approved_sop_count") != 715 or
            receipt.get("permit_pixel_decode") is not True or receipt.get("permit_annotation_bodies") is not True or
            not receipt.get("approval_evidence_reference")):
        raise ValueError("exact human approval receipt required")
    for field in ["permit_remote_transfer", "permit_training", "sealed_test_permitted", "hospital_display_permitted"]:
        if receipt.get(field) is not False:
            raise ValueError(f"approval exceeds local scope: {field}")
    if receipt.get("schema") == "EPI_NEXT_EXACT_DATA_APPROVAL_RECEIPT_V2":
        if receipt.get("permit_local_cpu") is not True or receipt.get("permit_local_mps") is not True:
            raise ValueError("v2 must record local CPU/MPS authorization")
        if not receipt.get("mps_schedule_constraint"):
            raise ValueError("MPS requires coordinator scheduling")
        for field in ["permit_remote_gpu", "permit_paid_compute"]:
            if receipt.get(field) is not False:
                raise ValueError(f"remote/paid scope forbidden: {field}")
    elif receipt.get("permit_gpu") is not False:
        raise ValueError("v1 generic GPU flag must remain false")


def join_scope(proposal, rows):
    cases = proposal.get("cases", [])
    if len(cases) != 3 or len({c["patient_id"] for c in cases}) != 3:
        raise ValueError("exact three distinct cases required")
    by_patient = {}
    for row in rows:
        by_patient.setdefault(row["patient_id"], []).append(row)
    joined = []
    seen = set()
    for case in cases:
        if case["split"] != "train":
            raise ValueError("non-train proposal record")
        selected = by_patient.get(case["patient_id"], [])
        sops = case["source_sops"]
        if (len(sops) != len(set(sops)) or len(selected) != case["frozen_inventory_sop_count"] or
                {r["sop_uid"] for r in selected} != set(sops) or seen.intersection(sops)):
            raise ValueError("exact frozen SOP inventory mismatch")
        seen.update(sops)
        if ({r["series_uid"] for r in selected} != {case["series_uid"]} or
                {r["study_uid"] for r in selected} != set(case["study_uids"]) or
                any(r["split"] != "train" or r["collection"] != "MIDRC-RICORD-1A" or
                    r["label"] != "1" or r["read_error"] or r["modality"] != "CT" for r in selected)):
            raise ValueError("Study/Series/split/label mismatch")
        joined.append({"case_index": case["case_index"], "patient_id": case["patient_id"],
                       "patient_pseudonymous_key": case["patient_pseudonymous_key"], "split": "train",
                       "collection": "MIDRC-RICORD-1A", "study_uids": case["study_uids"],
                       "series_uid": case["series_uid"], "sop_count": len(selected), "rows": selected,
                       "development_used": True, "independent_test_eligible": False,
                       "authorization": {"status": "AUTHORIZED_EXACT_THREE_CASE_LOCAL", "proposal_sha256": PROPOSAL_SHA},
                       "label": {"collection_proxy": 1, "clinical_result": None, "imaging_infection_status": None,
                                 "clinical_adjudication": "NOT_ADJUDICATED", "lesion_count": None,
                                 "annotation_completeness": "UNKNOWN"}})
    if len(seen) != 715:
        raise ValueError("expected exactly 715 SOP")
    return joined


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    Path(path).chmod(0o600)


def publish(proposal_path, receipt_path, header_path, source_root, output, source_commit, version=1):
    os.umask(0o077)
    proposal = read_bound(proposal_path, PROPOSAL_SHA)
    receipt = json.loads(receipt_path.read_text()); check_receipt(receipt)
    train_path = source_root / "outputs/data/formal_split_rule_b_v1/train_manifest.csv"
    if sha256(train_path) != TRAIN_SHA:
        raise ValueError("frozen train SHA mismatch")
    with train_path.open() as stream:
        cases = join_scope(proposal, list(csv.DictReader(stream)))
    header_expected = proposal["source_files"]["existing_header_qa"]["sha256"]
    header = read_bound(header_path, header_expected)
    header_cases = {c["patient_id"]: c for c in header["records"]}
    if set(header_cases) != {c["patient_id"] for c in cases}:
        raise ValueError("prior header QA case mismatch")
    for case in cases:
        h = header_cases[case["patient_id"]]
        if (h["rows"] != case["rows"] or h["study_uids"] != case["study_uids"] or
                h["series_uids"] != [case["series_uid"]]):
            raise ValueError("prior header QA inventory mismatch")
    # Output metadata only, kept inside this DATA-EVAL worktree's ignored tree.
    worktree = Path(__file__).resolve().parents[3]
    output = output.resolve()
    if not output.is_relative_to(worktree / ".local"):
        raise ValueError("delivery must stay in private DATA-EVAL .local")
    output.mkdir(parents=True, exist_ok=True)
    if version not in (1, 2):
        raise ValueError("supported delivery versions: 1, 2")
    if version == 2 and receipt.get("schema") != "EPI_NEXT_EXACT_DATA_APPROVAL_RECEIPT_V2":
        raise ValueError("v2 receipt required for v2 publication")
    suffix = "" if version == 1 else "_v2"
    allowlist_path = output / f"three_case_allowlist{suffix}.json"
    delivery_path = output / f"data_delivery{suffix}.json"
    if allowlist_path.exists() or delivery_path.exists():
        raise ValueError("refuse overwrite of published contract")
    allowlist = {"schema": "EPI_NEXT_APPROVED_THREE_CASE_ALLOWLIST_V1", "status": "APPROVED_EXACT_LOCAL_VALIDATION",
                 "proposal_path": str(proposal_path.resolve()), "proposal_sha256": PROPOSAL_SHA,
                 "approval_receipt_path": str(receipt_path.resolve()), "approval_receipt_sha256": sha256(receipt_path),
                 "source_root": str(source_root.resolve()), "train_manifest_sha256": TRAIN_SHA,
                 "records": cases, "case_count": 3, "sop_count": 715}
    if version == 2:
        allowlist["schema"] = "EPI_NEXT_APPROVED_THREE_CASE_ALLOWLIST_V2"
    write_new(allowlist_path, allowlist)
    spatial_cases = []
    for case in cases:
        h = header_cases[case["patient_id"]]
        spatial_cases.append({"case_index": case["case_index"], "patient_id": case["patient_id"],
                              "header_only_qa": h["native_header_qa"], "image_sizes_rc": h["image_sizes_rc"],
                              "pixel_spacing_rc_mm": h["pixel_spacing_rc_mm"], "rescale_pairs": h["rescale_pairs"],
                              "volume_shape_krc": [case["sop_count"], *h["image_sizes_rc"][0]],
                              "ordered_sop_uids": None, "affine_lps": None, "native_header_ledger": None,
                              "inverse_transform_ledger": None, "resampled_volume_path": None,
                              "new_mapping_status": "NOT RUN"})
    delivery = {"schema": "EPI_NEXT_DATA_DELIVERY_V1", "status": "ALLOWLIST_RELEASED_GT_AND_VOLUME_LEDGER_NOT_RUN",
                "owner": "DATA-EVAL", "worktree": str(worktree), "branch": "codex/epi-next-data-eval-20261009",
                "source_commit": source_commit, "publication_source_sha256": sha256(Path(__file__)),
                "allowlist_path": str(allowlist_path), "allowlist_sha256": sha256(allowlist_path),
                "authorization_reference": {"proposal_path": str(proposal_path.resolve()), "proposal_sha256": PROPOSAL_SHA,
                                            "receipt_path": str(receipt_path.resolve()), "receipt_sha256": sha256(receipt_path),
                                            "evidence_scope": "explicit human approval relayed by coordinator; exact three-case local use only"},
                "case_count": 3, "sop_count": 715, "split_counts": {"train": 3, "val": 0, "test": 0},
                "label_definition": {"status": "COLLECTION_PROXY_VERIFIED_CLINICAL_LABEL_UNKNOWN", "collection_proxy": 1,
                                     "meaning": "source-derived RICORD-1A membership; not lesion GT or clinical adjudication",
                                     "clinical_result": None, "imaging_infection_status": None, "lesion_count": None,
                                     "clinical_adjudication": "NOT_ADJUDICATED", "annotation_completeness": "UNKNOWN",
                                     "evidence_scope": "hash-verified frozen train metadata; no new clinical source parse"},
                "gt_vnext": {"version": "GT-vNext-three-case-dev-v1", "path": None, "manifest_sha256": None,
                              "status": "NOT RUN", "overlays_path": None, "complete_metrics_eligible": False,
                              "evidence_scope": "synthetic preparation only; no usable real GT asset published"},
                "spatial_mapping": {"status": "PRIOR_HEADER_ONLY_QA_AVAILABLE_VOLUME_LEDGER_NOT_RUN",
                                    "header_qa_path": str(header_path.resolve()), "header_qa_sha256": header_expected,
                                    "cases": spatial_cases, "world_convention": "DICOM_LPS_MM",
                                    "array_convention": "slice,row,column", "resampling_status": "NOT RUN",
                                    "evidence_scope": "existing exact three-case header-only QA; no published SOP ordering/affine ledger or pixel volume"},
                "consumer_contract": {"verify_delivery_sha256_before_read": True, "verify_allowlist_and_receipt_sha256": True,
                                      "verify_exact_Study_Series_SOP_before_any_pixel_or_annotation_use": True,
                                      "derive_new_allowlist": False, "coordinate_mapping_owner": "DATA-EVAL",
                                      "local_use_only": True, "hospital_display": "NOT_AUTHORIZED",
                                      "sealed_test": "NOT_AUTHORIZED", "training": "NOT_AUTHORIZED_BY_THIS_DATA_RECEIPT",
                                      "gpu": "NOT_AUTHORIZED", "external_transfer": "NOT_AUTHORIZED",
                                      "independent_test_claim": "NOT_ELIGIBLE_DEVELOPMENT_CASES"},
                "historical_out_of_scope": {"path": str(worktree / ".local/gt-vnext-20261009/development_scope_allowlist.json"),
                                            "status": "NOT_APPROVED_DO_NOT_CONSUME", "case_count": 80,
                                            "evidence_scope": "historical generated metadata; no access grant"}}
    if version == 2:
        delivery["schema"] = "EPI_NEXT_DATA_DELIVERY_V2"
        # Membership is byte-for-byte the same semantic list; only authority
        # receipt version changes. Never derive a new cohort or SOP selection.
        delivery["supersedes"] = {"path": str(output / "data_delivery.json"),
                                  "sha256": sha256(output / "data_delivery.json"),
                                  "reason": "separate local CPU/MPS from remote/paid GPU authorization"}
        contract = delivery["consumer_contract"]
        del contract["gpu"]
        contract.update(local_cpu="ALLOWED", local_mps="ALLOWED_SUBJECT_TO_COORDINATOR_SERIAL_SCHEDULE",
                        mps_current_owner="ENCODER", remote_gpu="NOT_AUTHORIZED", paid_compute="NOT_AUTHORIZED",
                        hospital_display="NOT_AUTHORIZED", f0_training="NOT_AUTHORIZED")
    write_new(delivery_path, delivery)
    return delivery_path, sha256(delivery_path)


def verify_delivery(path, expected_sha):
    delivery = read_bound(path, expected_sha)
    auth = delivery["authorization_reference"]
    read_bound(auth["proposal_path"], PROPOSAL_SHA)
    receipt = read_bound(auth["receipt_path"], auth["receipt_sha256"]); check_receipt(receipt)
    allowlist = read_bound(delivery["allowlist_path"], delivery["allowlist_sha256"])
    if allowlist["proposal_sha256"] != PROPOSAL_SHA or allowlist["approval_receipt_sha256"] != auth["receipt_sha256"]:
        raise ValueError("allowlist authority mismatch")
    train = Path(allowlist["source_root"]) / "outputs/data/formal_split_rule_b_v1/train_manifest.csv"
    if sha256(train) != TRAIN_SHA:
        raise ValueError("train manifest changed")
    with train.open() as stream:
        joined = join_scope(read_bound(auth["proposal_path"], PROPOSAL_SHA), list(csv.DictReader(stream)))
    if allowlist["records"] != joined or delivery["case_count"] != 3 or delivery["sop_count"] != 715:
        raise ValueError("released membership mismatch")
    spatial = delivery["spatial_mapping"]
    read_bound(spatial["header_qa_path"], spatial["header_qa_sha256"])
    if delivery["schema"] == "EPI_NEXT_DATA_DELIVERY_V3":
        gt = delivery["gt_vnext"]
        manifest = read_bound(gt["path"], gt["manifest_sha256"])
        if manifest["allowlist_sha256"] != delivery["allowlist_sha256"] or manifest["counts"]["patients"] != 3 or manifest["counts"]["sops"] != 715:
            raise ValueError("GT-vNext membership mismatch")
        if {c["patient_id"] for c in manifest["cases"]} != {c["patient_id"] for c in joined}:
            raise ValueError("GT-vNext patient set mismatch")
        qa = read_bound(gt["asset_qa_path"], gt["asset_qa_sha256"])
        visual = read_bound(gt["visual_qa_path"], gt["visual_qa_sha256"])
        if qa["source_manifest_sha256"] != gt["manifest_sha256"] or visual["source_manifest_sha256"] != gt["manifest_sha256"]:
            raise ValueError("GT QA bound to another asset")
        read_bound(delivery["label_definition"]["path"], delivery["label_definition"]["sha256"])
        protocol_ref = delivery["evaluation_protocol"]
        protocol = read_bound(protocol_ref["path"], protocol_ref["sha256"])
        read_bound(protocol_ref["request_template_path"], protocol_ref["request_template_sha256"])
        if protocol["gt_manifest_sha256"] != gt["manifest_sha256"] or {c["patient_id"] for c in protocol["cases"]} != {c["patient_id"] for c in joined}:
            raise ValueError("evaluation protocol bound to another asset")
        asset_root = Path(gt["path"]).parent
        spatial_cases = {c["patient_id"]: c for c in spatial["cases"]}
        for reference in manifest["cases"]:
            case = read_bound(asset_root / reference["manifest_path"], reference["manifest_sha256"])
            ledger = spatial_cases[case["patient_id"]]
            if ledger["manifest_sha256"] != reference["manifest_sha256"] or ledger["ordered_sop_uids"] != case["native_volume"]["ordered_sop_uids"] or ledger["affine_lps"] != case["geometry"]["affine_lps"]:
                raise ValueError("published spatial ledger differs from native case")
            if sha256(ledger["native_hu_volume_path"]) != ledger["native_hu_volume_sha256"]:
                raise ValueError("native HU volume changed")
        for entry in protocol["cases"]:
            if sha256(entry["support_path"]) != entry["support_sha256"]:
                raise ValueError("predeclared common support changed")
    return delivery


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--header-qa", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--version", type=int, choices=[1, 2], default=1)
    parser.add_argument("--verify-delivery", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.verify_delivery:
        if not args.sha256:
            parser.error("--sha256 is required for verification")
        document = verify_delivery(args.verify_delivery, args.sha256)
        print(json.dumps({"status": "VERIFIED", "cases": document["case_count"], "sops": document["sop_count"], "sha256": args.sha256}))
    else:
        if any(value is None for value in [args.proposal, args.receipt, args.header_qa, args.source_root, args.output, args.source_commit]):
            parser.error("publication requires proposal, receipt, header QA, source root, output and source commit")
        path, checksum = publish(args.proposal, args.receipt, args.header_qa, args.source_root, args.output, args.source_commit, args.version)
        print(json.dumps({"path": str(path), "sha256": checksum}))
