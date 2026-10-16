"""One approved pair, bounded ZIP/gzip/NIfTI qualification; default metadata only.

No networking, models, resampling or queue implementation. Real CLI execution
requires a new exact owner approval and the original shared exclusive supervisor.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import stat
import struct
import sys
import time
import zipfile
import zlib

SCHEMA = 'R124_FIRST_CASE_QUALIFICATION_REQUEST_V1'
APPROVAL = 'R124_FIRST_CASE_QUALIFICATION_APPROVAL_V1'
LIMITS = dict(inner_gzip_max_per_member_bytes=536870912,
    inner_gzip_max_pair_bytes=1073741824, local_zip_read_bytes=104857600,
    chunk_bytes=65536, temp_disk_bytes=1342177280,
    output_metadata_bytes=33554432, disk_reserve_bytes=2147483648,
    seconds=300, RSS_bytes=268435456, max_native_voxels_per_member=134217728,
    max_native_plane_voxels=4194304, working_numeric_buffer_cap_bytes=16777216,
    tolerance_world_mm=1e-4, roundtrip_vox=1e-5, max_export_bytes=104857600,
    max_native_depth=4096, max_mask_values=64)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def identity(s):
    return dict(bytes=s.st_size, device=s.st_dev, inode=s.st_ino, mtime_ns=s.st_mtime_ns)


def no_symlinks(path):
    p = Path(path).absolute()
    require(not any(x.is_symlink() for x in (p, *p.parents)), 'SYMLINK_PATH_DENIED')


def check_archive(ref, fd=None):
    no_symlinks(ref['path'])
    s = Path(ref['path']).lstat() if fd is None else os.fstat(fd)
    require(stat.S_ISREG(s.st_mode) and identity(s) ==
            {k: ref[k] for k in ('bytes', 'device', 'inode', 'mtime_ns')}, 'ARCHIVE_STAT_IDENTITY_DRIFT')


def bound_file(ref, forbidden_inodes=()):
    no_symlinks(ref['path']); p = Path(ref['path'])
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        require((s.st_dev, s.st_ino) not in forbidden_inodes, 'ARCHIVE_ALIAS_HASH_FORBIDDEN')
        require(stat.S_ISREG(s.st_mode) and s.st_size <= 64*1024**2, 'BINDING_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(64*1024**2+1)
        require(len(raw) <= 64*1024**2 and len(raw) == s.st_size and
                identity(os.fstat(fd)) == identity(s) == identity(p.lstat()), 'BINDING_IDENTITY_OR_SIZE_DRIFT')
    finally:
        os.close(fd)
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'BINDING_SHA_DRIFT')
    if 'bytes' in ref:
        require(len(raw) == ref['bytes'], 'BINDING_SIZE_DRIFT')
    return raw


def validate(q):
    """Only stat and bound code/evidence; never open an archive or create output."""
    require(len(q['targets']) == 2 and [x['role'] for x in q['targets']] ==
            ['CT', 'INFECTION_MASK'], 'EXACT_PAIR_ROLES')
    for k, cap in LIMITS.items():
        require(type(q['limits'][k]) is type(cap) and 0 < q['limits'][k] <= cap, 'LIMITS_EXCEED_CAP_'+k)
    paths = []; forbidden_inodes = set()
    for item in q['targets']:
        ref, m = item['archive'], item['member']; check_archive(ref)
        require(len(ref['stream_sha256']) == 64, 'SAVED_STREAM_SHA_REQUIRED')
        require(m['name'] == 'coronacases_001.nii.gz' and m['compression'] in (0, 8), 'FIXED_MEMBER_REQUIRED')
        require(0 <= m['header_offset'] < ref['bytes'] and 0 < m['compressed_bytes'] <= ref['bytes']
                and 0 < m['uncompressed_bytes'] <= 100*1024**2, 'MEMBER_BOUNDS')
        paths.append(Path(ref['path']).absolute())
        forbidden_inodes.add((ref['device'], ref['inode']))
    require(len(set(paths)) == 2, 'DISTINCT_ARCHIVES_REQUIRED')
    root = Path(q['output_root']).absolute(); no_symlinks(root)
    require(not root.exists(), 'OUTPUT_ALREADY_EXISTS')
    require(not any(root == p or root in p.parents for p in paths), 'OUTPUT_SOURCE_OVERLAP')
    if q.get('schema') is not None:
        require(q['schema'] == SCHEMA, 'NEW_SCHEMA_REQUIRED')
        require(q['limits'] == LIMITS and q['CPU_threads'] == 1, 'EXACT_REAL_BUDGET')
        require([x['archive']['stream_sha256'] for x in q['targets']] == [
            '0000000000000000000000000000000000000000000000000000000000000000',
            '0000000000000000000000000000000000000000000000000000000000000000'], 'FIXED_ACQUIRED_ARCHIVE_IDENTITIES')
        require(q['spec']['owner'] == 'DATA' and q['spec']['device'] == 'cpu' and
                q['spec']['max_forward'] == q['spec']['max_backward'] == 0 and
                q['spec']['timeout_seconds'] == LIMITS['seconds'] and
                q['spec']['telemetry_max_gap_seconds'] == .25, 'SUPERVISION_SPEC')
        require(sys.executable == q['runtime_executable'] and platform.python_version() == q['python_version'], 'RUNTIME_IDENTITY')
        # Executable may itself be a venv symlink; bind its resolved bytes explicitly.
        require(hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() == q['runtime_sha256'], 'RUNTIME_SHA')
        for key in ('source_bindings', 'stdlib_bindings', 'runtime_bindings', 'metadata_evidence'):
            require(bool(q[key]), 'EMPTY_BINDINGS_'+key)
            for ref in q[key]:
                require(Path(ref['path']).absolute() not in paths, 'ARCHIVE_HASH_FORBIDDEN')
                bound_file(ref, forbidden_inodes)
        decoder = json.loads(bound_file(q['decoder_binding'], forbidden_inodes))
        for ref in decoder['package_files']:
            bound_file(ref, forbidden_inodes)
        for package, version in q['package_versions'].items():
            require(importlib.metadata.version(package) == version, 'PACKAGE_VERSION_DRIFT_'+package)
        from . import r92_label_read_entry as entry
        entry.load_shared(q['supervisor'])  # Validate original modules, no queue dispatch.
    return dict(status='CHECK_ONLY_NO_ARCHIVE_OPEN_NO_VOXELS', archive_opens=0,
                medical_denominator=None, model_calls=0)


class Budget:
    def __init__(self, root, limits, guard, free_fn):
        self.root, self.limits, self.guard = root, limits, guard
        self.free_fn = free_fn or (lambda p: shutil.disk_usage(p).free)
        self.start = time.monotonic(); self.zip_reads = self.expanded = self.written = 0
        self.last_resource_check = -1.

    def check(self):
        require(time.monotonic()-self.start < self.limits['seconds'], 'TIME_LIMIT')
        # Source streaming and numeric loops still check time/ChildGuard every
        # chunk; avoid a filesystem statistics syscall for every image row.
        now = time.monotonic()
        if now-self.last_resource_check >= .05:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
            require(rss <= self.limits['RSS_bytes'], 'RSS_LIMIT')
            require(self.free_fn(self.root) >= self.limits['disk_reserve_bytes'] +
                    self.limits['temp_disk_bytes'] - self.written + self.limits['output_metadata_bytes'], 'DISK_RESERVE')
            self.last_resource_check = now
        if self.guard:
            self.guard.check()

    def write(self, stream, data):
        require(self.written+len(data) <= self.limits['temp_disk_bytes'], 'TEMP_DISK_LIMIT')
        stream.write(data); self.written += len(data)


class CountedFile:
    """zipfile remains the parser; all physical archive reads share one cap."""
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget

    def read(self, n=-1):
        self.budget.check()
        remaining = self.budget.limits['local_zip_read_bytes'] - self.budget.zip_reads
        if n < 0:
            position = self.stream.tell(); self.stream.seek(0, 2)
            n = self.stream.tell()-position; self.stream.seek(position)
        require(0 <= n <= min(remaining, 1048576), 'ZIP_READ_LIMIT_BEFORE_READ')
        data = self.stream.read(n); self.budget.zip_reads += len(data)
        return data

    def seek(self, *args): return self.stream.seek(*args)
    def tell(self): return self.stream.tell()
    def seekable(self): return True


def localization_handoff(q, result, receipt_sha):
    """LOC V2 field aliases; missing qualification remains a blocked handoff."""
    qa = result['qualification']; geometry = qa.get('geometry') or {}
    ct = qa.get('members', {}).get('CT', {}); k8 = qa.get('K8') or {}
    arrays = {x['kind']: x for x in result.get('fixed8', {}).get('arrays', [])}
    hashes = {k: v['shape_dtype_C_bytes_sha256'] for k, v in arrays.items()}
    evidence = q.get('evidence', {})
    complete = (qa.get('qualification', {}).get('extent', {}).get('effective_status') == 'VERIFIED' and
                evidence.get('extent') == 'COMPLETE_REFERENCE_VERIFIED')
    indices = [x['native_Z'] for x in k8.get('selections', [])]
    grid = dict(native_shape_zyx=ct.get('native_shape_ZYX'), indices=indices,
                native_geometry_sha256=geometry.get('shape_and_transform_sha256'))
    grid_sha = hashlib.sha256(json.dumps(grid, sort_keys=True, separators=(',', ':')).encode()).hexdigest() if indices else None
    def provenance(binding):
        return (str(binding['path'])+' SHA256 '+str(binding['sha256'])) if isinstance(binding, dict) and binding.get('path') and binding.get('sha256') else 'UNKNOWN'
    return dict(schema='R122_DATA_LOCALIZATION_HANDOFF_V2',
        qualification_status=result['medical_qualification'], qualification_receipt_sha256=receipt_sha,
        technical_status=result['technical_status'], license_disposition=result['license_disposition'],
        evidence_type=('EXTERNALLY_VERIFIED_REFERENCE' if result['status'] == 'PASS' else 'REAL_SOURCE_NOT_YET_QUALIFIED')
            if q.get('schema') else 'GENERATED_ONLY',
        case_id='coronacases_001', patient_group_id=evidence.get('patient_group_id'),
        patient_group_provenance=provenance(evidence.get('patient_binding')),
        patient_group_provenance_binding=evidence.get('patient_binding'),
        source_namespace=evidence.get('source_namespace', 'UNKNOWN'), source_version=evidence.get('source_version', 'UNKNOWN'),
        ct_archive_sha256=q['targets'][0]['archive']['stream_sha256'], gt_archive_sha256=q['targets'][1]['archive']['stream_sha256'],
        input_sha256=hashes.get('CT'), gt_sha256=hashes.get('INFECTION_GT'),
        input_hash_role='fixed8 original-order scaled CT float32 array, frozen LOC shape/dtype/C-byte encoding; HU may be unproven',
        gt_hash_role='fixed8 infection-only bool array with explicit source label mapping; not complete-reference proof',
        member_provenance=result['integrity'], native_shape_zyx=ct.get('native_shape_ZYX'),
        original_shape_XYZ=ct.get('shape_original_XYZ'), native_definition='ORIGINAL_NIFTI_XYZ_TRANSPOSED_ZYX_NO_FLIPS',
        native_geometry_sha256=geometry.get('shape_and_transform_sha256'), geometry_qa=geometry.get('status', 'NOT_RUN'),
        fixed8_native_indices=indices, selected_original_nifti_Z=indices,
        selected_canonical_Z=[x.get('corresponding_canonical_Z') for x in k8.get('selections', [])],
        eval_grid_sha256=grid_sha, transform_chain_sha256=geometry.get('shape_and_transform_sha256'),
        fixed8_gt_bool_sha256=hashes.get('INFECTION_GT'), fixed8_reference_domain_sha256=hashes.get('REFERENCE_DOMAIN'),
        fixed8_fov_sha256=hashes.get('FOV_SUPPORT'),
        reference_kind=('COMPLETE_INFECTION_MASK' if complete else 'PARTIAL_INFECTION_REFERENCE') if 'INFECTION_GT' in arrays else 'UNKNOWN',
        annotation_completeness='CONFIRMED_COMPLETE' if complete else 'KNOWN_POSITIVES_BACKGROUND_UNKNOWN',
        reference_extent=evidence.get('extent', 'UNKNOWN'), label_mapping_provenance=provenance(evidence.get('class_map_binding')),
        label_mapping_provenance_binding=evidence.get('class_map_binding'),
        labels_and_unknown_policy=qa.get('labels'), HU_evidence=qa.get('HU'),
        full_region_metrics_enabled=False, independent_test=False, medical_denominator=None)


def validate_zip_local_header(fields, info, record):
    """APPNOTE 6.3.10 section 4.4.4; only stored and Deflate are supported.

    Deflate bits 1/2 describe compression options, not extra payload formats.
    Unknown/encryption bits remain rejected. Diagnostics never contain names
    or the original header block.
    """
    signature = fields[zipfile._FH_SIGNATURE]
    method = fields[zipfile._FH_COMPRESSION_METHOD]
    flags = fields[zipfile._FH_GENERAL_PURPOSE_FLAG_BITS]
    allowed = {zipfile.ZIP_STORED: 0x808, zipfile.ZIP_DEFLATED: 0x80e}.get(method, 0)
    diagnostic = dict(role=record.get('role') if record.get('role') in ('CT', 'INFECTION_MASK') else 'UNSPECIFIED',
        signature_hex=signature.hex(), signature_u32=int.from_bytes(signature, 'little'),
        local_method=method, central_method=info.compress_type, local_flags=flags,
        central_flags=info.flag_bits, allowed_flags=allowed, rejected_flags=flags & ~allowed,
        failed_check=None)
    record['zip_local_header_diagnostic'] = diagnostic
    checks = ((signature == zipfile.stringFileHeader, 'ZIP_LOCAL_SIGNATURE'),
        (method == info.compress_type, 'ZIP_LOCAL_METHOD_MISMATCH'),
        (flags == info.flag_bits, 'ZIP_LOCAL_FLAGS_MISMATCH'),
        (method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'ZIP_METHOD_UNSUPPORTED'),
        (not flags & 0x2041, 'ZIP_ENCRYPTION_UNSUPPORTED'),
        (not flags & ~allowed, 'ZIP_FLAGS_UNSUPPORTED'))
    for ok, reason in checks:
        if not ok:
            diagnostic['failed_check'] = reason
            raise ValueError(reason)


def new_member_file(path, created):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd); created.append((path, s.st_dev, s.st_ino))
        return os.fdopen(fd, 'wb')
    except BaseException:
        os.close(fd); raise


def extract(item, root, budget, record):
    ref, expected = item['archive'], item['member']
    check_archive(ref)
    fd = os.open(ref['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    created = []; verified = False
    try:
        check_archive(ref, fd)
        with os.fdopen(fd, 'rb', closefd=False) as raw:
            source = CountedFile(raw, budget)
            with zipfile.ZipFile(source) as archive:
                require(len(archive.infolist()) <= 4096, 'ZIP_DIRECTORY_LIMIT')
                matches = [x for x in archive.infolist() if x.filename == expected['name']]
                require(len(matches) == 1, 'ZIP_MEMBER_UNIQUE')
                info = matches[0]
                actual = dict(name=info.filename, header_offset=info.header_offset,
                    compression=info.compress_type, compressed_bytes=info.compress_size,
                    uncompressed_bytes=info.file_size, declared_crc32=info.CRC)
                require(actual == expected, 'ZIP_HEADER_DIRECTORY_BINDING_MISMATCH')
                require(info.orig_filename == expected['name'], 'ZIP_MEMBER_PATH_OR_NAME')
                source.seek(info.header_offset)
                header = source.read(zipfile.sizeFileHeader)
                require(len(header) == zipfile.sizeFileHeader, 'ZIP_LOCAL_HEADER_TRUNCATED')
                fields = struct.unpack(zipfile.structFileHeader, header)
                validate_zip_local_header(fields, info, record)
                if not info.flag_bits & 8:
                    require((fields[zipfile._FH_CRC], fields[zipfile._FH_COMPRESSED_SIZE], fields[zipfile._FH_UNCOMPRESSED_SIZE]) ==
                            (info.CRC, info.compress_size, info.file_size), 'ZIP_LOCAL_HEADER_CRC_SIZE')
                data_offset = info.header_offset + zipfile.sizeFileHeader + fields[zipfile._FH_FILENAME_LENGTH] + fields[zipfile._FH_EXTRA_FIELD_LENGTH]
                gz_path = root/(item['role']+'.nii.gz'); nii_path = root/(item['role']+'.nii')
                gzip_sha, nii_sha = hashlib.sha256(), hashlib.sha256()
                inflater = zlib.decompressobj(16+zlib.MAX_WBITS)
                zipped = expanded = 0
                with archive.open(info) as member, new_member_file(gz_path, created) as gz, new_member_file(nii_path, created) as nii:
                    while True:
                        budget.check(); chunk = member.read(budget.limits['chunk_bytes'])
                        if not chunk: break
                        zipped += len(chunk); require(zipped <= info.file_size, 'ZIP_MEMBER_SIZE_LIMIT')
                        gzip_sha.update(chunk); budget.write(gz, chunk)
                        pending = chunk
                        while pending:
                            require(not inflater.eof, 'GZIP_EXTRA_STREAM_OR_TRAILING_BYTES')
                            maximum = min(budget.limits['chunk_bytes'],
                                budget.limits['inner_gzip_max_per_member_bytes']-expanded+1,
                                budget.limits['inner_gzip_max_pair_bytes']-budget.expanded+1)
                            require(maximum > 0, 'GZIP_EXPANDED_LIMIT')
                            try: data = inflater.decompress(pending, maximum)
                            except zlib.error as exc: raise ValueError('GZIP_CRC_ISIZE_OR_FORMAT: '+str(exc)) from exc
                            pending = inflater.unconsumed_tail
                            require(not inflater.unused_data, 'GZIP_EXTRA_STREAM_OR_TRAILING_BYTES')
                            expanded += len(data); budget.expanded += len(data)
                            require(expanded <= budget.limits['inner_gzip_max_per_member_bytes'] and
                                    budget.expanded <= budget.limits['inner_gzip_max_pair_bytes'], 'GZIP_EXPANDED_LIMIT')
                            nii_sha.update(data); budget.write(nii, data); budget.check()
                    require(zipped == info.file_size and member._left == 0 and member._compress_left == 0,
                            'ZIP_SIZE_OR_DEFLATE_TRUNCATED')
                    if info.compress_type == zipfile.ZIP_DEFLATED:
                        require(member._decompressor.eof and not member._decompressor.unused_data,
                                'ZIP_DEFLATE_EOF_OR_TRAILING_BYTES')
                    require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail, 'GZIP_EOF_UNPROVEN')
                    gz.flush(); nii.flush(); os.fsync(gz.fileno()); os.fsync(nii.fileno())
                if info.flag_bits & 8:
                    descriptor_start = data_offset+info.compress_size
                    require(descriptor_start+12 <= info._end_offset, 'ZIP_DESCRIPTOR_MISSING')
                    source.seek(descriptor_start)
                    first = source.read(4)
                    signed = first == b'PK\x07\x08'
                    require(descriptor_start+(16 if signed else 12) <= info._end_offset, 'ZIP_DESCRIPTOR_OVERLAP')
                    body = source.read(12) if signed else first+source.read(8)
                    require(len(body) == 12 and struct.unpack('<III', body) ==
                            (info.CRC, info.compress_size, info.file_size), 'ZIP_DESCRIPTOR_CRC_SIZE')
                record.update(status='INTEGRITY_PASS', member_bytes=zipped, expanded_bytes=expanded,
                    member_sha256=gzip_sha.hexdigest(), decoded_nii_sha256=nii_sha.hexdigest(),
                    member_crc32=info.CRC, zip_CRC_EOF_verified=True, gzip_CRC_EOF_verified=True,
                    gzip_path=str(gz_path), nii_path=str(nii_path))
        check_archive(ref, fd); check_archive(ref)
        verified = True
        return nii_path
    except zipfile.BadZipFile as exc:
        # zipfile errors can include untrusted local filenames. Save a fixed
        # code only; numerical field diagnostics above remain available.
        message = str(exc)
        reason = ('ZIP_CRC_MISMATCH' if 'CRC' in message else
                  'ZIP_LOCAL_NAME_MISMATCH' if 'name' in message.lower() else 'ZIP_CONTAINER_INVALID')
        raise ValueError(reason) from None
    finally:
        os.close(fd)
        if not verified:
            record['status'] = 'REJECT'; removed = retained = 0
            for path, device, inode in created:
                try:
                    s = path.lstat()
                    if stat.S_ISREG(s.st_mode) and (s.st_dev, s.st_ino) == (device, inode):
                        path.unlink(); removed += 1
                    else: retained += 1
                except FileNotFoundError: pass
                except OSError: retained += 1
            record['cleanup'] = dict(unverified_member_files_removed=removed,
                retained_due_to_identity_drift_or_error=retained, prior_outputs_touched=False)


def run(q, guard=None, free_fn=None):
    if q.get('schema') is not None:
        require(guard is not None, 'REAL_API_REQUIRES_ORIGINAL_CHILD_GUARD')
        from . import r92_label_read_entry as entry
        shared = entry.load_shared(q['supervisor'])
        require(isinstance(guard, shared.ChildGuard) and vars(guard.spec) == q['spec'], 'REAL_API_SHARED_GUARD_SPEC')
        guard.check()
    root = Path(q['output_root'])
    if root.exists() or root.is_symlink(): raise FileExistsError('OUTPUT_ALREADY_EXISTS')
    no_symlinks(root); root.mkdir(mode=0o700, parents=False, exist_ok=False)
    result = dict(schema='R122_FIRST_CASE_QUALIFICATION_RECEIPT_V1', status='REJECT',
        reasons=[], integrity=[], qualification={}, medical_denominator=None,
        model_calls=0, network_calls=0, retry=False, independent_test=False,
        technical_status='REJECT', medical_qualification='UNKNOWN',
        license_disposition=q.get('evidence', {}).get('license_status', 'UNKNOWN'))
    budget = Budget(root, q['limits'], guard, free_fn)
    try:
        # validate expects a nonexistent output, so only the internal run copy changes it.
        probe = dict(q, output_root=str(root/'CHECK_ONLY_UNUSED'))
        validate(probe); budget.check()
        paths = []
        for item in q['targets']:
            record = dict(role=item['role'], status='REJECT'); result['integrity'].append(record)
            paths.append(extract(item, root, budget, record))
        from .first_case_nifti_qa_v1 import analyze_pair, export_fixed8
        evidence = dict(q.get('evidence', {}), member_bindings={
            key: dict(path=str(path), sha256=record['decoded_nii_sha256'])
            for key, path, record in zip(('CT', 'Mask'), paths, result['integrity'])})
        qa = analyze_pair(*paths, evidence, q.get('preprocess', {}), q['limits'], budget.check)
        technical_rejected = any(row.get('severity') == 'REJECT' and
            row.get('domain') in ('CT', 'Mask', 'geometry', 'preprocess') for row in qa['reasons'])
        result.update(qualification=qa, status=qa['status'], reasons=qa['reasons'],
            technical_status='REJECT' if technical_rejected else 'PASS',
            medical_qualification=qa['status'])
        if qa['status'] != 'REJECT':
            # Reserve the entire bounded plane allowance before any export write.
            require(budget.written+q['limits']['max_export_bytes'] <= q['limits']['temp_disk_bytes'], 'EXPORT_TOTAL_DISK_CAP')
            reserved = q['limits']['max_export_bytes']; budget.written += reserved
            exported = export_fixed8(*paths, qa, evidence, root/'fixed8', q['limits'], budget.check)
            actual = sum(item['bytes'] for item in exported['arrays'])
            require(actual <= reserved, 'EXPORT_ACTUAL_DISK_CAP')
            budget.written -= reserved-actual
            result['fixed8'] = exported
        budget.check()
    except Exception as exc:
        result.update(status='REJECT', technical_status='REJECT', medical_qualification='UNKNOWN')
        for record in result['integrity']:
            if record['status'] == 'INTEGRITY_PASS':
                record['qualification_asset_state'] = 'RETAINED_INTEGRITY_ONLY_NOT_QUALIFIED'
        result['reasons'].append(dict(domain='container_or_runtime', code=type(exc).__name__, detail=str(exc)[:400]))
    finally:
        result['metrics'] = dict(local_zip_read_bytes=budget.zip_reads, inner_expanded_bytes=budget.expanded,
            temp_written_bytes=budget.written, elapsed_seconds=time.monotonic()-budget.start)
        data = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
        require(len(data) <= q['limits']['output_metadata_bytes'], 'METADATA_LIMIT')
        with (root/'RECEIPT.json').open('xb') as output:
            os.chmod(root/'RECEIPT.json', 0o600); output.write(data)
        handoff = localization_handoff(q, result, hashlib.sha256(data).hexdigest())
        handoff_bytes = (json.dumps(handoff, indent=2, allow_nan=False)+'\n').encode()
        require(len(data)+len(handoff_bytes) <= q['limits']['output_metadata_bytes'], 'TOTAL_METADATA_LIMIT')
        with (root/'LOCALIZATION_HANDOFF.json').open('xb') as output:
            os.chmod(root/'LOCALIZATION_HANDOFF.json', 0o600); output.write(handoff_bytes)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--request', required=True); p.add_argument('--sha256', required=True)
    p.add_argument('--execute', action='store_true'); p.add_argument('--child', action='store_true')
    p.add_argument('--approval'); p.add_argument('--approval-sha256'); p.add_argument('--dispatch'); p.add_argument('--dispatch-sha256')
    a = p.parse_args(); q = json.loads(bound_file(dict(path=a.request, sha256=a.sha256)))
    require(q.get('schema') == SCHEMA, 'REAL_REQUEST_SCHEMA_REQUIRED')
    guard = shared = None
    if a.execute and a.child:
        # Start the original heartbeat before decoder import/closure hashing.
        # No archive access is possible until the full approval check below.
        from . import r92_label_read_entry as entry
        shared = entry.load_shared(q['supervisor'])
        guard = shared.ChildGuard.from_environment()
    try:
        status = validate(q)
        if not a.execute:
            print(json.dumps(status)); return
        require(all((a.approval, a.approval_sha256, a.dispatch, a.dispatch_sha256)), 'NEW_EXACT_OWNER_APPROVAL_AND_DISPATCH_REQUIRED')
        owner = json.loads(bound_file(dict(path=a.approval, sha256=a.approval_sha256)))
        expected = dict(schema=APPROVAL, status='APPROVED_NEW_SCOPE', request_sha256=a.sha256,
            permit_exact_pair_member_read=True, permit_inner_gzip_and_voxels=True,
            permit_medical_qualification=True, permit_fixed8_native_exports=True, permit_models=False, retry=False)
        require(all(type(owner.get(k)) is type(v) and owner.get(k) == v for k, v in expected.items()), 'EXACT_APPROVAL_REQUIRED')
        from . import r92_label_read_entry as entry
        dispatch = json.loads(bound_file(dict(path=a.dispatch, sha256=a.dispatch_sha256)))
        entry.validate_dispatch(q, a.sha256, a.approval_sha256, dispatch)
        shared = shared or entry.load_shared(q['supervisor'])
        if not a.child:
            command = [sys.executable, '-m', 'epi_next.first_case_qualification_v1', '--request', a.request,
                '--sha256', a.sha256, '--execute', '--child', '--approval', a.approval,
                '--approval-sha256', a.approval_sha256, '--dispatch', a.dispatch,
                '--dispatch-sha256', a.dispatch_sha256]
            recovery = dispatch.get('administrative_recovery') or {}
            receipt = shared.run_supervised(shared.SupervisionSpec(**q['spec']), command, q['supervisor_output'],
                q['supervisor']['dependency_root'], q['supervisor']['dependency_sha256'],
                recovery_decision_path=recovery.get('path'), recovery_decision_sha=recovery.get('sha256'))
            require(receipt['status'] == 'SUCCESS' and receipt['slot_completed'], 'SUPERVISOR_FAILED_STOP')
            return
        require(guard is not None and vars(guard.spec) == q['spec'], 'CHILD_SPEC_DRIFT')
        receipt = run(q, guard)
        require(receipt['status'] != 'REJECT', 'QUALIFICATION_REJECTED_SEE_RECEIPT')
        guard.complete('SUCCESS', device_recovered=True, actual_forward=0, actual_backward=0)
    except BaseException:
        if guard is not None:
            guard.complete('FAILED', device_recovered=True, actual_forward=0, actual_backward=0)
        raise


if __name__ == '__main__': main()
