from __future__ import annotations

from pathlib import Path

import pytest

from firebrief.ingest.manifest import Manifest, UnlistedDocument

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "corpus" / "sources.toml"


@pytest.fixture
def manifest() -> Manifest:
    return Manifest.from_toml(MANIFEST_PATH)


def test_the_reviewed_manifest_loads(manifest: Manifest) -> None:
    assert len(manifest) >= 2
    meta = manifest.get("fire-safety-purpose-built-flats")
    assert meta.licence == "OGL-3.0"
    assert meta.edition == "2019"
    assert meta.effective_from is not None


def test_an_unlisted_document_is_refused(manifest: Manifest) -> None:
    with pytest.raises(UnlistedDocument):
        manifest.get("some-document-nobody-reviewed")


def test_a_manifest_entry_missing_its_licence_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text('[documents."x"]\ntitle = "X"\nedition = "1"\n')

    with pytest.raises(ValueError, match="licence"):
        Manifest.from_toml(path)


def test_a_manifest_entry_with_a_refused_licence_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text('[documents."x"]\ntitle = "X"\nlicence = "Crown copyright"\nedition = "1"\n')

    with pytest.raises(ValueError, match="Crown copyright"):
        Manifest.from_toml(path)


def test_an_effective_date_that_is_not_a_date_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(
        '[documents."x"]\ntitle = "X"\nlicence = "OGL-3.0"\nedition = "1"\n'
        'effective_from = "last summer"\n'
    )

    with pytest.raises(ValueError, match="effective_from"):
        Manifest.from_toml(path)


def test_an_empty_manifest_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text("")

    with pytest.raises(ValueError):
        Manifest.from_toml(path)
