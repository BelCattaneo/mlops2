"""Mini-TP 1: API REST que sirve el modelo de arrestos de Chicago."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from arrest_model.model import load_bundle, predict
from arrest_model.schemas import CrimeReport, PredictionOut

logger = logging.getLogger("tp1_rest")


def create_app(loader: Callable[[], dict[str, Any]] = load_bundle) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo (los tests inyectan otro)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.bundle = loader()  # una sola vez, al arrancar
        except Exception as exc:
            app.state.load_error = str(exc)
            logger.error("No se pudo cargar el modelo: %s", exc)
        yield

    app = FastAPI(title="Mini-TP 1 · Arrestos en Chicago", lifespan=lifespan)
    app.state.bundle, app.state.load_error = None, None

    @app.get("/health")
    def health() -> JSONResponse:
        if app.state.bundle is None:
            return JSONResponse({"status": "unavailable", "detail": app.state.load_error}, 503)
        metadata = app.state.bundle["metadata"]
        return JSONResponse(
            {"status": "ok", "model_name": metadata["name"], "model_version": metadata["version"]}
        )

    v1 = APIRouter(prefix="/v1")  # versionado como el nivel 3 de API_MLOPS2.ipynb

    @v1.post("/predict", response_model=PredictionOut)
    def predict_one(report: CrimeReport) -> PredictionOut:
        if app.state.bundle is None:
            raise HTTPException(503, detail=f"Modelo no disponible: {app.state.load_error}")
        return predict(app.state.bundle, [report])[0]

    app.include_router(v1)
    return app


app = create_app()
