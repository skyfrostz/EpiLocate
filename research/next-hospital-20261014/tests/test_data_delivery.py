import pytest

from epi_next.data_delivery import PERMITTED, PROPOSAL_SHA, check_receipt, join_scope, read_bound


def receipt():
    return {"status": "APPROVED_EXACT_LOCAL_VALIDATION", "proposal_sha256": PROPOSAL_SHA,
            "approved_scope": PERMITTED.copy(), "approved_case_count": 3, "approved_sop_count": 715,
            "permit_pixel_decode": True, "permit_annotation_bodies": True,
            "approval_evidence_reference": {"kind": "human_approval"},
            **{k: False for k in ["permit_remote_transfer", "permit_training", "permit_gpu",
                                  "sealed_test_permitted", "hospital_display_permitted"]}}


def scope():
    cases, rows = [], []
    for i, count in enumerate([223, 244, 248]):
        sops = [f"synthetic-sop-{i}-{j}" for j in range(count)]
        cases.append({"case_index": i + 1, "patient_id": f"synthetic-{i}", "patient_pseudonymous_key": f"key-{i}",
                      "split": "train", "frozen_inventory_sop_count": count, "source_sops": sops,
                      "series_uid": f"synthetic-series-{i}", "study_uids": [f"synthetic-study-{i}"]})
        rows.extend({"patient_id": f"synthetic-{i}", "split": "train", "collection": "MIDRC-RICORD-1A",
                     "sop_uid": s, "series_uid": f"synthetic-series-{i}", "study_uid": f"synthetic-study-{i}",
                     "label": "1", "read_error": "", "modality": "CT"} for s in sops)
    return {"cases": cases}, rows


def test_exact_scope_unknown_labels():
    proposal, rows = scope()
    result = join_scope(proposal, rows)
    assert sum(r["sop_count"] for r in result) == 715
    assert all(r["label"]["clinical_result"] is None and not r["independent_test_eligible"] for r in result)


@pytest.mark.parametrize("field,value", [("status", "PENDING"), ("proposal_sha256", "f" * 64),
                                           ("approved_case_count", 80), ("permit_pixel_decode", False),
                                           ("hospital_display_permitted", True), ("sealed_test_permitted", True),
                                           ("permit_training", True), ("permit_gpu", True),
                                           ("approval_evidence_reference", None)])
def test_missing_or_expanded_approval_rejected(field, value):
    item = receipt(); item[field] = value
    with pytest.raises(ValueError):
        check_receipt(item)


def test_exact_receipt():
    check_receipt(receipt())


def v2_receipt():
    item = receipt(); item.pop("permit_gpu")
    item.update(schema="EPI_NEXT_EXACT_DATA_APPROVAL_RECEIPT_V2", permit_local_cpu=True, permit_local_mps=True,
                permit_remote_gpu=False, permit_paid_compute=False, mps_schedule_constraint="coordinator serial schedule")
    return item


def test_v2_local_mps_is_not_remote_gpu_permission():
    check_receipt(v2_receipt())


@pytest.mark.parametrize("field,value", [("permit_remote_gpu", True), ("permit_paid_compute", True),
                                           ("mps_schedule_constraint", None), ("hospital_display_permitted", True)])
def test_v2_resource_scope_stays_bounded(field, value):
    item = v2_receipt(); item[field] = value
    with pytest.raises(ValueError):
        check_receipt(item)


@pytest.mark.parametrize("mutation", ["duplicate_sop", "missing_sop", "extra_sop", "wrong_series", "test"])
def test_membership_mutations_rejected(mutation):
    proposal, rows = scope()
    if mutation == "duplicate_sop":
        proposal["cases"][0]["source_sops"][1] = proposal["cases"][0]["source_sops"][0]
    elif mutation == "missing_sop":
        rows.pop()
    elif mutation == "extra_sop":
        rows.append({**rows[-1], "sop_uid": "unapproved-sop"})
    elif mutation == "wrong_series":
        rows[0]["series_uid"] = "other-series"
    else:
        proposal["cases"][0]["split"] = "test"
    with pytest.raises(ValueError):
        join_scope(proposal, rows)


def test_hash_before_json_parse(tmp_path):
    path = tmp_path / "tampered.json"; path.write_text("not valid json")
    with pytest.raises(ValueError, match="SHA mismatch"):
        read_bound(path, "0" * 64)
