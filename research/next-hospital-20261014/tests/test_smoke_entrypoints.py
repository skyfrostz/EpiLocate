import importlib
import sys

import pytest


@pytest.mark.parametrize("module", ["encoder_smoke", "localization_smoke", "residual_localization", "baseline_comparison_smoke", "encoder_ctfm_cpu_smoke"])
def test_smoke_refuses_existing_artifact_before_execution(tmp_path, monkeypatch, module):
    destination = tmp_path / "prior.json"
    destination.write_text('{"previous": true}')
    arguments = [module, "--output", str(destination)]
    if module == "baseline_comparison_smoke":
        arguments += ["--checkpoint", str(tmp_path / "absent.pth"), "--checkpoint-sha", "a" * 64]
    if module == "encoder_ctfm_cpu_smoke":
        arguments += ["--weights", str(tmp_path / "absent.safetensors"), "--sha256", "a" * 64]
    monkeypatch.setattr(sys, "argv", arguments)
    loaded = importlib.import_module("epi_next." + module)
    with pytest.raises((FileExistsError, SystemExit)) as caught:
        loaded.main()
    if isinstance(caught.value, SystemExit):
        assert caught.value.code == 2
    assert destination.read_text() == '{"previous": true}'
