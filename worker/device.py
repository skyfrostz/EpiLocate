"""Choose an execution device without changing FrozenBaseline's model math."""
from __future__ import annotations

from dataclasses import dataclass

import torch


class DeviceUnavailable(RuntimeError):
    """The requested execution device cannot be used on this host."""


@dataclass(frozen=True)
class DeviceSelection:
    requested: str
    actual: str
    torch_device: torch.device
    gpu_name: str | None = None
    gpu_memory_mib: int | None = None

    @property
    def hardware(self) -> dict:
        value = {"accelerator": self.actual}
        if self.gpu_memory_mib is not None:
            value["gpu_memory_mib"] = self.gpu_memory_mib
        return value


def select_device(requested: str) -> DeviceSelection:
    mode = requested.upper()
    if mode not in {"CPU", "CUDA", "AUTO"}:
        raise ValueError("WORKER_DEVICE must be CPU, CUDA, or AUTO")
    if mode == "CPU":
        return DeviceSelection(mode, "CPU", torch.device("cpu"))
    try:
        available = torch.version.cuda is not None and torch.cuda.is_available() and torch.cuda.device_count() > 0
    except (AssertionError, RuntimeError, OSError):
        available = False
    if not available:
        if mode == "CUDA":
            raise DeviceUnavailable("CUDA requested but no usable NVIDIA GPU is available")
        return DeviceSelection(mode, "CPU", torch.device("cpu"))
    try:
        properties = torch.cuda.get_device_properties(0)
        device = torch.device("cuda:0")
        return DeviceSelection(mode, "CUDA", device, str(properties.name),
                               int(properties.total_memory // (1024 * 1024)))
    except (AssertionError, RuntimeError, OSError) as exc:
        if mode == "CUDA":
            raise DeviceUnavailable("CUDA requested but GPU initialization failed") from exc
        return DeviceSelection(mode, "CPU", torch.device("cpu"))
