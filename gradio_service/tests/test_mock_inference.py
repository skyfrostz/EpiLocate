import io

from PIL import Image

from gradio_debug.contracts import CaseInput
from gradio_debug.inference import InferenceAdapter
from gradio_debug.storage import Storage


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "navy").save(buffer, format="PNG")
    return buffer.getvalue()


def test_mock_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    storage = Storage(tmp_path)
    relative, _ = storage.save_image_bytes(png_bytes(), "TEMP-1")
    target = storage.uploads / "CASE-1"
    target.mkdir()
    source = storage.root / relative
    final = target / source.name
    source.replace(final)
    source.parent.rmdir()
    case = CaseInput(case_id="CASE-1", input_kind="image", files=[final.relative_to(storage.root).as_posix()])
    adapter = InferenceAdapter(storage)
    first = adapter.run_case(case)
    second = adapter.run_case(case)
    assert first.prediction == second.prediction
    assert first.mode == "mock"
    assert first.occlusion.available is False
    assert "MOCK RESULT" in first.warnings[0]

