"""Modelo empaquetado en model/model.pkl: carga y predicción."""

from pathlib import Path
from typing import Any

import pytest

from arrest_model.features import encode_payload
from arrest_model.model import load_bundle, predict
from arrest_model.schemas import CrimeReport


@pytest.fixture
def reports(valid_payload: dict[str, Any]) -> list[CrimeReport]:
    """Tres reportes que solo se diferencian en el tipo de delito."""
    types = ("CRIMINAL DAMAGE", "NARCOTICS", "WEAPONS VIOLATION")
    return [CrimeReport.model_validate(valid_payload | {"primary_type": t}) for t in types]


def test_load_bundle_reads_committed_model(bundle: dict[str, Any]) -> None:
    metadata = bundle["metadata"]
    assert (metadata["name"], metadata["version"]) == ("chicago-arrest-xgboost", 1)


def test_load_bundle_explains_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No existe el modelo"):
        load_bundle(tmp_path / "model.pkl")


def test_predict_follows_xgboost_rule(bundle: dict[str, Any], reports: list[CrimeReport]) -> None:
    expected = bundle["model"].predict(encode_payload(reports, bundle["params"])).tolist()
    assert [p.arrest for p in predict(bundle, reports)] == expected


def test_predictions_carry_probability_and_model_version(
    bundle: dict[str, Any], reports: list[CrimeReport]
) -> None:
    predictions = predict(bundle, reports)
    assert len(predictions) == len(reports)
    assert all(0.0 <= p.probability <= 1.0 for p in predictions)
    assert {(p.model_name, p.model_version) for p in predictions} == {("chicago-arrest-xgboost", 1)}
