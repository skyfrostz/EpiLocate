import io
import json
from zipfile import ZipFile

import pytest

from epi_next.bounded_study_parser import Scanner, FIELDS
import epi_next.study_labels as labels


def export_bytes(records):
    groups = [{"labels": [{"name": "Infectious lung disease", "id": "infection", "scope": "STUDY", "type": "GLOBAL", "note": {"ignored": "synthetic"}},
                          {"name": "Normal lung", "id": "normal", "scope": "STUDY", "type": "GLOBAL"},
                          {"name": "Infectious opacity", "id": "other", "scope": "INSTANCE", "type": "LOCAL"}], "id": "synthetic-group"}]
    return ('{"labelGroups":' + json.dumps(groups) + ',"datasets":[{"annotations":[' + ','.join(records) + ']}]}').encode()


def annotation(study="study-a", label="infection", **updates):
    value = {"id": study + "-" + label, "StudyInstanceUID": study, "labelId": label,
             "createdById": "synthetic-reader", "groupId": "synthetic-group", "data": None}
    value.update(updates)
    return json.dumps(value)


def test_selective_dictionary_and_body_projection():
    unknown = annotation("outside").replace('"data": null', '"data":{"bad":NOT_JSON}')
    other = annotation(label="other").replace('"data": null', '"data":{"bad":NOT_JSON}')
    raw = export_bytes([unknown, other, annotation(note={"ignored": "synthetic"})])
    dictionary = labels.dictionary(Scanner(io.BytesIO(raw)))
    assert set(dictionary) == {"infection", "normal"}
    assert set(dictionary["infection"]) == {"id", "name", "scope", "type", "label_group_id"}
    result = list(labels.annotations(Scanner(io.BytesIO(raw)), {"study-a"}, dictionary))
    assert len(result) == 1 and set(result[0]) <= FIELDS


def test_non_null_data_is_quarantined_without_interpretation():
    raw = export_bytes([annotation().replace('"data": null', '"data":{"bad":NOT_JSON}')])
    rows = list(labels.annotations(Scanner(io.BytesIO(raw)), {"study-a"}, {"infection"}))
    assert rows[0]["_quarantine"] == "GLOBAL_DATA_NOT_EXPLICIT_NULL"


@pytest.mark.parametrize("strata,quarantine,complete,status", [
    ({}, 0, True, "UNKNOWN"),
    ({("r", "g"): {"Normal lung"}}, 0, True, "NEGATIVE"),
    ({("r", "g"): {"Infectious lung disease"}}, 0, True, "POSITIVE"),
    ({("r", "g"): set(labels.NAMES)}, 0, True, "CONFLICT"),
    ({("r", "g"): {"Normal lung"}, ("s", "g"): {"Infectious lung disease"}}, 0, True, "CONFLICT"),
    ({(None, "g"): {"Normal lung"}}, 0, True, "UNKNOWN"),
    ({("r", "g"): {"Normal lung"}}, 1, True, "UNKNOWN"),
    ({("r", "g"): {"Normal lung"}}, 0, False, "UNKNOWN"),
])
def test_explicit_statuses(strata, quarantine, complete, status):
    assert labels.study_result(strata, quarantine, complete)[0] == status


def bind_fixture(tmp_path, monkeypatch, records):
    archive = tmp_path / "synthetic.zip"
    with ZipFile(archive, "w") as writer:
        writer.writestr("synthetic.json", export_bytes(records))
    monkeypatch.setattr(labels, "SOURCE_SHA", labels.digest(archive))
    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return {"path": str(path), "sha256": labels.digest(path)}
    scope = {"exact_studies": [{"StudyInstanceUID": s, "SeriesInstanceUID": s + "-series", "patient_id": "synthetic-" + s, "split": "train"} for s in ("study-a", "study-b", "study-c")],
             "annotation_fields": sorted(FIELDS), "annotation_source_sha256": labels.SOURCE_SHA, "annotation_source_path": str(archive)}
    proposal = write("proposal.json", {"access_stage1": scope})
    monkeypatch.setattr(labels, "PROPOSAL_SHA", proposal["sha256"])
    request = write("request.json", {"labels": {"proposal": proposal, "annotation_fields": sorted(FIELDS), "stage": "STAGE1_ONLY"}})
    monkeypatch.setattr(labels, "REQUEST_SHA", request["sha256"])
    approval = write("approval.json", {"status": "APPROVED_WITH_HARD_LIMIT_EXECUTION_GATE", "request": request, "approved": {"DATA": "Stage1 exact3Study exact2labels and fields in request only; no clinical.xlsx"}})
    monkeypatch.setattr(labels, "APPROVAL_SHA", approval["sha256"])
    revision = write("revision.json", {"status": "APPROVED_RESOURCE_SEMANTICS_REVISION", "original_approval": approval,
                                      "request": request, "study_proposal": proposal,
                                      "protection": {"rss_pre_stop_bytes": labels.PRE_STOP, "rss_target_bytes": 6 * 1024 ** 3}})
    monkeypatch.setattr(labels, "REVISION_SHA", revision["sha256"])
    return revision["path"], archive


