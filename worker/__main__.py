"""Start one EpiLocate Worker node with `python -m worker`."""
from __future__ import annotations

import logging
import signal

from .agent import WorkerAgent
from .config import WorkerConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    agent = WorkerAgent(WorkerConfig.from_env())
    signal.signal(signal.SIGINT, lambda *_: agent.stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: agent.stop_event.set())
    try:
        agent.run_forever()
    finally:
        agent.stop()


if __name__ == "__main__":
    main()
