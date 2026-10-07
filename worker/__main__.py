"""Start one EpiLocate Worker node with `python -m worker`."""
from __future__ import annotations

import logging
import signal

from .agent import WorkerAgent
from .config import WorkerConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx INFO includes complete presigned MinIO URLs, including their short-lived signature.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    agent = WorkerAgent(WorkerConfig.from_env())
    logging.getLogger("epilocate.worker").info("Worker execution device: %s", agent.runner.hardware["accelerator"])
    signal.signal(signal.SIGINT, lambda *_: agent.stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: agent.stop_event.set())
    try:
        agent.run_forever()
    finally:
        agent.stop()


if __name__ == "__main__":
    main()
