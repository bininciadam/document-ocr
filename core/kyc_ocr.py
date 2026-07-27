"""KYC-only OCR language selection and result merging.

Passport OCR continues to use the existing ``run_ocr`` behavior. Operators
with a known non-passport document population can opt into additional
recognition models with ``DOCUMENT_OCR_KYC_LANGS``:

    DOCUMENT_OCR_KYC_LANGS=en,devanagari

Running several recognizers increases latency and memory, so the default is the
existing automatic OCR pass. This module does not guess a script from an
English model's failed output; accuracy by language must be measured with the
private KYC benchmark.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import numpy as np

from .ocr_engine import TextRegion, run_ocr

KYC_LANGS_ENV = "DOCUMENT_OCR_KYC_LANGS"
SUPPORTED_KYC_LANGS = frozenset(
    {
        "en",
        "latin",
        "devanagari",
        "ka",
        "ta",
        "te",
    }
)
MAX_CONFIGURED_LANGUAGES = 4


class KycOCRConfigError(ValueError):
    """Raised when KYC recognition-model configuration is invalid."""


def configured_kyc_languages(raw: str | None = None) -> tuple[str, ...]:
    """Parse and validate the optional KYC recognition-model list."""
    configured = os.getenv(KYC_LANGS_ENV) if raw is None else raw
    if not configured or not configured.strip():
        return ()

    requested = [
        token.strip().lower()
        for token in configured.split(",")
        if token.strip()
    ]
    invalid = sorted(set(requested) - SUPPORTED_KYC_LANGS)
    if invalid:
        raise KycOCRConfigError(
            f"Unsupported KYC OCR languages: {invalid}"
        )

    languages = list(dict.fromkeys(requested))
    if len(languages) > MAX_CONFIGURED_LANGUAGES:
        raise KycOCRConfigError(
            f"At most {MAX_CONFIGURED_LANGUAGES} KYC OCR languages may be used"
        )
    return tuple(languages)


def run_kyc_ocr(
    image: np.ndarray,
    *,
    languages: Iterable[str] | None = None,
) -> list[TextRegion]:
    """Run the default or explicitly configured OCR passes for KYC documents."""
    selected = (
        tuple(
            dict.fromkeys(
                str(language).strip().lower()
                for language in languages
                if str(language).strip()
            )
        )
        if languages is not None
        else configured_kyc_languages()
    )
    if not selected:
        return run_ocr(image)

    invalid = [
        language
        for language in selected
        if language not in SUPPORTED_KYC_LANGS
    ]
    if invalid:
        raise KycOCRConfigError(
            f"Unsupported KYC OCR languages: {sorted(set(invalid))}"
        )
    if len(selected) > MAX_CONFIGURED_LANGUAGES:
        raise KycOCRConfigError(
            f"At most {MAX_CONFIGURED_LANGUAGES} KYC OCR languages may be used"
        )

    regions: list[TextRegion] = []
    for language in selected:
        regions.extend(run_ocr(image, lang=language))
    return _deduplicate_regions(regions)


def _deduplicate_regions(regions: list[TextRegion]) -> list[TextRegion]:
    """Deduplicate repeated readings without discarding another script's text.

    Confidence values produced by different recognition models are not
    calibrated against one another.  Keep distinct text alternatives for the
    same box, while retaining only the highest-confidence copy of an identical
    normalized reading.
    """
    deduplicated: dict[
        tuple[tuple[tuple[int, int], ...], str],
        TextRegion,
    ] = {}
    order: list[tuple[tuple[tuple[int, int], ...], str]] = []

    for region in regions:
        geometry = tuple(tuple(point) for point in region.bbox)
        normalized_text = " ".join(region.text.split()).casefold()
        key = (geometry, normalized_text)
        previous = deduplicated.get(key)
        if previous is None:
            order.append(key)
            deduplicated[key] = region
        elif region.confidence > previous.confidence:
            deduplicated[key] = region

    return [deduplicated[key] for key in order]
