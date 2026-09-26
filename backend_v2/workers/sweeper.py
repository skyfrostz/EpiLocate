"""Cloud scheduler process. This is not inference Worker code."""
from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from backend_v2.db.base import make_engine
from backend_v2.services.jobs import queue_created, recover_expired
from backend_v2.services.retention import expire_inputs
from backend_v2.services.storage import ObjectStore


def sweep_once(engine, store) -> tuple[int, int, int]:
    with Session(engine) as db:
        with db.begin():
            created = queue_created(db)
            expired_leases = recover_expired(db)
            expired_inputs = expire_inputs(db, store)
        return created, expired_leases, expired_inputs


def main():
    logging.basicConfig(level=logging.INFO)
    engine = make_engine()
    store = ObjectStore()
    while True:
        try:
            counts = sweep_once(engine, store)
            if any(counts):
                logging.info("sweep created=%d expired_leases=%d expired_inputs=%d", *counts)
        except Exception:
            logging.exception("backend_v2 sweep failed")
        time.sleep(15)


if __name__ == "__main__":
    main()
