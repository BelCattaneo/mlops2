"""El modelo servible: recibe los campos crudos y devuelve la probabilidad."""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from arrest_model.params import dump_params
from arrest_model.schemas import EXAMPLE_REPORT
from arrest_model.serving import RAW_INPUTS, ArrestModel


class FakeContext:
    """El contexto que MLflow le pasa al modelo: nada más que rutas a sus artefactos."""

    def __init__(self, artifacts: dict[str, str]) -> None:
        self.artifacts = artifacts


@pytest.fixture
def servible(tmp_path: Path, bundle: dict[str, Any]) -> ArrestModel:
    """El modelo del bundle entregado, empaquetado como servible con sus parámetros."""
    modelo = tmp_path / "model.ubj"
    parametros = tmp_path / "params.json"
    bundle["model"].save_model(modelo)
    parametros.write_bytes(dump_params(bundle["params"]))

    servible = ArrestModel()
    servible.load_context(FakeContext({"model": str(modelo), "params": str(parametros)}))
    return servible


def test_the_raw_inputs_are_the_six_fields_of_the_contract() -> None:
    assert sorted(RAW_INPUTS) == sorted(EXAMPLE_REPORT)


def test_predicting_gives_one_probability_per_row(servible: ArrestModel) -> None:
    entrada = pd.DataFrame([EXAMPLE_REPORT, EXAMPLE_REPORT])

    probabilidades = servible.predict(None, entrada)

    assert len(probabilidades) == 2
    assert all(0.0 <= p <= 1.0 for p in probabilidades)


def test_the_probability_matches_the_path_the_apis_use_today(
    servible: ArrestModel, reference_probability: float
) -> None:
    # La prueba que importa: el artefacto servible tiene que dar exactamente lo mismo que
    # `arrest_model.predict`, que es lo que los cuatro protocolos sirven hoy.
    probabilidades = servible.predict(None, pd.DataFrame([EXAMPLE_REPORT]))

    assert probabilidades[0] == pytest.approx(reference_probability)


def test_an_invalid_payload_fails_inside_the_model(servible: ArrestModel) -> None:
    # El modelo valida con el mismo contrato que las APIs, así que sirve solo: expuesto con
    # `mlflow models serve`, una latitud fuera de Chicago no pasa.
    fuera_de_chicago = {**EXAMPLE_REPORT, "latitude": 0.0}

    with pytest.raises(ValueError):
        servible.predict(None, pd.DataFrame([fuera_de_chicago]))


def test_the_model_needs_both_artifacts(tmp_path: Path, bundle: dict[str, Any]) -> None:
    modelo = tmp_path / "model.ubj"
    bundle["model"].save_model(modelo)
    servible = ArrestModel()

    with pytest.raises(KeyError):
        servible.load_context(FakeContext({"model": str(modelo)}))
