"""Contrato del payload: CrimeReport."""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from arrest_model.schemas import CrimeReport


def test_parses_valid_payload(valid_payload: dict[str, Any]) -> None:
    report = CrimeReport.model_validate(valid_payload)
    assert (report.iucr, report.primary_type, report.location_description) == (
        "1310",
        "CRIMINAL DAMAGE",
        "APARTMENT",
    )
    assert report.date == datetime(2024, 12, 31, 23, 58)
    assert (report.latitude, report.longitude) == (41.771470188, -87.59074212)


@pytest.mark.parametrize("field", ["iucr", "primary_type", "date", "latitude", "longitude"])
def test_rejects_payload_without_required_field(valid_payload: dict[str, Any], field: str) -> None:
    del valid_payload[field]
    with pytest.raises(ValidationError):
        CrimeReport.model_validate(valid_payload)
