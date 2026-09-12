"""Mini-TP 3: servidor gRPC que sirve el modelo de arrestos de Chicago.

Mismo núcleo que la API REST: valida con `CrimeReport` y puntúa con `predict`. Lo único
propio de acá es traducir entre los mensajes protobuf y ese núcleo.
"""

import logging
from collections.abc import Iterator, Sequence
from concurrent import futures
from datetime import UTC
from typing import Any

import grpc
from pydantic import ValidationError

from arrest_model.model import load_bundle, predict
from arrest_model.schemas import CrimeReport, PredictionOut
from tp3_grpc import scoring_pb2, scoring_pb2_grpc

logger = logging.getLogger("tp3_grpc")

# Acá no hay uvicorn que configure el logging: sin esto los INFO se descartan en el contenedor.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")


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
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = ArrestScoringServicer(load_bundle() if bundle is None else bundle)
    scoring_pb2_grpc.add_ArrestScoringServicer_to_server(servicer, server)
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
