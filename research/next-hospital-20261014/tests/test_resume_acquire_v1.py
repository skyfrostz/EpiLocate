"""Generated ZIP bytes and fake HTTP only; never real archives or networking."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from epi_next import resume_acquire_v1 as resume
from epi_next import r111_full_acquire as frozen


class Items:
    def __init__(self, pairs):
        self.pairs = pairs

    def items(self):
        return iter(self.pairs)


class Response:
    def __init__(self, body, url, pairs, status=206, before_read=None):
        self.stream = io.BytesIO(body)
        self.url = url
        self.headers = Items(pairs)
        self.status = status
        self.length = len(body)
        self.reads = 0
        self.before_read = before_read

    def geturl(self):
        return self.url

    def read(self, amount):
        self.reads += 1
        if self.before_read:
            self.before_read()
        chunk = self.stream.read(amount)
        self.length -= len(chunk)
        return chunk

    def close(self):
        self.stream.close()


def zip_bytes(marker):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('GENERATED_ONLY.nii', marker * 90)
    return stream.getvalue()


def inputs(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    bodies = [zip_bytes(b'GENERATED_CT'), zip_bytes(b'GENERATED_MASK')]
    prefix = tmp_path / 'original-prefix.part'
    prefix.write_bytes(bodies[0][:len(bodies[0]) // 2])
    held = prefix.stat()
    q = dict(
        output_root=str(tmp_path / 'new-output'),
        files=[dict(key=key, bytes=len(body), md5=hashlib.md5(body).hexdigest(),
                    seconds=60, url=frozen.source_url(key))
               for (key, *_), body in zip(frozen.FILES, bodies)],
        prefix=dict(path=str(prefix), bytes=held.st_size, device=held.st_dev,
                    inode=held.st_ino, mtime_ns=held.st_mtime_ns),
        network_body_bytes=len(bodies[0]) - held.st_size + len(bodies[1]),
    )
    return q, bodies


def pairs_for(q, index):
    size = q['files'][index]['bytes']
    offset = q['prefix']['bytes'] if index == 0 else 0
    pairs = [('Content-Length', str(size - offset)), ('Content-Encoding', 'identity')]
    if index == 0:
        pairs.append(('Content-Range', f'bytes {offset}-{size - 1}/{size}'))
    return pairs


def fake_transport(q, bodies, *, first_status=206, first_pairs=None,
                   first_body=None, before_read=None, etag=None):
    responses = []
    calls = []

    def transport(url, headers, timeout):
        index = len(calls)
        assert index < 2, 'Unexpected extra request or retry'
        assert url == q['files'][index]['url']
        expected = {'Accept-Encoding': 'identity'}
        if index == 0:
            expected['Range'] = f"bytes={q['prefix']['bytes']}-{q['files'][0]['bytes'] - 1}"
        assert headers == expected
        assert timeout > 0
        calls.append((url, dict(headers)))
        body = bodies[index][q['prefix']['bytes']:] if index == 0 else bodies[index]
        pairs = pairs_for(q, index)
        if index == 0 and first_pairs is not None:
            pairs = first_pairs
        if etag is not None:
            pairs = [*pairs, ('ETag', etag)]
        response = Response(first_body if index == 0 and first_body is not None else body,
                            url, pairs, first_status if index == 0 else 200,
                            before_read if index == 0 else None)
        responses.append(response)
        return response

    return transport, calls, responses


def receipt(q):
    return json.loads((Path(q['output_root']) / 'RECEIPT.json').read_text())


@pytest.mark.parametrize('etag', [None, 'W/"GENERATED_WEAK"'])
def test_resume_two_archives_without_strong_etag_and_without_member_reads(tmp_path, monkeypatch, etag):
    q, bodies = inputs(tmp_path)
    prefix = Path(q['prefix']['path'])
    original_bytes, original_stat = prefix.read_bytes(), prefix.stat()

    def forbidden(*args, **kwargs):
        raise AssertionError('ZIP member payload read is forbidden')

    for method in ('open', 'read', 'testzip', 'extract', 'extractall'):
        monkeypatch.setattr(zipfile.ZipFile, method, forbidden)
    transport, calls, responses = fake_transport(q, bodies, etag=etag)
    resume.acquire(q, transport, request_sha='GENERATED_REQUEST')
    result = receipt(q)
    assert result['status'] == 'FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY'
    assert result['network_body_bytes'] == q['network_body_bytes']
    assert result['prefix_read_bytes'] == len(original_bytes)
    assert result['actual_GETs'] == len(calls) == 2
    assert len(result['files']) == 2
    assert all(response.stream.closed for response in responses)
    assert prefix.read_bytes() == original_bytes
    after = prefix.stat()
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        original_stat.st_dev, original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns)
    for item, body in zip(q['files'], bodies):
        final = Path(q['output_root']) / item['key']
        assert final.read_bytes() == body
        assert hashlib.md5(final.read_bytes()).hexdigest() == item['md5']
        assert (Path(q['output_root']) / (item['key'] + '.directory.json')).exists()


@pytest.mark.parametrize('fault', ['status_200', 'wrong_start', 'wrong_end', 'wrong_total', 'wrong_length'])
def test_range_contract_rejects_before_body_and_stops_mask(tmp_path, fault):
    q, bodies = inputs(tmp_path)
    size, offset = q['files'][0]['bytes'], q['prefix']['bytes']
    value = {'wrong_start': f'bytes {offset + 1}-{size - 1}/{size}',
             'wrong_end': f'bytes {offset}-{size - 2}/{size}',
             'wrong_total': f'bytes {offset}-{size - 1}/{size + 1}'}
    pairs = pairs_for(q, 0)
    if fault in value:
        pairs = [(name, value[fault] if name == 'Content-Range' else content) for name, content in pairs]
    if fault == 'wrong_length':
        pairs = [(name, str(size - offset - 1) if name == 'Content-Length' else content)
                 for name, content in pairs]
    transport, calls, responses = fake_transport(q, bodies, first_status=200 if fault == 'status_200' else 206,
                                                first_pairs=pairs)
    with pytest.raises(ValueError):
        resume.acquire(q, transport)
    assert len(calls) == 1 and responses[0].reads == 0 and responses[0].stream.closed
    assert receipt(q)['status'] == 'FAILED_STOP_NO_RETRY'
    assert receipt(q)['network_body_bytes'] == 0


@pytest.mark.parametrize('fault', ['identity', 'size', 'symlink'])
def test_prefix_identity_size_and_symlink_are_rejected_without_http(tmp_path, fault):
    q, bodies = inputs(tmp_path)
    prefix = Path(q['prefix']['path'])
    if fault == 'identity':
        q['prefix']['inode'] += 1
    elif fault == 'size':
        q['prefix']['bytes'] += 1
    else:
        target = prefix.with_name('generated-original-kept.part')
        prefix.rename(target)
        prefix.symlink_to(target)
    transport, calls, _ = fake_transport(q, bodies)
    with pytest.raises((ValueError, OSError)):
        resume.acquire(q, transport)
    assert calls == []


def test_duplicate_critical_header_audit_is_sanitized_and_precedes_body(tmp_path):
    q, bodies = inputs(tmp_path)
    pairs = [*pairs_for(q, 0), ('ETag', 'SECRET_GENERATED_A'), ('etag', 'SECRET_GENERATED_B')]
    transport, calls, responses = fake_transport(q, bodies, first_pairs=pairs)
    with pytest.raises(ValueError):
        resume.acquire(q, transport)
    assert len(calls) == 1 and responses[0].reads == 0
    audits = sorted(Path(q['output_root']).glob('HTTP_HEADER_AUDIT_*.json'))
    assert len(audits) == 1
    audit = audits[0].read_text()
    assert 'SECRET_GENERATED' not in audit and 'etag' in audit.lower()


@pytest.mark.parametrize('fault', ['md5', 'truncated_tail'])
def test_tail_integrity_failure_never_publishes_or_starts_mask(tmp_path, fault):
    q, bodies = inputs(tmp_path)
    original = Path(q['prefix']['path']).read_bytes()
    if fault == 'md5':
        q['files'][0]['md5'] = '0' * 32
    tail = bodies[0][q['prefix']['bytes']:]
    transport, calls, _ = fake_transport(q, bodies, first_body=tail[:-1] if fault == 'truncated_tail' else tail)
    with pytest.raises(ValueError):
        resume.acquire(q, transport)
    assert len(calls) == 1 and receipt(q)['status'] == 'FAILED_STOP_NO_RETRY'
    assert not (Path(q['output_root']) / q['files'][0]['key']).exists()
    assert Path(q['prefix']['path']).read_bytes() == original


@pytest.mark.parametrize('allowed', [True, False])
def test_only_one_fixed_official_redirect_is_allowed(tmp_path, allowed):
    q, bodies = inputs(tmp_path)
    ct = q['files'][0]
    target = f"https://example.invalid/records/3757476/files/{ct['key']}?download=1" if allowed else 'https://invalid.example/SECRET'
    calls, responses = [], []

    def transport(url, headers, timeout):
        calls.append((url, dict(headers)))
        if len(calls) == 1:
            response = Response(b'', url, [('Location', target)], 302)
        elif len(calls) == 2:
            assert url == target and headers['Range'] == f"bytes={q['prefix']['bytes']}-{ct['bytes'] - 1}"
            response = Response(bodies[0][q['prefix']['bytes']:], url, pairs_for(q, 0))
        else:
            assert len(calls) == 3 and url == q['files'][1]['url']
            assert headers == {'Accept-Encoding': 'identity'}
            response = Response(bodies[1], url, pairs_for(q, 1), 200)
        responses.append(response)
        return response

    if allowed:
        resume.acquire(q, transport)
        assert receipt(q)['status'] == 'FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY'
        assert receipt(q)['actual_GETs'] == len(calls) == 3
    else:
        with pytest.raises(ValueError):
            resume.acquire(q, transport)
        assert len(calls) == 1
    assert responses[0].reads == 0 and all(response.stream.closed for response in responses)


def test_disk_network_budget_and_existing_output_fail_closed(tmp_path):
    q, bodies = inputs(tmp_path / 'disk')
    transport, calls, _ = fake_transport(q, bodies)
    with pytest.raises(ValueError):
        resume.acquire(q, transport, free_fn=lambda _: 0)
    assert calls == []

    q, bodies = inputs(tmp_path / 'budget')
    q['network_body_bytes'] = 0
    transport, calls, responses = fake_transport(q, bodies)
    with pytest.raises(ValueError):
        resume.acquire(q, transport)
    assert all(response.reads == 0 for response in responses)
    assert not (Path(q['output_root']) / q['files'][0]['key']).exists()

    q, bodies = inputs(tmp_path / 'existing')
    root = Path(q['output_root'])
    root.mkdir()
    keep = root / 'KEEP'
    keep.write_bytes(b'GENERATED_KEEP')
    transport, calls, _ = fake_transport(q, bodies)
    with pytest.raises((ValueError, FileExistsError)):
        resume.acquire(q, transport)
    assert calls == [] and keep.read_bytes() == b'GENERATED_KEEP'
    assert sorted(path.name for path in root.iterdir()) == ['KEEP']


def test_audit_is_persisted_before_body_raises_baseexception(tmp_path):
    q, bodies = inputs(tmp_path)

    class GeneratedAbort(BaseException):
        pass

    def abort():
        audits = list(Path(q['output_root']).glob('HTTP_HEADER_AUDIT_*.json'))
        assert len(audits) == 1
        assert 'SECRET_GENERATED' not in audits[0].read_text()
        raise GeneratedAbort('generated body interruption')

    pairs = [*pairs_for(q, 0), ('Set-Cookie', 'SECRET_GENERATED')]
    transport, calls, responses = fake_transport(q, bodies, first_pairs=pairs, before_read=abort)
    with pytest.raises(GeneratedAbort):
        resume.acquire(q, transport)
    assert len(calls) == 1 and responses[0].stream.closed
    assert receipt(q)['status'] == 'FAILED_STOP_NO_RETRY'
    assert receipt(q)['network_body_bytes'] == 0
