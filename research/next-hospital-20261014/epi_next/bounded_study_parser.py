"""Bounded binary annotation-array reader; no file, ZIP or authorization entrypoint.

Caller supplies an already positioned array stream and validated scope. This is
buffer bounding, not an OS-enforced RSS limit. Unknown bodies are scanned, never
retained or semantically decoded. Oversize content fails closed.
"""
import json

FIELDS = frozenset({"id", "StudyInstanceUID", "labelId", "createdById", "createdAt", "updatedAt", "groupId"})
IDENTITY = frozenset({"StudyInstanceUID", "labelId"})
CHUNK = 4096
TOKEN = 4096
OBJECT = 1024 * 1024
DEPTH = 64


class Scanner:
    def __init__(self, stream):
        self.stream = stream
        self.buffer = b""
        self.index = 0
        self.object_bytes = None
        self.peak_chunk = 0
        self.peak_token = 0

    def peek(self):
        if self.index == len(self.buffer):
            block = self.stream.read(CHUNK)
            if not isinstance(block, bytes) or len(block) > CHUNK:
                raise ValueError("binary stream must honor chunk bound")
            self.buffer, self.index = block, 0
            self.peak_chunk = max(self.peak_chunk, len(block))
        return self.buffer[self.index] if self.buffer else None

    def take(self):
        value = self.peek()
        if value is None:
            raise ValueError("truncated input")
        self.index += 1
        if self.object_bytes is not None:
            self.object_bytes += 1
            if self.object_bytes > OBJECT:
                raise ValueError("object scan bound exceeded")
        return value

    def space(self):
        while self.peek() in (32, 9, 10, 13):
            self.take()

    def expect(self, value):
        self.space()
        if self.take() != value:
            raise ValueError("unexpected delimiter")

    def value(self, capture=False):
        self.space()
        saved = bytearray() if capture else None
        stack = []
        quoted = escaped = False
        token_size = 0
        first = self.peek()
        if first is None or first in (44, 125, 93):
            raise ValueError("missing value")
        while True:
            char = self.peek()
            if char is None:
                raise ValueError("truncated value")
            if not quoted and not stack and char in (44, 125, 93, 32, 9, 10, 13):
                break
            char = self.take()
            if saved is not None:
                if len(saved) >= TOKEN:
                    raise ValueError("captured value bound exceeded")
                saved.append(char)
                self.peak_token = max(self.peak_token, len(saved))
            if quoted:
                token_size += 1
                if token_size > TOKEN:
                    raise ValueError("string token bound exceeded")
                if escaped:
                    escaped = False
                elif char == 92:
                    escaped = True
                elif char == 34:
                    quoted = False
                    token_size = 0
                    if not stack:
                        break
            elif char == 34:
                quoted = True
                token_size = 1
            elif char in (123, 91):
                token_size = 0
                stack.append(125 if char == 123 else 93)
                if len(stack) > DEPTH:
                    raise ValueError("nesting bound exceeded")
            elif char in (125, 93):
                token_size = 0
                if not stack or stack.pop() != char:
                    raise ValueError("unbalanced value")
                if not stack:
                    break
            elif char in (44, 58, 32, 9, 10, 13):
                token_size = 0
            else:
                token_size += 1
                if token_size > TOKEN:
                    raise ValueError("scalar token bound exceeded")
        return bytes(saved) if saved is not None else None


def scalar(raw):
    if raw is None or (raw != b"null" and not raw.startswith(b'"')):
        raise ValueError("requested scalar must be string or null")
    value = json.loads(raw)
    if value is not None and not isinstance(value, str):
        raise ValueError("requested scalar must be string or null")
    return value


def annotation_fields(scanner, studies, labels, quarantine_data=False):
    scanner.object_bytes = 0
    scanner.expect(123)
    captured = {}
    bad_scalars = set()
    data_seen = data_null = False
    scanner.space()
    if scanner.peek() != 125:
        while True:
            if scanner.peek() != 34:
                raise ValueError("object key must be string")
            key = json.loads(scanner.value(capture=True))
            scanner.expect(58)
            scanner.space()
            if key in FIELDS:
                if key in captured or key in bad_scalars:
                    raise ValueError("duplicate requested key")
                if scanner.peek() in (34, 110):
                    captured[key] = scanner.value(capture=True)
                else:
                    scanner.value()
                    bad_scalars.add(key)
            elif key == "data":
                if data_seen:
                    raise ValueError("duplicate data key")
                data_seen = True
                if scanner.peek() == 110:
                    data_null = scanner.value(capture=True) == b"null"
                else:
                    scanner.value()
            else:
                scanner.value()
            scanner.space()
            delimiter = scanner.take()
            if delimiter == 125:
                break
            if delimiter != 44:
                raise ValueError("unexpected object delimiter")
            scanner.space()
    else:
        scanner.take()
    scanner.object_bytes = None
    # Only identity scalars decoded until both allowlist dimensions match.
    if bad_scalars & IDENTITY:
        raise ValueError("invalid identity scalar")
    identity = {key: scalar(captured[key]) for key in IDENTITY if key in captured}
    if identity.get("StudyInstanceUID") not in studies or identity.get("labelId") not in labels:
        return None
    if bad_scalars:
        raise ValueError("selected annotation requires scalar fields and data:null")
    result = {key: scalar(value) for key, value in captured.items()}
    if not result.get("id"):
        raise ValueError("missing annotation ID")
    if not data_seen or not data_null:
        if not quarantine_data:
            raise ValueError("selected annotation requires scalar fields and data:null")
        result["_quarantine"] = "GLOBAL_DATA_NOT_EXPLICIT_NULL"
    return result


def iter_fields(stream, studies, labels):
    """Consume one standalone array; source/schema/receipt validation is external."""
    if not studies or not labels:
        raise ValueError("explicit nonempty scope required")
    scanner = Scanner(stream)
    scanner.expect(91)
    scanner.space()
    if scanner.peek() != 93:
        while True:
            record = annotation_fields(scanner, studies, labels)
            if record is not None:
                yield record
            scanner.space()
            delimiter = scanner.take()
            if delimiter == 93:
                break
            if delimiter != 44:
                raise ValueError("unexpected array delimiter")
            scanner.space()
    else:
        scanner.take()
    scanner.space()
    if scanner.peek() is not None:
        raise ValueError("trailing input")
