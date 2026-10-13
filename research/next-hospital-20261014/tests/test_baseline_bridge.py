import numpy as np
import pytest
import torch

from epi_next.baseline_bridge import Preprocessed2DPredictor, load_verified_resnet18


def test_missing_checkpoint_fails_without_loading(tmp_path):
    with pytest.raises(FileNotFoundError, match="MODEL_UNAVAILABLE"):
        load_verified_resnet18(tmp_path / "missing.pth", "0" * 64)


def test_mismatched_hash_fails_before_pickle(tmp_path):
    file = tmp_path / "unsafe.pth"
    file.write_bytes(b"not a checkpoint")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_verified_resnet18(file, "0" * 64)


def test_input_rejected_before_forward():
    def fail(_):
        raise AssertionError("must not call")
    predict = Preprocessed2DPredictor(fail)
    for x in (np.zeros((3, 4)), np.full((224, 224), np.nan), np.full((224, 224), 2.)):
        with pytest.raises(ValueError):
            predict(x)
    assert predict.calls == 0


def test_counts_actual_calls_and_preserves_logits():
    class Model(torch.nn.Module):
        def forward(self, x):
            assert x.shape == (1, 3, 224, 224)
            return torch.tensor([[0., 100.]])
    predict = Preprocessed2DPredictor(Model())
    assert predict(np.zeros((224, 224))).tolist() == [0., 100.]
    assert predict.calls == 1
