"""Mini-TP 3: servidor gRPC que sirve el modelo de arrestos de Chicago.

Mismo núcleo que la API REST: valida con `CrimeReport` y puntúa con `predict`. Lo único
propio de acá es traducir entre los mensajes protobuf y ese núcleo.
"""

import time
from collections.abc import Callable, Iterator, Sequence
from concurrent import futures
from datetime import UTC
from typing import Any

import grpc
from pydantic import ValidationError

from arrest_model.log import service_logger
from arrest_model.model import predict
from arrest_model.registry import load_model_bundle
from arrest_model.schemas import CrimeReport, PredictionOut
from tp3_grpc import scoring_pb2, scoring_pb2_grpc

logger = service_logger("tp3_grpc")


def report_from_proto(message: scoring_pb2.CrimeReport) -> dict[str, Any]:
    """Pasa el mensaje a un dict con **solo los campos presentes**.

    Lo ausente se omite en vez de viajar en cero: así un campo que falta da error de
    validación y no una predicción sobre un dato inventado.
    """
    report: dict[str, Any] = {"iucr": message.iucr, "primary_type": message.primary_type}
    if message.HasField("location_description"):
        report["location_description"] = message.location_description
    if message.HasField("date"):
        # ToDatetime() devuelve UTC sin zona; se la ponemos para que CrimeReport la convierta
        # a hora de Chicago, que es como se entrenó el Day_sin.
        report["date"] = message.date.ToDatetime().replace(tzinfo=UTC)
    for field in ("latitude", "longitude"):
        if message.HasField(field):
            report[field] = getattr(message, field)
    return report


