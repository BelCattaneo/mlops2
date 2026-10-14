"""Mini-TP 1: API REST que sirve el modelo de arrestos de Chicago."""

import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
from tp1_rest.security import OpenGuard, TokenGuard, guard_from_env, report_digest

logger = service_logger("tp1_rest")
bearer = HTTPBearer(auto_error=False)  # el 401 lo decide el guardia, no el esquema

# El motivo real (ruta del modelo, traza) va al log del servidor, no a la respuesta.
UNAVAILABLE_DETAIL = "El modelo no está disponible; revisá el log del servicio."
INTERNAL_ERROR_DETAIL = "Error interno del servicio; revisá el log para el detalle."


def audit_trail(request: Request) -> str:
    """Lo que la auditoría le suma a la línea del log: quién preguntó y por qué cosa.

    Sale del estado de la request, así que una request rechazada queda igual registrada con su
    status: un registro que solo guarda lo que salió bien no sirve para detectar el abuso.
    """
    user = getattr(request.state, "user", None)
    digest = getattr(request.state, "digest", None)
    return "".join(
        parte
        for parte in (f", usuario {user}" if user else "", f", entrada {digest}" if digest else "")
    )


def create_app(
    loader: Callable[[], dict[str, Any]] = load_bundle,
    guard: OpenGuard | TokenGuard | None = None,
) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo y `guard` decide quién puede pedirlo.

    Sin guardia sirve abierto, que es lo que entrega el mini-TP 1. La plataforma lo arma con
    `service()`, que lo saca del entorno y no arranca si falta el secreto.
    """
    guard = guard or OpenGuard()

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
            "%s %s -> %s en %.1f ms (modelo v%s%s)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            metadata.get("version"),
            audit_trail(request),
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

    def caller(
        request: Request,
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        """Quién pide esto: 401 si no se sabe, 403 si su rol no alcanza.

        Deja el usuario en el estado de la request para que la auditoría lo escriba incluso
        cuando la predicción después falla. Un 403 queda sin usuario a propósito: la
        autorización corta antes, y el patrón se ve igual por ruta y status.
        """
        user = guard.identify(credential)
        request.state.user = user
        return user

    def charged(request: Request, user: str, reports: list[CrimeReport]) -> list[CrimeReport]:
        """Cobra los reportes al presupuesto del usuario y los deja anotados en la auditoría."""
        guard.charge(user, len(reports))
        request.state.digest = report_digest([report.model_dump() for report in reports])
        return reports

    v1 = APIRouter(prefix="/v1")  # versionado como el nivel 3 de API_MLOPS2.ipynb

    @v1.post("/predict", response_model=PredictionOut)
    def predict_one(
        request: Request, report: CrimeReport, user: Annotated[str, Depends(caller)]
    ) -> PredictionOut:
        """Predice un reporte; FastAPI ya validó el payload (422 si no cumple)."""
        return predict(loaded_bundle(), charged(request, user, [report]))[0]

    @v1.post("/predict/batch", response_model=BatchPredictionOut)
    def predict_batch(
        request: Request, batch: BatchRequest, user: Annotated[str, Depends(caller)]
    ) -> BatchPredictionOut:
        """Predice de 1 a 1000 reportes con una sola llamada al modelo."""
        reports = charged(request, user, batch.reports)
        return BatchPredictionOut(predictions=predict(loaded_bundle(), reports))

    @v1.get("/metadata", response_model=ModelMetadata)
    def metadata(user: Annotated[str, Depends(caller)]) -> ModelMetadata:
        """Describe el modelo cargado: versión, entradas, features y métricas de test.

        Pide token aunque no prediga: publica las métricas, las features y el umbral de
        decisión, que es lo que necesita quien quiere entrenar un sustituto del modelo.
        """
        return ModelMetadata.model_validate(loaded_bundle()["metadata"])

    app.include_router(v1)
    return app


# El mini-TP 1: la API abierta, que es como se entregó y como la usan su cliente, su notebook y
# el benchmark de gRPC. Corrida suelta sirve el .pkl del repo; con `MODEL_URI`, el champion del
# registro. Lo decide el proveedor, no este módulo, y es también el que hace que promover una
# versión no exija reiniciar el servicio.
app = create_app(model_provider().current)


def service() -> FastAPI:
    """La app de la plataforma: el mismo servicio, detrás del control de acceso del entorno.

    Es una fábrica y no un objeto de módulo porque así el control se resuelve al arrancar el
    proceso: sin `REST_JWT_SECRET` el servicio no levanta, en vez de levantar abierto. El compose
    la invoca con `uvicorn --factory`.
    """
    guard = guard_from_env(os.environ)  # primero el guardia: si falta el secreto, no se sigue
    return create_app(model_provider().current, guard)
