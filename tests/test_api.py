"""Mini-TP 1: API REST."""

from typing import Any

from fastapi.testclient import TestClient

from tp1_rest.app import create_app

BUNDLE: dict[str, Any] = {"metadata": {"name": "chicago-arrest-xgboost", "version": 1}}


def test_health_reports_loaded_model() -> None:
    with TestClient(create_app(lambda: BUNDLE)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_name": "chicago-arrest-xgboost",
        "model_version": 1,
    }


def test_health_returns_503_without_model() -> None:
    def missing_model() -> dict[str, Any]:
        raise FileNotFoundError("No existe el modelo en model/model.pkl")

    with TestClient(create_app(missing_model)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "detail": "No existe el modelo en model/model.pkl",
    }