def validation_detail(error: ValidationError) -> str:
    """Resume los errores nombrando el campo que falló, sin exponer nada interno."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )


def prediction_to_proto(prediction: PredictionOut) -> scoring_pb2.Prediction:
    """Pasa la predicción del núcleo al mensaje del contrato gRPC."""
    return scoring_pb2.Prediction(
        arrest=prediction.arrest,
        probability=prediction.probability,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
    )


def validated_reports(
    messages: Sequence[scoring_pb2.CrimeReport], context: grpc.ServicerContext, *, indexed: bool
) -> list[CrimeReport]:
    """Valida **todos** los mensajes antes de que se puntúe ninguno.

    Con `indexed`, el detalle del error dice qué item del lote falló: en un stream, si no
    se validara todo primero, el cliente recibiría predicciones y recién después el error.
    """
    reports = []
    for index, message in enumerate(messages):
        try:
            reports.append(CrimeReport.model_validate(report_from_proto(message)))
        except ValidationError as exc:
            prefix = f"item {index}: " if indexed else ""
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, prefix + validation_detail(exc))
    return reports


class ArrestScoringServicer(scoring_pb2_grpc.ArrestScoringServicer):
    """Sirve un modelo ya cargado; la carga es responsabilidad de `serve`."""

    def __init__(self, bundle: dict[str, Any]) -> None:
        self.bundle = bundle

    def Predict(  # noqa: N802 (el nombre lo fija el .proto)
        self, request: scoring_pb2.CrimeReport, context: grpc.ServicerContext
    ) -> scoring_pb2.Prediction:
        """Unary: valida un reporte y devuelve su predicción."""
        reports = validated_reports([request], context, indexed=False)
        return prediction_to_proto(predict(self.bundle, reports)[0])

    def PredictStream(  # noqa: N802 (el nombre lo fija el .proto)
        self, request: scoring_pb2.CrimeBatch, context: grpc.ServicerContext
    ) -> Iterator[scoring_pb2.Prediction]:
        """Server streaming: valida el lote entero, puntúa de una y emite una por item."""
        if not request.items:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "el lote no puede estar vacío")
        reports = validated_reports(request.items, context, indexed=True)
        # Una sola llamada al modelo para todo el lote; el stream es solo la entrega.
        for prediction in predict(self.bundle, reports):
            yield prediction_to_proto(prediction)


class RequestLogger(grpc.ServerInterceptor):
    """Deja una línea por RPC con método, status, latencia y versión del modelo.

    Es el equivalente gRPC del middleware HTTP del TP1. Va como interceptor y no dentro de cada
    método para cubrir a todos los del servicio con un solo lugar, incluidos los que cortan con
    `abort`. Sin esto el servicio gRPC haría menos trabajo que el REST por request, y la
    comparación de latencia mediría esa diferencia en vez del protocolo.

    Lo que no cubre: una llamada a un método que no existe termina en UNIMPLEMENTED sin pasar
    por acá, porque gRPC ni siquiera resuelve un handler que envolver.
    """

    def __init__(self, model_version: Any) -> None:
        self.model_version = model_version

    def intercept_service(self, continuation: Callable[[Any], Any], details: Any) -> Any:
        """Envuelve el handler del método para medirlo y loguearlo."""
        handler = continuation(details)
        if handler is None:
            return handler
        method = details.method.rsplit("/", 1)[-1]
        common = {
            "request_deserializer": handler.request_deserializer,
            "response_serializer": handler.response_serializer,
        }
        if handler.unary_unary is not None:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary(handler.unary_unary, method), **common
            )
        if handler.unary_stream is not None:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_stream(handler.unary_stream, method), **common
            )
        # Client-streaming o bidireccional: se deja pasar sin loguear, en vez de registrarlo
        # con el tipo equivocado y fallar recién en la primera llamada.
        return handler

    def _log(
        self, method: str, context: grpc.ServicerContext, started: float, *, completed: bool
    ) -> None:
        """Escribe la línea con el status con el que terminó el RPC.

        `context.code()` es None mientras nadie lo haya fijado, así que no alcanza para decidir
        el status: un stream cancelado por el cliente, o un handler que revienta sin `abort`,
        llegarían acá con None y se loguearían como OK. Por eso `completed` dice si el handler
        llegó al final; si no llegó y nadie fijó código, se registra UNKNOWN.

        No propaga nunca: se llama desde un `finally`, así que si fallara acá taparía la
        excepción real del handler y un INVALID_ARGUMENT limpio se volvería un error opaco.
        """
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            fallback = grpc.StatusCode.OK if completed else grpc.StatusCode.UNKNOWN
            code = context.code() or fallback
            logger.info(
                "%s -> %s en %.1f ms (modelo v%s)",
                method,
                code.name,
                elapsed_ms,
                self.model_version,
            )
        except Exception:
            logger.exception("No se pudo loguear el RPC %s", method)

    def _wrap_unary(self, behavior: Callable[..., Any], method: str) -> Callable[..., Any]:
        """Handler unary con el log al final, pase lo que pase."""

        def wrapper(request: Any, context: grpc.ServicerContext) -> Any:
            started = time.perf_counter()
            completed = False
            try:
                response = behavior(request, context)
                completed = True
                return response
            finally:
                self._log(method, context, started, completed=completed)

        return wrapper

    def _wrap_stream(self, behavior: Callable[..., Any], method: str) -> Callable[..., Any]:
        """Handler de streaming: el log va cuando se agota el stream, no cuando se crea."""

        def wrapper(request: Any, context: grpc.ServicerContext) -> Iterator[Any]:
            started = time.perf_counter()
            completed = False
            try:
                yield from behavior(request, context)
                completed = True
            finally:
                self._log(method, context, started, completed=completed)

        return wrapper


def serve(
    port: int = 50051,
    bundle: dict[str, Any] | None = None,
    host: str = "0.0.0.0",  # noqa: S104 (en el contenedor tiene que aceptar desde afuera)
    max_workers: int = 4,
) -> tuple[grpc.Server, int]:
    """Arranca el servidor y devuelve (servidor, puerto asignado) **sin bloquear**.

    Con `port=0` el sistema elige un puerto libre, que es lo que usan los tests y el notebook.
    El modelo se carga una sola vez, acá.
    """
    # Sin bundle inyectado, de donde diga el entorno: el .pkl del repo o el champion.
    loaded = load_model_bundle() if bundle is None else bundle
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        interceptors=[RequestLogger(loaded["metadata"]["version"])],
    )
    scoring_pb2_grpc.add_ArrestScoringServicer_to_server(ArrestScoringServicer(loaded), server)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    server.start()
    logger.info("Servidor gRPC escuchando en %s:%s", host, bound_port)
    return server, bound_port


def main() -> None:
    """Levanta el servidor y espera; se corre con `uv run python -m tp3_grpc.server`."""
    server, _ = serve()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
