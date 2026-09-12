"""Mini-TP 1: API REST que sirve el modelo de arrestos de Chicago."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from arrest_model.model import load_bundle, predict
from arrest_model.schemas import BatchPredictionOut, BatchRequest, CrimeReport, PredictionOut

logger = logging.getLogger("tp1_rest")

# El motivo real (ruta del modelo, traza) va al log del servidor, no a la respuesta.
UNAVAILABLE_DETAIL = "El modelo no está disponible; revisá el log del servicio."


def create_app(loader: Callable[[], dict[str, Any]] = load_bundle) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo (los tests inyectan otro)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Carga el modelo al arrancar; si falla, la app igual sirve y lo informa en /health."""
        try:
            app.state.bundle = loader()  # una sola vez, al arrancar
        except Exception:
            logger.exception("No se pudo cargar el modelo")  # traza completa para diagnosticar
        yield

    app = FastAPI(title="Mini-TP 1 · Arrestos en Chicago", lifespan=lifespan)
    app.state.bundle = None

    @app.get("/health")
    def health() -> JSONResponse:
        """Estado del servicio: 200 con el modelo cargado, 503 si no se pudo cargar."""
        if app.state.bundle is None:
            return JSONResponse({"status": "unavailable", "detail": UNAVAILABLE_DETAIL}, 503)
        metadata = app.state.bundle["metadata"]
        return JSONResponse(
            {"status": "ok", "model_name": metadata["name"], "model_version": metadata["version"]}
        )

    def loaded_bundle() -> dict[str, Any]:
        """Devuelve el bundle cargado o corta con 503 si el modelo no está disponible."""
        if app.state.bundle is None:
            raise HTTPException(503, detail=UNAVAILABLE_DETAIL)
        return app.state.bundle

    v1 = APIRouter(prefix="/v1")  # versionado como el nivel 3 de API_MLOPS2.ipynb

    @v1.post("/predict", response_model=PredictionOut)
    def predict_one(report: CrimeReport) -> PredictionOut:
        """Predice un reporte; FastAPI ya validó el payload (422 si no cumple)."""
        return predict(loaded_bundle(), [report])[0]

    @v1.post("/predict/batch", response_model=BatchPredictionOut)
    def predict_batch(batch: BatchRequest) -> BatchPredictionOut:
        """Predice de 1 a 1000 reportes con una sola llamada al modelo."""
        return BatchPredictionOut(predictions=predict(loaded_bundle(), batch.reports))

    app.include_router(v1)
    return app


app = create_app()
