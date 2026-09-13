"""Cliente de prueba del Mini-TP 3: llama al servicio gRPC y muestra cada respuesta.

Equivalente al cliente del TP1, pero contra gRPC: en vez de status HTTP se comparan
códigos de `grpc.StatusCode`.
"""

import argparse
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import grpc

from arrest_model.schemas import CHICAGO, EXAMPLE_REPORT
from tp3_grpc import scoring_pb2, scoring_pb2_grpc

CONNECT_TIMEOUT = 15  # segundos que espera a que el servidor acepte conexiones


def crime_report(**changes: Any) -> scoring_pb2.CrimeReport:
    """Arma el mensaje a partir del ejemplo del contrato REST, aplicando los cambios indicados.

    Un campo en None no se setea: así se prueba la ausencia que permiten los `optional`.
    La fecha del ejemplo es hora de Chicago y viaja como instante UTC.
    """
    data = dict(EXAMPLE_REPORT) | changes
    message = scoring_pb2.CrimeReport(
        iucr=data["iucr"],
        primary_type=data["primary_type"],
        location_description=data["location_description"],
    )
    for field in ("latitude", "longitude"):
        if data[field] is not None:
            setattr(message, field, data[field])
    if data["date"] is not None:
        chicago_time = datetime.fromisoformat(data["date"]).replace(tzinfo=CHICAGO)
        message.date.FromDatetime(chicago_time.astimezone(UTC))
    return message


def describe(result: Any) -> str:
    """Resume una predicción, o una lista de predicciones, en una línea."""
    predictions = result if isinstance(result, list) else [result]
    return " | ".join(f"arrest={p.arrest} probability={p.probability:.6f}" for p in predictions)


def check(label: str, expected: grpc.StatusCode, call: Callable[[], Any]) -> bool:
    """Corre la llamada y muestra el status; devuelve si fue el esperado."""
    try:
        code, detail = grpc.StatusCode.OK, describe(call())
    except grpc.RpcError as error:
        code, detail = error.code(), error.details()
    ok = code == expected
    print(f"[{'OK' if ok else 'FALLA'}] {label} -> {code.name} (esperado {expected.name})")
    print(f"     {detail}")
    return ok


def check_stream(stub: scoring_pb2_grpc.ArrestScoringStub, count: int = 10) -> bool:
    """Consume un lote por streaming, mostrando cada predicción a medida que llega."""
    label = f"PredictStream con {count} reportes"
    # Se alternan dos reportes distintos para ver que el orden se respeta; con `count` impar
    # el truncamiento dejaría menos items de los que después se exigen.
    alternados = [crime_report(), crime_report(primary_type="THEFT")]
    batch = scoring_pb2.CrimeBatch(items=[alternados[i % 2] for i in range(count)])
    received = 0
    try:
        for prediction in stub.PredictStream(batch):
            received += 1
            print(f"     [{received:2}] {describe(prediction)}")
    except grpc.RpcError as error:
        print(f"[FALLA] {label} -> {error.code().name}: {error.details()}")
        return False
    ok = received == count
    print(f"[{'OK' if ok else 'FALLA'}] {label} -> llegaron {received} de {count}")
    return ok


def run_client(target: str) -> int:
    """Recorre los casos contra el servicio; devuelve 0 si todos dan el status esperado."""
    invalid = grpc.StatusCode.INVALID_ARGUMENT
    try:
        with grpc.insecure_channel(target) as channel:
            grpc.channel_ready_future(channel).result(timeout=CONNECT_TIMEOUT)
            stub = scoring_pb2_grpc.ArrestScoringStub(channel)
            results = [
                check(
                    "Predict con un reporte válido",
                    grpc.StatusCode.OK,
                    lambda: stub.Predict(crime_report()),
                ),
                check(
                    "Predict sin latitude",
                    invalid,
                    lambda: stub.Predict(crime_report(latitude=None)),
                ),
                check(
                    "Predict sin fecha",
                    invalid,
                    lambda: stub.Predict(crime_report(date=None)),
                ),
                check(
                    "Predict con primary_type desconocido",
                    invalid,
                    lambda: stub.Predict(crime_report(primary_type="BANANA")),
                ),
                check(
                    "PredictStream con el lote vacío",
                    invalid,
                    lambda: list(stub.PredictStream(scoring_pb2.CrimeBatch())),
                ),
                check_stream(stub),
            ]
    except grpc.FutureTimeoutError:
        print(f"No se pudo conectar a {target}.")
        print("¿Levantaste el servidor con `make grpc-run` o `make grpc-up`?")
        return 1
    return 0 if all(results) else 1


def main() -> int:
    """Punto de entrada: `uv run python -m tp3_grpc.client [--target host:puerto]`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="127.0.0.1:50051")
    return run_client(parser.parse_args().target)


if __name__ == "__main__":
    raise SystemExit(main())
