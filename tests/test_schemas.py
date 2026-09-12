"""Contrato del payload: CrimeReport."""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from arrest_model.schemas import PRIMARY_TYPES, CrimeReport


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


def test_normalizes_case_and_spaces(valid_payload: dict[str, Any]) -> None:
    changes = {"iucr": " 041a ", "primary_type": "battery ", "location_description": " street"}
    report = CrimeReport.model_validate(valid_payload | changes)
    assert (report.iucr, report.primary_type, report.location_description) == (
        "041A",
        "BATTERY",
        "STREET",
    )


def test_accepts_valid_iucr_not_seen_in_training(valid_payload: dict[str, Any]) -> None:
    assert CrimeReport.model_validate(valid_payload | {"iucr": "999Z"}).iucr == "999Z"


def test_converts_date_with_timezone_to_chicago(valid_payload: dict[str, Any]) -> None:
    report = CrimeReport.model_validate(valid_payload | {"date": "2025-01-01T05:58:00Z"})
    assert report.date == datetime(2024, 12, 31, 23, 58)


@pytest.mark.parametrize(
    "change",
    [
        {"iucr": "48"},  # muy corto
        {"iucr": "13100"},  # muy largo
        {"iucr": "13A0"},  # la letra solo puede ir al final
        {"iucr": 1310},  # número en vez de texto
        {"primary_type": "BANANA"},  # no es uno de los 31 tipos
        {"latitude": 40.71},  # Nueva York
        {"longitude": -74.0},
        {"date": "ayer"},
        {"foo": 1},  # campo que no está en el contrato
    ],
)
def test_rejects_invalid_payload(valid_payload: dict[str, Any], change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CrimeReport.model_validate(valid_payload | change)


def test_primary_types_are_the_ones_seen_in_training(bundle: dict[str, Any]) -> None:
    assert len(PRIMARY_TYPES) == 31
    assert set(PRIMARY_TYPES) == set(bundle["params"]["freq"]["primary_type"])
