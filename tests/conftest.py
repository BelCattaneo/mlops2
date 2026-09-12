"""Fixtures compartidas de los tests."""

from typing import Any

import pytest

from arrest_model.model import load_bundle
from arrest_model.schemas import EXAMPLE_REPORT


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """Copia del ejemplo del contrato, para que cada test pueda modificarla sin afectar al resto."""
    return dict(EXAMPLE_REPORT)


@pytest.fixture(scope="session")
def bundle() -> dict[str, Any]:
    """El modelo empaquetado en model/model.pkl."""
    return load_bundle()
