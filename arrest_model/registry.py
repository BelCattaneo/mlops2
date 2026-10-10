"""De dónde sale el modelo que sirven las APIs: el .pkl versionado o el champion del registro.

Los mini-TPs sirven el `.pkl` que está en el repo. Dentro de la plataforma del integrador, en
cambio, el modelo lo produce el DAG de entrenamiento y lo publica el Model Registry de MLflow,
así que promover una versión tiene que ser una operación de registro y no un redespliegue.

Este módulo es el único que conoce las dos procedencias. No importa `mlflow` al cargarse: una
imagen que sirve el `.pkl` no tiene por qué traer el cliente de MLflow instalado.
"""

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import xgboost
from xgboost import XGBClassifier

from arrest_model.features import MODEL_FEATURES
from arrest_model.model import load_bundle
from arrest_model.params import load_params
from arrest_model.schemas import EXAMPLE_REPORT

MODEL_URI_ENV = "MODEL_URI"
REGISTRY_SCHEME = "models:/"

# Los nombres con los que el DAG de entrenamiento guarda las dos mitades del modelo.
MODEL_FILE = "model.ubj"
PARAMS_FILE = "params.json"


def _find(directory: Path, name: str) -> Path:
    """Ubica un artefacto en el árbol que bajó el registro.

    Busca en todo el árbol en vez de armar la ruta: cómo anida sus artefactos un modelo pyfunc es
    un detalle de MLflow, y si cambia de versión preferimos encontrarlos igual a fallar.
    """
    encontrado = next(iter(sorted(directory.rglob(name))), None)
    if encontrado is None:
        presentes = sorted(ruta.name for ruta in directory.rglob("*") if ruta.is_file())
        raise FileNotFoundError(f"falta {name} entre los artefactos de {directory}: {presentes}")
    return encontrado


def bundle_from_artifacts(
    directory: Path,
    *,
    name: str,
    version: int,
    metrics: dict[str, float],
    trained_at: datetime,
) -> dict[str, Any]:
    """Arma el bundle `{model, params, metadata}` con los artefactos que bajó el registro.

    Es la misma forma que devuelve `load_bundle`, para que los tres servicios no se enteren de
    dónde salió el modelo. Lo que el registro no guarda como artefacto —la versión, las métricas,
    cuándo se entrenó— entra por parámetro, de la corrida que produjo esa versión.
    """
    estimador = XGBClassifier()
    estimador.load_model(str(_find(directory, MODEL_FILE)))
    return {
        "model": estimador,
        "params": load_params(_find(directory, PARAMS_FILE).read_bytes()),
        "metadata": {
            "name": name,
            "version": version,
            "framework": f"xgboost {xgboost.__version__}",
            "inputs": list(EXAMPLE_REPORT),
            "features": list(MODEL_FEATURES),
            "metrics": metrics,
            # Como texto, igual que en el .pkl: `tp2_graphql/schema.py` lo parsea con
            # `datetime.fromisoformat`, así que un datetime ahí rompe la query de GraphQL.
            "trained_at": trained_at.isoformat(),
        },
    }


@dataclass(frozen=True)
class ModelSource:
    """Lo que el registro tiene que aportar: los artefactos bajados y de qué versión salieron."""

    directory: Path
    name: str
    version: int
    metrics: dict[str, float]
    trained_at: datetime


def registered_version(client: Any, uri: str) -> Any:
    """Resuelve `models:/<nombre>@<alias>` o `models:/<nombre>/<version>` a una versión concreta.

    Hay que resolverla a mano porque `mlflow.models.get_model_info` devuelve
    `registered_model_version=None` para una uri por alias (medido contra MLflow 3.16.1), y sin
    el número de versión las APIs no pueden decir qué están sirviendo.
    """
    if not uri.startswith(REGISTRY_SCHEME):
        raise ValueError(f"{MODEL_URI_ENV} tiene que empezar con {REGISTRY_SCHEME!r}, no {uri!r}")
    referencia = uri.removeprefix(REGISTRY_SCHEME)
    if "@" in referencia:
        name, alias = referencia.split("@", 1)
        return client.get_model_version_by_alias(name, alias)
    name, _, version = referencia.rpartition("/")
    if not name:
        raise ValueError(f"{uri!r} no nombra ni un alias ni una versión")
    return client.get_model_version(name, version)


def _fetch_from_mlflow(uri: str) -> ModelSource:
    """Baja los artefactos de esa versión y su procedencia desde MLflow."""
    import mlflow  # acá dentro: la imagen que sirve el .pkl no trae el cliente de MLflow

    client = mlflow.MlflowClient()
    version = registered_version(client, uri)
    run = client.get_run(version.run_id)
    # `mkdtemp` y no `TemporaryDirectory`: los artefactos tienen que seguir en disco después de
    # volver. Es un directorio por arranque del servicio, no por predicción.
    local = mlflow.artifacts.download_artifacts(
        artifact_uri=uri, dst_path=tempfile.mkdtemp(prefix="champion-")
    )
    return ModelSource(
        directory=Path(local),
        name=version.name,
        version=int(version.version),
        metrics=dict(run.data.metrics),
        trained_at=datetime.fromtimestamp(run.info.start_time / 1000, UTC),
    )


def load_from_registry(
    uri: str, fetch: Callable[[str], ModelSource] = _fetch_from_mlflow
) -> dict[str, Any]:
    """Arma el bundle con la versión que el registro resuelve para esa uri."""
    source = fetch(uri)
    return bundle_from_artifacts(
        source.directory,
        name=source.name,
        version=source.version,
        metrics=source.metrics,
        trained_at=source.trained_at,
    )


def resolve_loader(
    env: Mapping[str, str] = os.environ,
    fetch: Callable[[str], ModelSource] = _fetch_from_mlflow,
) -> Callable[[], dict[str, Any]]:
    """Elige el cargador según el entorno: sin `MODEL_URI`, el `.pkl` versionado del repo.

    Es el único lugar donde se decide la procedencia. Los tres servicios reciben un cargador y
    no se enteran: corridos sueltos como mini-TPs sirven el `.pkl`, y dentro de la plataforma,
    con `MODEL_URI` apuntando al alias `champion`, sirven lo que registró el entrenamiento.
    """
    uri = env.get(MODEL_URI_ENV, "").strip()
    if not uri:
        return load_bundle
    return partial(load_from_registry, uri, fetch=fetch)


def load_model_bundle() -> dict[str, Any]:
    """Carga el modelo de donde diga el entorno. Es lo que llaman los tres servicios al arrancar."""
    return resolve_loader()()
