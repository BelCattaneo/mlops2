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


@pytest.fixture
def reference_probability() -> float:
    """Probabilidad que da el modelo para EXAMPLE_REPORT, la misma que documentan los README.

    Vive acá porque la usan los tests de REST y los de gRPC: los dos protocolos tienen que
    devolver exactamente el mismo número para el mismo reporte.
    """
    return 0.06843266636133194
