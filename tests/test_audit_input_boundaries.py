"""Regressions for private validation bodies and disallowed image decoders."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from PIL import TiffImagePlugin
from pydantic import TypeAdapter
from pydantic import ValidationError

from editor.note_branding import normalize_watermark_upload
from editor.source_catalog.shared import safe_error_message


@pytest.mark.parametrize("private", ["value, input_type=str PRIVATE-CONTENT", "value]\nPRIVATE-CONTENT", "ordinary PRIVATE-CONTENT"])
def test_pydantic_input_cannot_forge_a_redaction_boundary(private):
    """Input containing error-like delimiters must never become visible in a UI error."""
    with pytest.raises(ValidationError) as error:
        TypeAdapter(int).validate_python(private)
    result = safe_error_message(error.value)
    assert "PRIVATE-CONTENT" not in result
    assert "valid integer" in result
    assert "input_value=<redacted>" in result


def test_disguised_tiff_is_rejected_without_running_its_decoder(monkeypatch):
    """A PNG filename cannot make the watermark entry point decode forbidden TIFF data."""
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="TIFF")
    calls = []
    def forbidden_decode(_self):
        calls.append("TIFF decoder")
        raise AssertionError("forbidden decoder was entered")
    monkeypatch.setattr(TiffImagePlugin.TiffImageFile, "load", forbidden_decode)
    with pytest.raises(ValueError):
        normalize_watermark_upload("logo.png", output.getvalue(), "image/png")
    assert calls == []
