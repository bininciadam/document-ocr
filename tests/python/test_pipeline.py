"""Optional end-to-end tests against a private, ignored image dataset."""

import json
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent
DATASET_DIR = Path(
    os.getenv("DOCUMENT_OCR_BENCHMARK_DATA", REPO_ROOT / "benchmark-data")
)
MANIFEST_PATH = DATASET_DIR / "manifest.json"


def _cases() -> list[tuple[str, dict]]:
    if not MANIFEST_PATH.exists():
        return []
    manifest = json.loads(MANIFEST_PATH.read_text())
    return list(manifest.items())


@pytest.mark.parametrize(
    ("filename", "expected"),
    _cases(),
    ids=[name for name, _ in _cases()],
)
def test_private_dataset_case(filename, expected):
    from core.pipeline import scan

    image_path = DATASET_DIR / filename
    assert image_path.is_file(), f"Dataset image not found: {image_path}"

    result = scan(image_path)
    actual = result.to_dict()

    assert result.processing_ms > 0
    for key, value in expected.items():
        assert actual.get(key) == value


def test_private_dataset_accepts_bytes():
    cases = _cases()
    if not cases:
        pytest.skip("No private benchmark dataset configured")

    from core.pipeline import scan

    filename, expected = cases[0]
    result = scan((DATASET_DIR / filename).read_bytes())

    assert result.processing_ms > 0
    assert result.status == expected["status"]
