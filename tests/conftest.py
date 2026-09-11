"""Fixtures compartidas de los tests."""

from typing import Any

import pytest


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """Primera fila de Crimes_Chicago_2024.csv con los 6 campos del contrato."""
    return {
        "iucr": "1310",
        "primary_type": "CRIMINAL DAMAGE",
        "location_description": "APARTMENT",
        "date": "2024-12-31T23:58:00",
        "latitude": 41.771470188,
        "longitude": -87.59074212,
    }
