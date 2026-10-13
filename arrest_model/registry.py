"""De dónde sale el modelo que sirven las APIs: el .pkl versionado o el champion del registro.

Los mini-TPs sirven el `.pkl` que está en el repo. Dentro de la plataforma del integrador, en
cambio, el modelo lo produce el DAG de entrenamiento y lo publica el Model Registry de MLflow,
así que promover una versión tiene que ser una operación de registro y no un redespliegue.

Este módulo es el único que conoce las dos procedencias. No importa `mlflow` al cargarse: una
imagen que sirve el `.pkl` no tiene por qué traer el cliente de MLflow instalado.
"""

import logging
import os
import tempfile
import time
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

logger = logging.getLogger(__name__)

MODEL_URI_ENV = "MODEL_URI"

# Cada cuánto se le pregunta al registro si hay otra versión, configurable por entorno. La
# consulta cuesta milisegundos y no baja artefactos, así que el valor decide cuánto tarda en
# notarse una promoción, no cuánto cuesta servir.
MODEL_TTL_ENV = "MODEL_TTL_SECONDS"
DEFAULT_TTL_SECONDS = 300.0
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
    threshold: float | None = None,
) -> dict[str, Any]:
    """Arma el bundle `{model, params, metadata}` con los artefactos que bajó el registro.

    Es la misma forma que devuelve `load_bundle`, para que los tres servicios no se enteren de
    dónde salió el modelo. Lo que el registro no guarda como artefacto —la versión, las métricas,
    cuándo se entrenó— entra por parámetro, de la corrida que produjo esa versión.
    """
    estimador = XGBClassifier()
    estimador.load_model(str(_find(directory, MODEL_FILE)))
    # La clave del umbral solo existe si el entrenamiento eligió uno: `predict` la lee con `get`,
    # así que su ausencia es lo que deja el 0.5 por defecto.
    umbral = {"threshold": float(threshold)} if threshold is not None else {}
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
            **umbral,
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
    # El umbral que eligió el entrenamiento, si eligió uno. Las versiones registradas antes de
    # que lo hiciera no traen ninguno y se sirven con el 0.5 de siempre.
    threshold: float | None = None


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
    # El umbral de decisión viaja como parámetro de la corrida. Las versiones registradas antes
    # de que el entrenamiento eligiera uno no lo traen, y se sirven con el 0.5 por defecto.
    registrado = run.data.params.get("threshold")
    registrado = float(registrado) if registrado is not None else None
    local = mlflow.artifacts.download_artifacts(
        artifact_uri=uri, dst_path=tempfile.mkdtemp(prefix="champion-")
    )
    return ModelSource(
        directory=Path(local),
        name=version.name,
        version=int(version.version),
        metrics=dict(run.data.metrics),
        trained_at=datetime.fromtimestamp(run.info.start_time / 1000, UTC),
        threshold=registrado,
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
        threshold=source.threshold,
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


class ModelProvider:
    """Mantiene el modelo cargado y lo reemplaza cuando el registro tiene otra versión.

    Sin esto, el alias se resuelve una sola vez al arrancar y promover una versión obliga a
    reiniciar el servicio. Con esto, promover es mover el alias y esperar al próximo chequeo.

    El chequeo es barato a propósito: pregunta el número de versión, que es una llamada al
    registro, y solo baja los artefactos cuando cambió. Bajarlos en cada request multiplicaría
    por cien la latencia de un servicio cuya mediana es de milisegundos.

    Y si el registro no contesta, se sigue sirviendo lo que ya estaba cargado: perder el modelo
    porque el registro parpadeó sería cambiar una degradación por una caída.
    """

    def __init__(
        self,
        loader: Callable[[], dict[str, Any]],
        version_of: Callable[[], Any] | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader
        self._version_of = version_of
        self._ttl = ttl
        self._clock = clock
        self._bundle: dict[str, Any] | None = None
        self._version: Any = None
        self._checked: float | None = None

    def current(self) -> dict[str, Any] | None:
        """El modelo que hay que servir ahora, o None si todavía no se pudo cargar ninguno."""
        if self._bundle is None:
            return self._cargar()
        if self._version_of is None or self._vigente():
            return self._bundle
        self._checked = self._clock()
        try:
            publicada = self._version_of()
        except Exception:
            logger.warning("No se pudo consultar la versión; sigo con la que está cargada")
            return self._bundle
        if publicada == self._version:
            return self._bundle
        logger.info("El registro publica la versión %s; recargando", publicada)
        return self._cargar() or self._bundle

    def _vigente(self) -> bool:
        """Si el último chequeo todavía está dentro del ttl."""
        return self._checked is not None and self._clock() - self._checked < self._ttl

    def _cargar(self) -> dict[str, Any] | None:
        """Intenta cargar y deja anotado cuándo, para no reintentar en cada request."""
        if self._bundle is None and self._vigente():
            return None
        self._checked = self._clock()
        try:
            bundle = self._loader()
        except Exception:
            logger.exception("No se pudo cargar el modelo")
            return None
        self._bundle = bundle
        self._version = bundle.get("metadata", {}).get("version")
        return bundle


def published_version(uri: str) -> Any:
    """El número de versión que el registro publica hoy para esa uri.

    Es la consulta barata del proveedor: resuelve el alias sin bajar ningún artefacto.
    """
    import mlflow  # acá dentro: la imagen que sirve el .pkl no trae el cliente de MLflow

    return registered_version(mlflow.MlflowClient(), uri).version


def model_provider(env: Mapping[str, str] = os.environ, ttl: float | None = None) -> ModelProvider:
    """El proveedor que los servicios consultan en cada request.

    Sin `MODEL_URI` el modelo es el `.pkl` versionado en el repo, que no cambia mientras el
    proceso vive: el proveedor lo carga una vez y no vuelve a preguntar nada.
    """
    if ttl is None:
        ttl = float(env.get(MODEL_TTL_ENV) or DEFAULT_TTL_SECONDS)
    uri = env.get(MODEL_URI_ENV, "").strip()
    if not uri:
        return ModelProvider(loader=load_bundle, ttl=ttl)
    return ModelProvider(
        loader=partial(load_from_registry, uri),
        version_of=partial(published_version, uri),
        ttl=ttl,
    )


def load_model_bundle() -> dict[str, Any]:
    """Carga el modelo de donde diga el entorno. Es lo que llaman los tres servicios al arrancar."""
    return resolve_loader()()
