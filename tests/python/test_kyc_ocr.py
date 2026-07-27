"""Tests for KYC-only recognition-language selection."""

import numpy as np
import pytest

from core.kyc_ocr import (
    KycOCRConfigError,
    configured_kyc_languages,
    run_kyc_ocr,
)
from core.ocr_engine import TextRegion


def _region(text: str, confidence: float = 0.9) -> TextRegion:
    return TextRegion(
        text=text,
        bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
        confidence=confidence,
    )


def test_no_configuration_preserves_existing_automatic_ocr(monkeypatch):
    calls = []
    monkeypatch.delenv("DOCUMENT_OCR_KYC_LANGS", raising=False)
    monkeypatch.setattr(
        "core.kyc_ocr.run_ocr",
        lambda image, **kwargs: calls.append(kwargs) or [_region("English")],
    )

    result = run_kyc_ocr(np.zeros((10, 10, 3), dtype=np.uint8))

    assert [region.text for region in result] == ["English"]
    assert calls == [{}]


def test_configured_models_keep_distinct_readings_for_same_detected_box(monkeypatch):
    calls = []

    def fake_ocr(image, **kwargs):
        language = kwargs["lang"]
        calls.append(language)
        if language == "en":
            return [_region("JOB CARD", 0.7)]
        return [_region("जॉब कार्ड", 0.95)]

    monkeypatch.setattr("core.kyc_ocr.run_ocr", fake_ocr)

    result = run_kyc_ocr(
        np.zeros((10, 10, 3), dtype=np.uint8),
        languages=("en", "devanagari"),
    )

    assert calls == ["en", "devanagari"]
    assert [region.text for region in result] == ["JOB CARD", "जॉब कार्ड"]


def test_duplicate_reading_keeps_higher_confidence(monkeypatch):
    monkeypatch.setattr(
        "core.kyc_ocr.run_ocr",
        lambda image, lang: [
            _region("NATIONAL POPULATION REGISTER", 0.7 if lang == "en" else 0.9)
        ],
    )

    result = run_kyc_ocr(
        np.zeros((10, 10, 3), dtype=np.uint8),
        languages=("en", "latin"),
    )

    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_configuration_deduplicates_supported_values():
    assert configured_kyc_languages(
        "en, devanagari,EN,ta"
    ) == ("en", "devanagari", "ta")


def test_environment_configuration_rejects_unknown_values():
    with pytest.raises(KycOCRConfigError, match="Unsupported"):
        configured_kyc_languages("en,devnagari")


def test_environment_configuration_rejects_more_than_four_models():
    with pytest.raises(KycOCRConfigError, match="At most 4"):
        configured_kyc_languages("en,latin,devanagari,ka,ta")


def test_explicit_unsupported_language_fails_fast():
    with pytest.raises(KycOCRConfigError, match="Unsupported KYC OCR languages"):
        run_kyc_ocr(
            np.zeros((10, 10, 3), dtype=np.uint8),
            languages=("bengali",),
        )
