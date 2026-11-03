"""Exact approved STUDY label extraction; streaming, no images or models.

Execution requires external serial dispatch. Limits bound parsing and trigger
cooperative stops; independent supervisor provides sampled resource protection.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import types
from zipfile import ZipFile

from .bounded_study_parser import Scanner, annotation_fields, scalar, FIELDS

REVISION_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
APPROVAL_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
REQUEST_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
PROPOSAL_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
SOURCE_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
NAMES = frozenset({"Infectious lung disease", "Normal lung"})
PRE_STOP = 5 * 1024 ** 3
SECONDS = 120
SHARED_MODULES = frozenset({"wave1_supervisor.py", "artifacts.py", "coordinator_writer.py",
                            "execution_lock.py", "hospital_runtime.py", "hospital_contract.py",
                            "contracts.py", "geometry.py"})


def load_shared(package, manifest_path, manifest_sha, module_sha):
    """Separate pinned package namespace; no DATA relative-import fallback."""
    package = Path(package).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    if digest(manifest_path) != manifest_sha or manifest_path.stat().st_size > 131072:
        raise ValueError("shared import manifest mismatch")
    manifest = json.loads(manifest_path.read_bytes())
    files = manifest["files"]
    if set(files) != SHARED_MODULES or files["wave1_supervisor.py"] != module_sha:
        raise ValueError("complete shared import closure required")
    for name, expected in files.items():
        path = package / name
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("shared snapshot source mismatch")
    namespace = "_epi_next_wave1_pinned_" + manifest_sha[:16]
    if namespace in sys.modules:
        raise ValueError("shared namespace already loaded")
    parent = types.ModuleType(namespace)
    # No filesystem fallback or cached bytecode: compile exact verified bytes.
    parent.__path__ = []
    parent.__package__ = namespace
    sys.modules[namespace] = parent
    order = ("artifacts", "contracts", "geometry", "coordinator_writer", "hospital_contract",
             "hospital_runtime", "execution_lock", "wave1_supervisor")
    for short in order:
        path = package / (short + ".py")
        raw = path.read_bytes()
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != files[path.name]:
            raise ValueError("shared source changed before compile")
        module = types.ModuleType(namespace + "." + short)
        module.__file__ = str(path)
        module.__package__ = namespace
        sys.modules[module.__name__] = module
        setattr(parent, short, module)
        exec(compile(raw, str(path), "exec"), module.__dict__)
    shared = parent.wave1_supervisor
    bindings = []
    for name, module in list(sys.modules.items()):
        if not name.startswith(namespace + "."):
            continue
        path = Path(module.__file__).resolve(strict=True)
        if path.parent != package or path.name not in files or digest(path) != files[path.name]:
            raise ValueError("actual shared import outside pinned closure")
        bindings.append({"module": name, "path": str(path), "sha256": files[path.name]})
    if {Path(row["path"]).name for row in bindings} != SHARED_MODULES:
        raise ValueError("unverified shared import closure")
    return shared, bindings


class StopRequested(RuntimeError):
    pass


class Guard:
    def __init__(self, stop_file, shared_check=None):
        self.start = time.monotonic()
        self.stop_file = Path(stop_file)
        self.checks = 0
        self.peak_rss = 0
        self.shared_check = shared_check

    def check(self):
        if self.shared_check is not None:
            self.shared_check()
        self.checks += 1
        # macOS getrusage reports bytes, Linux KiB; this is a high-water sample,
        # not the independent current-RSS/unified-pressure monitor.
        import sys
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = int(rss if sys.platform == "darwin" else rss * 1024)
        self.peak_rss = max(self.peak_rss, rss)
        if self.stop_file.exists():
            raise StopRequested("STOP_FILE")
        if time.monotonic() - self.start >= SECONDS:
            raise StopRequested("TIME_BUDGET")
        if rss >= PRE_STOP:
            raise StopRequested("RSS_PRE_STOP")


class GuardedStream:
    def __init__(self, stream, guard):
        self.stream, self.guard = stream, guard

    def read(self, size):
        self.guard.check()
        return self.stream.read(size)


def digest(path, guard=None):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            if guard:
                guard.check()
            block = stream.read(65536)
            if not block:
                break
            value.update(block)
    return value.hexdigest()


def bound_json(path, expected, guard):
    if digest(path, guard) != expected:
        raise ValueError("bound metadata hash mismatch")
    if Path(path).stat().st_size > 131072:
        raise ValueError("metadata size bound")
    return json.loads(Path(path).read_bytes())


def verify_scope(revision_path, guard):
    revision = bound_json(revision_path, REVISION_SHA, guard)
    if revision.get("status") != "APPROVED_RESOURCE_SEMANTICS_REVISION":
        raise ValueError("resource revision not approved")
    if revision["original_approval"]["sha256"] != APPROVAL_SHA or revision["request"]["sha256"] != REQUEST_SHA:
        raise ValueError("authorization binding mismatch")
    approval = bound_json(revision["original_approval"]["path"], APPROVAL_SHA, guard)
    request = bound_json(revision["request"]["path"], REQUEST_SHA, guard)
    if approval.get("status") != "APPROVED_WITH_HARD_LIMIT_EXECUTION_GATE":
        raise ValueError("approved original receipt required with resource revision")
    if approval.get("approved", {}).get("DATA") != "Stage1 exact3Study exact2labels and fields in request only; no clinical.xlsx":
        raise ValueError("Stage1 approval required")
    if approval.get("request") != revision["request"]:
        raise ValueError("approval request mismatch")
    proposal_ref = revision["study_proposal"]
    if proposal_ref != request["labels"]["proposal"] or proposal_ref["sha256"] != PROPOSAL_SHA:
        raise ValueError("proposal binding mismatch")
    proposal = bound_json(proposal_ref["path"], PROPOSAL_SHA, guard)
    scope = proposal["access_stage1"]
    studies = scope["exact_studies"]
    if len(studies) != 3 or len({s["StudyInstanceUID"] for s in studies}) != 3 or any(s["split"] != "train" for s in studies):
        raise ValueError("exact three train Studies required")
    if set(scope["annotation_fields"]) != FIELDS or set(request["labels"]["annotation_fields"]) != FIELDS:
        raise ValueError("field scope mismatch")
    if scope["annotation_source_sha256"] != SOURCE_SHA or request["labels"]["stage"] != "STAGE1_ONLY":
        raise ValueError("source/stage scope mismatch")
    protection = revision["protection"]
    if protection["rss_pre_stop_bytes"] != PRE_STOP or protection["rss_target_bytes"] != 6 * 1024 ** 3:
        raise ValueError("resource scope mismatch")
    return scope


def seek_array(scanner, wanted):
    """Locate a named array lexically, skip unrelated strings without retention.

    Repeated structure is traversed to find MD.ai nested labelGroups/annotations;
    no unknown body is JSON-decoded. First occurrence only, like prior export
    framing; hash-bound source layout compatibility remains an execution check.
    """
    depth = 0
    while scanner.peek() is not None:
        scanner.space()
        char = scanner.peek()
        if char == 34:
            raw = scanner.value(capture=True)
            scanner.space()
            if scanner.peek() == 58:
                scanner.take()
                if json.loads(raw) == wanted:
                    scanner.expect(91)
                    return
                scanner.space()
                if scanner.peek() not in (123, 91):
                    scanner.value()
        elif char in (123, 91):
            scanner.take()
            depth += 1
            if depth > 64:
                raise ValueError("navigation depth bound")
        elif char in (125, 93):
            scanner.take()
            depth -= 1
            if depth < 0:
                raise ValueError("invalid navigation structure")
        elif char in (44, 58):
            scanner.take()
        elif char is None:
            break
        else:
            scanner.value()
    raise ValueError("required array absent")


def raw_scalar_fields(scanner, wanted):
    scanner.expect(123)
    values = {}
    scanner.space()
    if scanner.peek() == 125:
        scanner.take()
        return values
    while True:
        key = scalar(scanner.value(capture=True))
        scanner.expect(58)
        scanner.space()
        if key in wanted:
            if key in values:
                raise ValueError("duplicate dictionary key")
            if scanner.peek() not in (34, 110):
                raise ValueError("dictionary scalar required")
            values[key] = scanner.value(capture=True)
        else:
            scanner.value()
        scanner.space()
        end = scanner.take()
        if end == 125:
            return values
        if end != 44:
            raise ValueError("dictionary delimiter")
        scanner.space()


def dictionary(scanner):
    seek_array(scanner, "labelGroups")
    selected = {}
    groups = 0
    scanner.space()
    if scanner.peek() == 93:
        scanner.take()
        return selected
    while True:
        groups += 1
        if groups > 128:
            raise ValueError("label group count bound")
        scanner.object_bytes = 0
        scanner.expect(123)
        group_id = None
        matches = []
        seen = set()
        scanner.space()
        while scanner.peek() != 125:
            key = scalar(scanner.value(capture=True))
            scanner.expect(58)
            if key in ("id", "labels"):
                if key in seen:
                    raise ValueError("duplicate group key")
                seen.add(key)
            if key == "id":
                group_id = scanner.value(capture=True)
            elif key == "labels":
                scanner.expect(91)
                scanner.space()
                label_count = 0
                if scanner.peek() != 93:
                    while True:
                        label_count += 1
                        if label_count > 256:
                            raise ValueError("dictionary label count bound")
                        raw = raw_scalar_fields(scanner, {"id", "name", "scope", "type"})
                        identity = {k: scalar(raw[k]) for k in ("name", "scope", "type") if k in raw}
                        if identity.get("name") in NAMES and identity.get("scope") == "STUDY" and identity.get("type") == "GLOBAL":
                            label_id = scalar(raw.get("id"))
                            if not label_id:
                                raise ValueError("matching label missing ID")
                            matches.append({"id": label_id, **identity})
                            if len(matches) > 16:
                                raise ValueError("matching dictionary count bound")
                        scanner.space()
                        end = scanner.take()
                        if end == 93:
                            break
                        if end != 44:
                            raise ValueError("label array delimiter")
                        scanner.space()
                else:
                    scanner.take()
            else:
                scanner.value()
            scanner.space()
            end = scanner.peek()
            if end == 125:
                break
            scanner.expect(44)
            scanner.space()
        scanner.expect(125)
        scanner.object_bytes = None
        for label in matches:
            label["label_group_id"] = scalar(group_id)
            if not label["label_group_id"] or label["id"] in selected:
                raise ValueError("dictionary ID/group ambiguity")
            selected[label["id"]] = label
            if len(selected) > 16:
                raise ValueError("selected dictionary bound")
        scanner.space()
        end = scanner.take()
        if end == 93:
            return selected
        if end != 44:
            raise ValueError("group array delimiter")
        scanner.space()


def annotations(scanner, studies, labels):
    seek_array(scanner, "annotations")
    scanner.space()
    if scanner.peek() == 93:
        scanner.take()
        return
    while True:
        selected = annotation_fields(scanner, studies, labels, quarantine_data=True)
        if selected is not None:
            yield selected
        scanner.space()
        end = scanner.take()
        if end == 93:
            return
        if end != 44:
            raise ValueError("annotation array delimiter")
        scanner.space()


def study_result(strata, quarantine, complete):
    if not complete:
        return "UNKNOWN", "INCOMPLETE_PARSE"
    if quarantine:
        return "UNKNOWN", "QUARANTINED_SOURCE"
    if not strata:
        return "UNKNOWN", "NO_MATCHING_ANNOTATION"
    values = set()
    for (creator, group), names in strata.items():
        if len(names) > 1:
            return "CONFLICT", "BOTH_LABELS_IN_STRATUM"
        if not creator or not group:
            return "UNKNOWN", "MISSING_PROVENANCE"
        values.update(names)
    if len(values) > 1:
        return "CONFLICT", "READERS_DISAGREE"
    return ("POSITIVE" if "Infectious lung disease" in values else "NEGATIVE"), "EXPLICIT_STUDY_LABEL"


def execute(revision_path, output, stop_file, shared_check=None, shared_bindings=None):
    guard = Guard(stop_file, shared_check)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    status = "FAILED"
    reason = None
    selected_count = 0
    scope = None
    labels = {}
    strata = {}
    quarantines = Counter()
    ids = set()
    try:
        if shared_bindings is not None:
            with (output / "shared-imports.json").open("x") as saved:
                json.dump(shared_bindings, saved, indent=2)
        scope = verify_scope(revision_path, guard)
        studies = {s["StudyInstanceUID"] for s in scope["exact_studies"]}
        strata = {study: {} for study in studies}
        source = Path(scope["annotation_source_path"])
        if digest(source, guard) != SOURCE_SHA:
            raise ValueError("annotation ZIP hash mismatch")
        with ZipFile(source) as archive:
            names = [n for n in archive.namelist() if n.endswith(".json") and not n.startswith("__MACOSX/")]
            if len(names) != 1 or len(archive.infolist()) > 128:
                raise ValueError("official archive layout mismatch")
            with archive.open(names[0]) as stream:
                labels = dictionary(Scanner(GuardedStream(stream, guard)))
            with (output / "dictionary.json").open("x") as saved:
                json.dump(list(labels.values()), saved, indent=2)
            # Missing one/both labels does not infer normality.
            with archive.open(names[0]) as stream, (output / "annotations.jsonl").open("x") as saved:
                for fields in annotations(Scanner(GuardedStream(stream, guard)), studies, labels):
                    guard.check()
                    selected_count += 1
                    if selected_count > 4096 or fields["id"] in ids:
                        raise ValueError("annotation count/duplicate ID bound")
                    ids.add(fields["id"])
                    study = fields["StudyInstanceUID"]
                    label = labels[fields["labelId"]]
                    if fields.get("groupId") and fields["groupId"] != label["label_group_id"]:
                        fields["_quarantine"] = "ANNOTATION_DICTIONARY_GROUP_MISMATCH"
                    json.dump(fields, saved, ensure_ascii=False)
                    saved.write("\n")
                    saved.flush()
                    if "_quarantine" in fields:
                        quarantines[study] += 1
                        continue
                    key = (fields.get("createdById"), fields.get("groupId"))
                    strata[study].setdefault(key, set()).add(label["name"])
                    if len(strata[study]) > 256:
                        raise ValueError("provenance stratum bound")
        if digest(source, guard) != SOURCE_SHA:
            raise ValueError("source changed during extraction")
        guard.check()
        status = "COMPLETE"
    except StopRequested as error:
        status, reason = "STOPPED_PARTIAL", str(error)
    except Exception as error:
        # No source object or patient content in diagnostic message.
        reason = type(error).__name__ + ": " + str(error)[:160]
    finally:
        cases = []
        if scope:
            for study in scope["exact_studies"]:
                uid = study["StudyInstanceUID"]
                classification, why = study_result(strata.get(uid, {}), quarantines[uid], status == "COMPLETE")
                cases.append({**study, "target_status": classification, "reason": why,
                              "quarantined_annotation_count": quarantines[uid],
                              "strata": [{"createdById": k[0], "groupId": k[1], "labels": sorted(v)}
                                         for k, v in strata.get(uid, {}).items()],
                              "independent_test_eligible": False})
        receipt = {"schema": "EPI_NEXT_STUDY_LABEL_EXTRACTION_V1", "status": status, "reason": reason,
                   "revision_sha256": REVISION_SHA, "approval_sha256": APPROVAL_SHA,
                   "request_sha256": REQUEST_SHA, "proposal_sha256": PROPOSAL_SHA,
                   "source_sha256": SOURCE_SHA, "selected_count": selected_count,
                   "cases": cases, "case_status_counts": dict(Counter(c["target_status"] for c in cases)),
                   "elapsed_seconds": time.monotonic() - guard.start, "guard_checks": guard.checks,
                   "getrusage_high_water_sample_bytes": guard.peak_rss,
                   "hard_RSS_cap_claimed": False, "resource_semantics": "MONITORED_WITH_ACCEPTED_BLIND_SPOTS",
                   "cpu_threads": 1, "forwards": 0, "backward": 0, "MPS": False,
                   "clinical_xlsx_read": False, "new_patient_pixels_read": False,
                   "files": [{"name": p.name, "sha256": digest(p)} for p in sorted(output.iterdir()) if p.is_file()]}
        with (output / "receipt.json").open("x") as saved:
            json.dump(receipt, saved, indent=2, ensure_ascii=False)
        for path in output.iterdir():
            if path.is_file():
                path.chmod(0o600)
    return receipt


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--resource-revision", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--stop-file", required=True)
    cli.add_argument("--supervisor-package", required=True,
                     help="Hash-bound snapshot's epi_next package directory")
    cli.add_argument("--supervisor-module-sha256", required=True)
    cli.add_argument("--supervisor-import-manifest", required=True)
    cli.add_argument("--supervisor-import-manifest-sha256", required=True)
    args = cli.parse_args()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    shared, bindings = load_shared(args.supervisor_package, args.supervisor_import_manifest,
                                   args.supervisor_import_manifest_sha256, args.supervisor_module_sha256)
    child = shared.ChildGuard.from_environment()
    receipt = None
    failure = None
    def checkpoint():
        try:
            child.check()
        except shared.StopWork as error:
            raise StopRequested("SHARED_" + str(error)) from error
    try:
        if child.spec.owner != "DATA" or child.spec.device != "cpu" or child.spec.max_forward != 0 or child.spec.max_backward != 0 or child.spec.timeout_seconds != SECONDS:
            raise ValueError("exact DATA zero-call CPU120s supervision required")
        if Path(args.stop_file).resolve() != (child.directory / "STOP").resolve():
            raise ValueError("stop-file must bind supervisor job")
        receipt = execute(args.resource_revision, args.output, args.stop_file,
                          shared_check=checkpoint, shared_bindings=bindings)
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        terminal = ("SUCCESS" if receipt and receipt["status"] == "COMPLETE" else
                    "PARTIAL_BUDGET" if receipt and receipt["status"] == "STOPPED_PARTIAL" else "FAILED")
        receipt_path = Path(args.output).resolve() / "receipt.json"
        reason = {"data_status": receipt["status"] if receipt else None,
                  "data_receipt_path": str(receipt_path) if receipt else None,
                  "data_receipt_sha256": digest(receipt_path) if receipt else None,
                  "failure_type": failure}
        # complete() invokes close(): joins telemetry, emits last CPU recovery
        # heartbeat, restores handlers, then exclusively writes job completion.
        child.complete(terminal, reason=reason, device_recovered=True,
                       actual_forward=0, actual_backward=0)
    print(json.dumps({"status": receipt["status"], "selected_count": receipt["selected_count"], "case_status_counts": receipt["case_status_counts"]}))
    return 0 if receipt["status"] in {"COMPLETE", "STOPPED_PARTIAL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
