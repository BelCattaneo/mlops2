"""De dónde sale el modelo que sirven las APIs: el .pkl del repo o el champion del registro."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from mlflow.exceptions import MlflowException

from arrest_model.config import MODEL_NAME
from arrest_model.model import load_bundle, predict
from arrest_model.params import dump_params
from arrest_model.registry import (
    ModelProvider,
    ModelSource,
    bundle_from_artifacts,
    load_model_bundle,
    model_provider,
    registered_version,
    resolve_loader,
)
from arrest_model.schemas import CrimeReport, ModelMetadata
from tp6_datalake.lake import ACCESS_KEY, ENDPOINT, SECRET_KEY
from tp6_datalake.tracking import TRACKING_URI, tracking_available


def test_without_model_uri_the_loader_is_the_committed_pkl() -> None:
    # Los mini-TPs corren sin la variable y tienen que seguir sirviendo el .pkl versionado.
    assert resolve_loader({}) is load_bundle


def test_the_bundle_from_the_registry_predicts_the_same_as_the_pkl(
    tmp_path: Path,
    bundle: dict[str, Any],
    valid_payload: dict[str, Any],
    reference_probability: float,
) -> None:
    # La prueba que importa: el champion del registro tiene que dar el mismo número que el .pkl
    # que sirven los mini-TPs hoy. Si no, las dos mitades de la plataforma predicen distinto.
    artefactos = tmp_path / "artifacts"  # en un subdirectorio: el layout del pyfunc no importa
    artefactos.mkdir()
    bundle["model"].save_model(artefactos / "model.ubj")
    (artefactos / "params.json").write_bytes(dump_params(bundle["params"]))

    desde_el_registro = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=7,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    prediccion = predict(desde_el_registro, [CrimeReport(**valid_payload)])[0]

    assert prediccion.probability == pytest.approx(reference_probability)


def test_the_metadata_satisfies_the_contract_the_apis_publish(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # `GET /v1/metadata` valida contra `ModelMetadata` y la query de GraphQL arma su tipo con lo
    # mismo: si al bundle del registro le falta un campo, el servicio falla recién en la request.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params(bundle["params"]))

    desde_el_registro = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=7,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    metadata = ModelMetadata.model_validate(desde_el_registro["metadata"])

    assert metadata.version == 7
    # Las entradas y las features son del modelo, no de la procedencia: tienen que ser las mismas
    # que las del .pkl o los dos caminos de la plataforma estarían sirviendo modelos distintos.
    assert metadata.inputs == bundle["metadata"]["inputs"]
    assert metadata.features == bundle["metadata"]["features"]


def test_with_model_uri_the_loader_brings_the_champion_from_the_registry(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # Dentro de la plataforma el modelo sale del registro, y la uri que el loader recibe tiene
    # que llegar entera: es la que decide qué versión se sirve.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params(bundle["params"]))
    pedidas: list[str] = []

    def fetch(uri: str) -> ModelSource:
        pedidas.append(uri)
        return ModelSource(
            directory=tmp_path,
            name="chicago-arrest-xgboost",
            version=7,
            metrics={"mcc": 0.58},
            trained_at=datetime(2026, 10, 10, tzinfo=UTC),
        )

    loader = resolve_loader({"MODEL_URI": "models:/chicago-arrest-xgboost@champion"}, fetch=fetch)
    desde_el_registro = loader()

    assert pedidas == ["models:/chicago-arrest-xgboost@champion"]
    assert desde_el_registro["metadata"]["version"] == 7


def test_an_empty_model_uri_falls_back_to_the_pkl() -> None:
    # `MODEL_URI=` en un .env es una variable presente y vacía: no es una uri.
    assert resolve_loader({"MODEL_URI": "  "}) is load_bundle


class FakeClient:
    """Registro de mentira: anota qué le preguntaron."""

    def __init__(self) -> None:
        self.asked: tuple[str, ...] = ()

    def get_model_version_by_alias(self, name: str, alias: str) -> str:
        self.asked = ("alias", name, alias)
        return "por alias"

    def get_model_version(self, name: str, version: str) -> str:
        self.asked = ("version", name, version)
        return "por version"


def test_an_alias_uri_asks_the_registry_who_the_champion_is() -> None:
    # Pedir el alias y no un número es lo que hace que promover sea una operación de registro:
    # el servicio pregunta en cada arranque quién es el champion.
    client = FakeClient()

    registered_version(client, "models:/chicago-arrest-xgboost@champion")

    assert client.asked == ("alias", "chicago-arrest-xgboost", "champion")


def test_a_pinned_uri_asks_for_that_exact_version() -> None:
    client = FakeClient()

    registered_version(client, "models:/chicago-arrest-xgboost/3")

    assert client.asked == ("version", "chicago-arrest-xgboost", "3")


def test_a_uri_that_is_not_from_the_registry_says_so() -> None:
    # Un path o una uri de corrida en MODEL_URI es un error de configuración y tiene que fallar
    # al arrancar, no servir un modelo que nadie promovió.
    with pytest.raises(ValueError, match="MODEL_URI"):
        registered_version(FakeClient(), "/opt/project/model/model.pkl")


@pytest.mark.mlflow
@pytest.mark.skipif(not tracking_available(), reason="no hay servidor de MLflow en 5001")
def test_the_champion_of_the_running_stack_loads_and_predicts(
    monkeypatch: pytest.MonkeyPatch, valid_payload: dict[str, Any]
) -> None:
    """De punta a punta contra la plataforma levantada: el champion que registró el DAG se baja,
    se arma y predice. Deja documentado, además, qué necesita el entorno de un servicio para
    poder cargarlo: la uri del tracking y las credenciales del almacenamiento de artefactos.
    """
    monkeypatch.setenv("MLFLOW_TRACKING_URI", TRACKING_URI)
    monkeypatch.setenv("MLFLOW_S3_ENDPOINT_URL", ENDPOINT)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET_KEY)
    loader = resolve_loader({"MODEL_URI": f"models:/{MODEL_NAME}@champion"})

    try:
        champion = loader()
    except MlflowException as error:
        pytest.skip(f"la plataforma no tiene un champion registrado: {error}")

    metadata = ModelMetadata.model_validate(champion["metadata"])
    prediccion = predict(champion, [CrimeReport(**valid_payload)])[0]

    assert metadata.name == MODEL_NAME
    assert metadata.version >= 1
    assert 0.0 <= prediccion.probability <= 1.0
    # La versión que informa cada predicción es la del registro, no la del .pkl horneado.
    assert prediccion.model_version == metadata.version


def test_the_entry_point_the_services_call_defaults_to_the_pkl(
    monkeypatch: pytest.MonkeyPatch, bundle: dict[str, Any]
) -> None:
    # Es la función que los tres servicios llaman al arrancar. Sin `MODEL_URI` en el entorno
    # tiene que dar el mismo modelo que hoy, que es lo que corre cuando el mini-TP va suelto.
    monkeypatch.delenv("MODEL_URI", raising=False)

    cargado = load_model_bundle()

    assert cargado["metadata"] == bundle["metadata"]


def test_the_training_date_travels_as_text_like_in_the_pkl(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # El esquema de GraphQL hace `datetime.fromisoformat(metadata["trained_at"])`
    # (`tp2_graphql/schema.py:98`), así que el campo tiene que ser texto y no un datetime: con un
    # datetime el servicio levanta igual y falla recién en la query.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params(bundle["params"]))

    desde_el_registro = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=7,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    trained_at = desde_el_registro["metadata"]["trained_at"]

    assert isinstance(trained_at, str)
    assert isinstance(bundle["metadata"]["trained_at"], str)  # la misma forma que el .pkl
    assert datetime.fromisoformat(trained_at) == datetime(2026, 10, 10, tzinfo=UTC)


def test_the_threshold_travels_with_the_model_when_the_run_recorded_one(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # El umbral lo elige el entrenamiento sobre un conjunto de validación, así que es parte del
    # modelo registrado y tiene que llegar al servicio junto con los parámetros.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params(bundle["params"]))

    con_umbral = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=9,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 10, tzinfo=UTC),
        threshold=0.58,
    )

    assert con_umbral["metadata"]["threshold"] == 0.58


def test_without_a_recorded_threshold_the_bundle_does_not_carry_one(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # Una versión registrada antes de que el entrenamiento eligiera umbral tiene que seguir
    # decidiendo en 0,5, que es lo que hace `predict` cuando el bundle no trae ninguno.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params(bundle["params"]))

    sin_umbral = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=4,
        metrics={"mcc": 0.56},
        trained_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    assert "threshold" not in sin_umbral["metadata"]


class RelojFalso:
    """Un reloj que avanza cuando se le dice."""

    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora


def test_the_provider_loads_once_and_reuses_it() -> None:
    # El bundle no se vuelve a bajar en cada predicción: a 5 ms de mediana, bajar 800 KB por
    # request sería multiplicar la latencia por cien.
    cargas = []

    def cargar() -> dict[str, Any]:
        cargas.append(1)
        return {"metadata": {"version": 1}}

    proveedor = ModelProvider(loader=cargar, clock=RelojFalso())

    assert proveedor.current() is proveedor.current()
    assert len(cargas) == 1


def test_the_provider_reloads_when_the_registry_has_another_version() -> None:
    # Promover una versión no tiene que exigir reiniciar el servicio.
    reloj = RelojFalso()
    version = [1]
    proveedor = ModelProvider(
        loader=lambda: {"metadata": {"version": version[0]}},
        version_of=lambda: version[0],
        ttl=300,
        clock=reloj,
    )
    assert proveedor.current()["metadata"]["version"] == 1

    version[0] = 2
    reloj.ahora += 301

    assert proveedor.current()["metadata"]["version"] == 2


def test_the_provider_does_not_ask_the_registry_before_the_ttl() -> None:
    reloj = RelojFalso()
    consultas = []
    proveedor = ModelProvider(
        loader=lambda: {"metadata": {"version": 1}},
        version_of=lambda: consultas.append(1) or 1,
        ttl=300,
        clock=reloj,
    )
    proveedor.current()

    reloj.ahora += 299
    proveedor.current()

    assert consultas == []


def test_a_registry_that_blinks_keeps_the_model_it_had() -> None:
    # Perder el modelo servido porque el registro no contestó sería cambiar una degradación por
    # una caída: lo que ya está cargado sigue sirviendo.
    reloj = RelojFalso()

    def se_cae() -> int:
        raise ConnectionError("el registro no responde")

    proveedor = ModelProvider(
        loader=lambda: {"metadata": {"version": 7}}, version_of=se_cae, ttl=10, clock=reloj
    )
    assert proveedor.current()["metadata"]["version"] == 7
    reloj.ahora += 11

    assert proveedor.current()["metadata"]["version"] == 7


def test_without_a_model_the_provider_says_so_and_sigue_intentando() -> None:
    # Arrancar sin champion no puede ser definitivo: el servicio queda en 503 y lo vuelve a
    # intentar, así que entrenar después lo levanta sin reiniciar nada.
    reloj = RelojFalso()
    disponible = [False]

    def cargar() -> dict[str, Any]:
        if not disponible[0]:
            raise RuntimeError("todavía no hay champion")
        return {"metadata": {"version": 1}}

    proveedor = ModelProvider(loader=cargar, ttl=10, clock=reloj)
    assert proveedor.current() is None

    disponible[0] = True
    reloj.ahora += 11

    assert proveedor.current()["metadata"]["version"] == 1


def test_the_refresh_interval_comes_from_the_environment() -> None:
    # Un operador tiene que poder decidir cuánto tarda en notarse una promoción sin tocar código.
    proveedor = model_provider({"MODEL_TTL_SECONDS": "7"})

    assert proveedor._ttl == 7.0


def test_the_threshold_in_the_artifact_wins_over_the_one_recorded_in_the_run(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # Desde que el umbral viaja adentro del artefacto, ese es el que decide: el parámetro de la
    # corrida queda para comparar entrenamientos, no para configurar el servicio.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params({**bundle["params"], "threshold": 0.81}))

    desde_el_registro = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=14,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 14, tzinfo=UTC),
        threshold=0.58,
    )

    assert desde_el_registro["metadata"]["threshold"] == 0.81


def test_the_encoder_does_not_receive_the_threshold_as_a_parameter(
    tmp_path: Path, bundle: dict[str, Any]
) -> None:
    # El umbral no es un parámetro de codificación: `encode_payload` recibe frecuencias,
    # escaladores y comisarías, y nada más.
    bundle["model"].save_model(tmp_path / "model.ubj")
    (tmp_path / "params.json").write_bytes(dump_params({**bundle["params"], "threshold": 0.81}))

    desde_el_registro = bundle_from_artifacts(
        tmp_path,
        name="chicago-arrest-xgboost",
        version=14,
        metrics={"mcc": 0.58},
        trained_at=datetime(2026, 10, 14, tzinfo=UTC),
    )

    assert set(desde_el_registro["params"]) == {"freq", "scale", "stations"}
