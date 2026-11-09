from __future__ import annotations

import pytest

from firebrief.ingest.licence import LicenceNotAccepted, check_licence


@pytest.mark.parametrize("value", ["OGL-3.0", "ogl-2.0", "  OGL-3.0  "])
def test_open_government_licences_are_accepted_exactly(value: str) -> None:
    assert check_licence(value).startswith("ogl")


@pytest.mark.parametrize(
    "value", ["Crown copyright", "BS 9999", "", "proprietary", "ogl-3.0-extra", "OGL"]
)
def test_anything_else_is_refused_including_near_misses(value: str) -> None:
    with pytest.raises(LicenceNotAccepted):
        check_licence(value)
