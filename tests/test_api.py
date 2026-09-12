"""Mini-TP 1: API REST."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from arrest_model.schemas import EXAMPLE_REPORT
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


def test_predict_batch_returns_one_prediction_per_report_in_order(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    reports = [valid_payload, valid_payload | {"primary_type": "THEFT"}]
    with TestClient(create_app(lambda: bundle)) as client:
        response = client.post("/v1/predict/batch", json={"reports": reports})
    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert len(predictions) == 2
    # El primero es el payload de referencia; el segundo cambia de tipo y no puede dar lo mismo.
    assert predictions[0]["probability"] == pytest.approx(0.06843266636133194)
    assert predictions[1]["probability"] != predictions[0]["probability"]


@pytest.mark.parametrize(
    "reports",
    [[], [EXAMPLE_REPORT] * 1001, [EXAMPLE_REPORT, EXAMPLE_REPORT | {"primary_type": "BANANA"}]],
    ids=["lote vacío", "más de 1000", "un reporte inválido"],
)
def test_predict_batch_rejects_invalid_batches(
    bundle: dict[str, Any], reports: list[dict[str, Any]]
) -> None:
    with TestClient(create_app(lambda: bundle)) as client:
        assert client.post("/v1/predict/batch", json={"reports": reports}).status_code == 422


def test_predict_batch_returns_503_without_model(valid_payload: dict[str, Any]) -> None:
    with TestClient(create_app(_missing_model)) as client:
        response = client.post("/v1/predict/batch", json={"reports": [valid_payload]})
    assert response.status_code == 503
