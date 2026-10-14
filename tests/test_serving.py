"""El modelo servible: recibe los campos crudos y devuelve la probabilidad."""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from arrest_model.config import DEFAULT_THRESHOLD
from arrest_model.params import dump_params
from arrest_model.schemas import EXAMPLE_REPORT
from arrest_model.serving import RAW_INPUTS, ArrestModel


class FakeContext:
    """El contexto que MLflow le pasa al modelo: nada más que rutas a sus artefactos."""

    def __init__(self, artifacts: dict[str, str]) -> None:
        self.artifacts = artifacts


def servible_con_umbral(directorio: Path, bundle: dict[str, Any], umbral: float) -> ArrestModel:
    """El mismo modelo, con un umbral metido en sus parámetros, como lo deja el entrenamiento."""
    directorio.mkdir()
    modelo = directorio / "model.ubj"
    parametros = directorio / "params.json"
    bundle["model"].save_model(modelo)
    parametros.write_bytes(dump_params({**bundle["params"], "threshold": umbral}))

    servible = ArrestModel()
    servible.load_context(FakeContext({"model": str(modelo), "params": str(parametros)}))
    return servible


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

    salida = servible.predict(None, entrada)

    assert len(salida) == 2
    assert all(0.0 <= p <= 1.0 for p in salida["probability"])


def test_the_probability_matches_the_path_the_apis_use_today(
    servible: ArrestModel, reference_probability: float
) -> None:
    # La prueba que importa: el artefacto servible tiene que dar exactamente lo mismo que
    # `arrest_model.predict`, que es lo que los cuatro protocolos sirven hoy.
    salida = servible.predict(None, pd.DataFrame([EXAMPLE_REPORT]))

    assert salida["probability"][0] == pytest.approx(reference_probability)


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


def test_the_decision_uses_the_threshold_that_came_in_the_artifact(
    tmp_path: Path, bundle: dict[str, Any], reference_probability: float
) -> None:
    # Lo que cierra el desajuste: quien carga el artefacto decide igual que la API, sin tener
    # que preguntarle el umbral al registro. El de referencia da 0,068, así que con 0,05 de
    # corte el reporte es arresto y con 0,5 no.
    bajo = servible_con_umbral(tmp_path / "bajo", bundle, 0.05)
    alto = servible_con_umbral(tmp_path / "alto", bundle, 0.5)
    entrada = pd.DataFrame([EXAMPLE_REPORT])

    assert reference_probability < 0.5
    assert bajo.predict(None, entrada)["arrest"][0] == 1
    assert alto.predict(None, entrada)["arrest"][0] == 0


def test_without_a_threshold_in_the_artifact_it_decides_with_the_default(
    servible: ArrestModel, reference_probability: float
) -> None:
    # Las versiones registradas antes de esto no traen umbral en sus parámetros y siguen
    # decidiendo con el 0,5 de `XGBClassifier.predict`, igual que el .pkl del repo.
    salida = servible.predict(None, pd.DataFrame([EXAMPLE_REPORT]))

    assert salida["arrest"][0] == int(reference_probability > DEFAULT_THRESHOLD)
