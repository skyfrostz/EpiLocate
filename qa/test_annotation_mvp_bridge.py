import pytest

from annotation_mvp_bridge import annotation_html


def test_annotation_entry_is_accessible_and_explicitly_synthetic():
    source = b"<html><body><main>frozen</main></body></html>"
    result = annotation_html(source)
    text = result.decode("utf-8")
    assert "医生标注" in text
    assert "合成工作区" in text
    assert "棋盘测试影像（非真实 CT）" in text
    assert "https://localhost:57171/annotations/" in text
    assert 'target="_blank"' in text
    assert "noopener noreferrer" in text
    assert "position: fixed" in text
    assert "@media (max-width: 720px)" in text
    assert ":focus-visible" in text


def test_annotation_entry_injection_is_idempotent_and_preserves_readonly_shell():
    source = b"<html><body>frozen</body></html>"
    once = annotation_html(source)
    twice = annotation_html(once)
    assert twice == once
    assert "frozen" in twice.decode("utf-8")


def test_annotation_entry_rejects_external_or_unencrypted_target():
    source = b"<html><body>frozen</body></html>"
    with pytest.raises(ValueError, match="ANNOTATION_URL_OUTSIDE_FIXED_LOCAL_WORKSPACE"):
        annotation_html(source, "https://example.test/annotations/")
    with pytest.raises(ValueError, match="ANNOTATION_URL_OUTSIDE_FIXED_LOCAL_WORKSPACE"):
        annotation_html(source, "http://localhost:57171/annotations/")
