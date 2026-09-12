"""Mini-TP 1: API REST."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tp1_rest.app import UNAVAILABLE_DETAIL, create_app
from tp1_rest.client import INVALID

HEALTH_ONLY_BUNDLE: dict[str, Any] = {"metadata": {"name": "chicago-arrest-xgboost", "version": 1}}


def _missing_model() -> dict[str, Any]:
    raise FileNotFoundError("No existe el modelo en /srv/app/model/model.pkl")


def test_health_reports_loaded_model() -> None:
    with TestClient(create_app(lambda: HEALTH_ONLY_BUNDLE)) as client:
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
    assert response.json() == {"status": "unavailable", "detail": UNAVAILABLE_DETAIL}


def test_errors_do_not_leak_server_paths(valid_payload: dict[str, Any]) -> None:
    with TestClient(create_app(_missing_model)) as client:
        health = client.get("/health").json()["detail"]
        prediction = client.post("/v1/predict", json=valid_payload).json()["detail"]
    assert "model.pkl" not in f"{health} {prediction}"
    assert "/srv" not in f"{health} {prediction}"


def test_predict_matches_the_reference_prediction(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    with TestClient(create_app(lambda: bundle)) as client:
        response = client.post("/v1/predict", json=valid_payload)
    assert response.status_code == 200
    # Valor de referencia documentado en el README: fija codificación, modelo y regla de decisión.
    assert response.json() == {
        "arrest": 0,
        "probability": pytest.approx(0.06843266636133194),
        "model_name": "chicago-arrest-xgboost",
        "model_version": 1,
    }


@pytest.mark.parametrize("payload", list(INVALID.values()), ids=list(INVALID))
def test_predict_rejects_payloads_that_break_the_contract(
    bundle: dict[str, Any], payload: dict[str, Any]
) -> None:
    with TestClient(create_app(lambda: bundle)) as client:
        assert client.post("/v1/predict", json=payload).status_code == 422


def test_predict_returns_503_without_model(valid_payload: dict[str, Any]) -> None:
    with TestClient(create_app(_missing_model)) as client:
        assert client.post("/v1/predict", json=valid_payload).status_code == 503
