"""Mini-TP 1: API REST."""

from typing import Any

from fastapi.testclient import TestClient

from arrest_model.model import predict
from arrest_model.schemas import CrimeReport
from tp1_rest.app import create_app

FAKE_BUNDLE: dict[str, Any] = {"metadata": {"name": "chicago-arrest-xgboost", "version": 1}}


def _missing_model() -> dict[str, Any]:
    raise FileNotFoundError("No existe el modelo en model/model.pkl")


def test_health_reports_loaded_model() -> None:
    with TestClient(create_app(lambda: FAKE_BUNDLE)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_name": "chicago-arrest-xgboost",
        "model_version": 1,
    }


def test_health_returns_503_without_model() -> None:
    with TestClient(create_app(_missing_model)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "detail": "No existe el modelo en model/model.pkl",
    }


def test_predict_returns_prediction_and_model_version(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    with TestClient(create_app(lambda: bundle)) as client:
        response = client.post("/v1/predict", json=valid_payload)
    expected = predict(bundle, [CrimeReport.model_validate(valid_payload)])[0]
    assert response.status_code == 200
    assert response.json() == expected.model_dump()


def test_predict_rejects_payload_without_required_field(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    del valid_payload["date"]
    with TestClient(create_app(lambda: bundle)) as client:
        assert client.post("/v1/predict", json=valid_payload).status_code == 422


def test_predict_returns_503_without_model(valid_payload: dict[str, Any]) -> None:
    with TestClient(create_app(_missing_model)) as client:
        assert client.post("/v1/predict", json=valid_payload).status_code == 503
