from __future__ import annotations

import hashlib
import sys

from backend_v2.services.storage import ObjectStore


def main() -> int:
    store = ObjectStore()
    payload = b"epilocate-production-like-storage-check"
    key = store.put(payload, "application/octet-stream", "integration")
    try:
        read, media_type = store.read(key)
        signed = store.signed_key_get(key)
        if read != payload or media_type != "application/octet-stream" or "X-Amz-Signature" not in signed:
            print("storage validation failed", file=sys.stderr)
            return 1
        print(f"storage round-trip OK; sha256={hashlib.sha256(read).hexdigest()}; signed_url=true")
        return 0
    finally:
        store.delete(key)


if __name__ == "__main__":
    raise SystemExit(main())
