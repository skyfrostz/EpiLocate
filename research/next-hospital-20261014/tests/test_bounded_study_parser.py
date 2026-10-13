import io
import json

import pytest

import epi_next.bounded_study_parser as parser


def record(**updates):
    value = {"id": "synthetic-object", "StudyInstanceUID": "synthetic-study",
             "labelId": "synthetic-label", "data": None, "createdById": "synthetic-reader"}
    value.update(updates)
    return json.dumps(value).encode()


def consume(raw, stream_type=io.BytesIO):
    return list(parser.iter_fields(stream_type(raw), {"synthetic-study"}, {"synthetic-label"}))


class SmallChunks(io.BytesIO):
    def read(self, size):
        assert size == parser.CHUNK
        return super().read(min(size, 3))


def test_cross_chunk_escapes_and_projection():
    raw = b'[' + record(note='escaped " \\ } [', updateHistory=[{"a": "excluded"}]) + b']'
    result = consume(raw, SmallChunks)
    assert result == [{"id": "synthetic-object", "StudyInstanceUID": "synthetic-study",
                       "labelId": "synthetic-label", "createdById": "synthetic-reader"}]


def test_outside_study_and_label_never_decode_body(monkeypatch):
    originals = parser.json.loads
    def guarded(raw):
        assert b"NOT_JSON" not in raw if isinstance(raw, bytes) else "NOT_JSON" not in raw
        return originals(raw)
    monkeypatch.setattr(parser.json, "loads", guarded)
    outside = record(StudyInstanceUID="outside").replace(b'"data": null', b'"data":{"bad":NOT_JSON}')
    other_label = record(labelId="outside").replace(b'"data": null', b'"data":[NOT_JSON]')
    assert len(consume(b'[' + outside + b',' + other_label + b',' + record() + b']')) == 1


def test_unknown_large_nested_object_is_not_retained():
    body = b'{"ignored":[' + b'0,' * 50000 + b'0],"StudyInstanceUID":"outside","labelId":"outside"}'
    scanner = parser.Scanner(io.BytesIO(body))
    assert parser.annotation_fields(scanner, {"synthetic-study"}, {"synthetic-label"}) is None
    assert scanner.peak_chunk <= parser.CHUNK
    assert scanner.peak_token < 100


def test_oversize_object_fails_before_full_read():
    raw = b'{"ignored":[' + b'0,' * parser.OBJECT + b'0],"StudyInstanceUID":"outside"}'
    stream = io.BytesIO(raw)
    with pytest.raises(ValueError, match="object scan bound"):
        parser.annotation_fields(parser.Scanner(stream), {"synthetic-study"}, {"synthetic-label"})
    assert stream.tell() <= parser.OBJECT + parser.CHUNK
    assert stream.tell() < len(raw)


def test_oversize_unknown_string_fails_early():
    raw = b'[{"ignored":"' + b'x' * 100000 + b'"}]'
    stream = io.BytesIO(raw)
    with pytest.raises(ValueError, match="string token bound"):
        list(parser.iter_fields(stream, {"synthetic-study"}, {"synthetic-label"}))
    assert stream.tell() <= parser.TOKEN + 2 * parser.CHUNK


@pytest.mark.parametrize("change", [{"data": {}}, {"data": "unexpected"}, {"createdById": []}])
def test_selected_invalid_content_rejected(change):
    with pytest.raises(ValueError, match="selected annotation"):
        consume(b'[' + record(**change) + b']')


def test_duplicate_and_nested_identity():
    duplicate = record()[:-1] + b',"StudyInstanceUID":"outside"}'
    with pytest.raises(ValueError, match="duplicate"):
        consume(b'[' + duplicate + b']')
    assert consume(b'[{"ignored":{"StudyInstanceUID":"synthetic-study","labelId":"synthetic-label"}}]') == []


def test_depth_and_truncation_rejected():
    with pytest.raises(ValueError, match="nesting bound"):
        consume(b'[{"ignored":' + b'[' * (parser.DEPTH + 1) + b'0' + b']' * (parser.DEPTH + 1) + b'}]')
    with pytest.raises(ValueError, match="truncated"):
        consume(b'[' + record()[:-2])


def test_scope_and_trailing_input_rejected():
    with pytest.raises(ValueError, match="scope"):
        list(parser.iter_fields(io.BytesIO(b'[]'), set(), {"synthetic-label"}))
    with pytest.raises(ValueError, match="trailing"):
        consume(b'[]extra')


def test_nested_oversize_scalar_and_stream_contract_rejected():
    with pytest.raises(ValueError, match="scalar token bound"):
        consume(b'[{"ignored":[' + b'1' * (parser.TOKEN + 1) + b']}]')
    class BrokenStream:
        def read(self, size):
            return b' ' * (size + 1)
    with pytest.raises(ValueError, match="chunk bound"):
        list(parser.iter_fields(BrokenStream(), {"synthetic-study"}, {"synthetic-label"}))