def test_synthetic_zip_bound_execution_and_missing_unknown(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation(), annotation("study-b", "normal"), annotation("outside")])
    result = labels.execute(revision, tmp_path / "output", tmp_path / "stop")
    assert result["status"] == "COMPLETE"
    assert result["case_status_counts"] == {"POSITIVE": 1, "NEGATIVE": 1, "UNKNOWN": 1}
    assert result["selected_count"] == 2 and result["forwards"] == 0
    assert len((tmp_path / "output" / "annotations.jsonl").read_text().splitlines()) == 2
    with pytest.raises(FileExistsError):
        labels.execute(revision, tmp_path / "output", tmp_path / "stop")


def test_tampered_approval_fails_before_zip_open(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation()])
    (tmp_path / "approval.json").write_text('{}')
    monkeypatch.setattr(labels, "ZipFile", lambda *args: pytest.fail("ZIP must not open"))
    result = labels.execute(revision, tmp_path / "output", tmp_path / "stop")
    assert result["status"] == "FAILED" and not result["cases"]


def test_stop_preserves_partial_receipt(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation()])
    stop = tmp_path / "stop"
    stop.touch()
    result = labels.execute(revision, tmp_path / "output", stop)
    assert result["status"] == "STOPPED_PARTIAL" and result["reason"] == "STOP_FILE"
    assert (tmp_path / "output" / "receipt.json").exists()


def test_failure_after_one_row_preserves_unknown(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation(), annotation(id="study-a-infection")])
    result = labels.execute(revision, tmp_path / "output", tmp_path / "stop")
    assert result["status"] == "FAILED"
    assert result["case_status_counts"] == {"UNKNOWN": 3}
    assert len((tmp_path / "output" / "annotations.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("fault,reason", [("clock", "TIME_BUDGET"), ("rss", "RSS_PRE_STOP")])
def test_guard_faults(fault, reason, tmp_path, monkeypatch):
    guard = labels.Guard(tmp_path / "stop")
    if fault == "clock":
        monkeypatch.setattr(labels.time, "monotonic", lambda: guard.start + 121)
    else:
        from types import SimpleNamespace
        import sys
        rss = labels.PRE_STOP if sys.platform == "darwin" else labels.PRE_STOP // 1024
        monkeypatch.setattr(labels.resource, "getrusage", lambda _: SimpleNamespace(ru_maxrss=rss))
    with pytest.raises(labels.StopRequested, match=reason):
        guard.check()


def test_stop_after_first_row_preserves_cooperative_partial(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation(), annotation("study-b", "normal")])
    stop = tmp_path / "stop"
    original = labels.annotations
    def interrupted(*args):
        for row in original(*args):
            yield row
            stop.touch()
    monkeypatch.setattr(labels, "annotations", interrupted)
    result = labels.execute(revision, tmp_path / "output", stop)
    assert result["status"] == "STOPPED_PARTIAL" and result["reason"] == "STOP_FILE"
    assert result["case_status_counts"] == {"UNKNOWN": 3}
    assert len((tmp_path / "output" / "annotations.jsonl").read_text().splitlines()) == 1


def test_shared_checkpoint_failure_stops_before_archive(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation()])
    calls = []
    def failed_monitor():
        calls.append(1)
        raise labels.StopRequested("SHARED_MONITOR_FAILURE")
    monkeypatch.setattr(labels, "ZipFile", lambda *args: pytest.fail("ZIP must not open"))
    result = labels.execute(revision, tmp_path / "output", tmp_path / "stop", shared_check=failed_monitor)
    assert result["status"] == "STOPPED_PARTIAL"
    assert result["reason"] == "SHARED_MONITOR_FAILURE" and calls == [1]
