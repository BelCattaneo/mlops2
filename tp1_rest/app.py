"""Mini-TP 1: API REST que sirve el modelo de arrestos de Chicago."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from arrest_model.model import load_bundle

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

    return app


app = create_app()
