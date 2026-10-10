"""Modelo empaquetado en model/model.pkl: carga y predicción."""

from pathlib import Path
from typing import Any

import pytest

from arrest_model.config import MODEL_NAME
from arrest_model.features import encode_payload
from arrest_model.model import load_bundle, predict
from arrest_model.schemas import EXAMPLE_REPORT, CrimeReport


@pytest.fixture
def reports(valid_payload: dict[str, Any]) -> list[CrimeReport]:
    """Tres reportes que solo se diferencian en el tipo de delito."""
    types = ("CRIMINAL DAMAGE", "NARCOTICS", "WEAPONS VIOLATION")
    return [CrimeReport.model_validate(valid_payload | {"primary_type": t}) for t in types]


def test_load_bundle_reads_committed_model(bundle: dict[str, Any]) -> None:
    # Ata la constante al .pkl: si se regenera el modelo con otro nombre, esto avisa.
    metadata = bundle["metadata"]
    assert (metadata["name"], metadata["version"]) == (MODEL_NAME, 1)


def test_load_bundle_explains_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No existe el modelo"):
        load_bundle(tmp_path / "model.pkl")


def test_predict_follows_xgboost_rule(bundle: dict[str, Any], reports: list[CrimeReport]) -> None:
    expected = bundle["model"].predict(encode_payload(reports, bundle["params"])).tolist()
    assert [p.arrest for p in predict(bundle, reports)] == expected


def test_predict_with_no_reports_returns_empty_list(bundle: dict[str, Any]) -> None:
    assert predict(bundle, []) == []


def test_predictions_carry_probability_and_model_version(
    bundle: dict[str, Any], reports: list[CrimeReport]
) -> None:
    predictions = predict(bundle, reports)
    assert len(predictions) == len(reports)
    assert all(0.0 <= p.probability <= 1.0 for p in predictions)
    assert {(p.model_name, p.model_version) for p in predictions} == {(MODEL_NAME, 1)}


def test_the_decision_threshold_defaults_to_half(bundle: dict[str, Any]) -> None:
    # El modelo entregado no trae umbral y tiene que seguir decidiendo en 0,5: es la regla que
    # documentan los cuatro protocolos y la que fija la probabilidad de referencia.
    assert "threshold" not in bundle

    prediccion = predict(bundle, [CrimeReport(**EXAMPLE_REPORT)])[0]

    assert prediccion.arrest == int(prediccion.probability > 0.5)


def test_a_bundle_can_carry_its_own_threshold(bundle: dict[str, Any]) -> None:
    # El umbral es un parámetro del modelo como cualquier otro: el que entrena lo elige y viaja
    # con él. Medido sobre la ventana entera, el mejor corte del modelo actual es 0,58 y no 0,5,
    # así que el 0,5 fijo le dejaba MCC sin usar.
    con_umbral = {**bundle, "threshold": 0.01}

    prediccion = predict(con_umbral, [CrimeReport(**EXAMPLE_REPORT)])[0]

    # La probabilidad del reporte de ejemplo es 0,068: por encima de 0,01 y por debajo de 0,5.
    assert prediccion.probability > 0.01
    assert prediccion.arrest == 1
