"""Mini-TP 1: API REST que sirve el modelo de arrestos de Chicago."""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from arrest_model.log import service_logger
from arrest_model.model import load_bundle, predict
from arrest_model.registry import model_provider
from arrest_model.schemas import (
    BatchPredictionOut,
    BatchRequest,
    CrimeReport,
    ModelMetadata,
    PredictionOut,
)

logger = service_logger("tp1_rest")

# El motivo real (ruta del modelo, traza) va al log del servidor, no a la respuesta.
UNAVAILABLE_DETAIL = "El modelo no está disponible; revisá el log del servicio."
INTERNAL_ERROR_DETAIL = "Error interno del servicio; revisá el log para el detalle."


def create_app(loader: Callable[[], dict[str, Any]] = load_bundle) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo (los tests inyectan otro)."""

    def vigente() -> dict[str, Any] | None:
        """El modelo que hay que servir ahora, consultando al cargador.

        Se le pregunta en cada request y no una sola vez al arrancar, porque así promover una
        versión en el registro no exige reiniciar el servicio. Quien decide cuánto cuesta esa
        pregunta es el cargador: el de la plataforma cachea y solo consulta al registro cada
        tanto. Y si falla, se sigue sirviendo lo que ya estaba cargado.
        """
        try:
            actual = loader()
        except Exception:
            logger.exception("No se pudo cargar el modelo")  # traza completa para diagnosticar
            actual = None
        if actual is not None:
            app.state.bundle = actual
        return app.state.bundle

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Intenta cargar al arrancar; si falla, la app igual sirve y lo dice en /health."""
        vigente()
        yield

    app = FastAPI(title="Mini-TP 1 · Arrestos en Chicago", lifespan=lifespan)
    app.state.bundle = None

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Deja una línea por request y convierte cualquier error inesperado en un 500 genérico.

        Va en el mismo lugar porque el log necesita el status y la latencia incluso cuando la
        request falla.
        """
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Error inesperado en %s %s", request.method, request.url.path)
            response = JSONResponse({"detail": INTERNAL_ERROR_DETAIL}, 500)
        metadata = (app.state.bundle or {}).get("metadata", {})
        logger.info(
            "%s %s -> %s en %.1f ms (modelo v%s)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            metadata.get("version"),
        )
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        """Estado del servicio: 200 con el modelo cargado, 503 si no se pudo cargar."""
        bundle = vigente()
        if bundle is None:
            return JSONResponse({"status": "unavailable", "detail": UNAVAILABLE_DETAIL}, 503)
        metadata = bundle["metadata"]
        return JSONResponse(
            {"status": "ok", "model_name": metadata["name"], "model_version": metadata["version"]}
        )

    def loaded_bundle() -> dict[str, Any]:
        """Devuelve el modelo vigente o corta con 503 si no hay ninguno."""
        bundle = vigente()
        if bundle is None:
            raise HTTPException(503, detail=UNAVAILABLE_DETAIL)
        return bundle

    v1 = APIRouter(prefix="/v1")  # versionado como el nivel 3 de API_MLOPS2.ipynb

    @v1.post("/predict", response_model=PredictionOut)
    def predict_one(report: CrimeReport) -> PredictionOut:
        """Predice un reporte; FastAPI ya validó el payload (422 si no cumple)."""
        return predict(loaded_bundle(), [report])[0]

    @v1.post("/predict/batch", response_model=BatchPredictionOut)
    def predict_batch(batch: BatchRequest) -> BatchPredictionOut:
        """Predice de 1 a 1000 reportes con una sola llamada al modelo."""
        return BatchPredictionOut(predictions=predict(loaded_bundle(), batch.reports))

    @v1.get("/metadata", response_model=ModelMetadata)
    def metadata() -> ModelMetadata:
        """Describe el modelo cargado: versión, entradas, features y métricas de test."""
        return ModelMetadata.model_validate(loaded_bundle()["metadata"])

    app.include_router(v1)
    return app


# Corrido suelto sirve el .pkl del repo; dentro de la plataforma, con `MODEL_URI`, el champion
# del registro de MLflow. Lo decide el proveedor, no este módulo, y es también el que hace que
# promover una versión no exija reiniciar el servicio.
app = create_app(model_provider().current)
