"""Mini-TP 3: servicio gRPC."""

import filecmp
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grpc
import pytest

from arrest_model.schemas import CHICAGO, EXAMPLE_REPORT
from tp3_grpc import scoring_pb2, scoring_pb2_grpc
from tp3_grpc.server import serve

REPO = Path(__file__).resolve().parent.parent
PROTO = "tp3_grpc/scoring.proto"
STUBS = ("tp3_grpc/scoring_pb2.py", "tp3_grpc/scoring_pb2_grpc.py")
# Mismo valor de referencia que usa el TP1: fija codificación, modelo y regla de decisión.
REFERENCE_PROBABILITY = 0.06843266636133194


def _generate_stubs(output_dir: Path) -> None:
    """Genera los stubs dentro de output_dir, con el mismo comando que `make grpc-stubs`."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I",
            ".",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            PROTO,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"protoc falló: {result.stderr}"


def _proto_report(**changes: Any) -> scoring_pb2.CrimeReport:
    """Arma el mensaje gRPC con el ejemplo del contrato REST, aplicando los cambios indicados.

    Un campo en None no se setea, para poder probar la ausencia que permiten los `optional`.
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
    chicago_time = datetime.fromisoformat(data["date"]).replace(tzinfo=CHICAGO)
    message.date.FromDatetime(chicago_time.astimezone(UTC))
    return message


@pytest.fixture(scope="module")
def grpc_stub(bundle: dict[str, Any]) -> Iterator[scoring_pb2_grpc.ArrestScoringStub]:
    server, port = serve(port=0, bundle=bundle)
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield scoring_pb2_grpc.ArrestScoringStub(channel)
    server.stop(0)


def test_versioned_stubs_match_the_proto(tmp_path: Path) -> None:
    for stub in STUBS:
        assert (REPO / stub).exists(), f"falta {stub}: corré `make grpc-stubs`"
    _generate_stubs(tmp_path)
    for stub in STUBS:
        assert filecmp.cmp(REPO / stub, tmp_path / stub, shallow=False), (
            f"{stub} no coincide con {PROTO}: corré `make grpc-stubs`"
        )


def test_predict_matches_the_reference_prediction(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    response = grpc_stub.Predict(_proto_report())
    assert response.arrest == 0
    assert response.probability == pytest.approx(REFERENCE_PROBABILITY)
    assert response.model_name == "chicago-arrest-xgboost"
    assert response.model_version == 1


def test_predict_uses_the_absolute_instant_not_the_wall_clock(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    # Las 23:58 del 31/12 en Chicago son las 05:58 del 1/1 en UTC: si el servidor tomara el día
    # de la semana en UTC, cambiaría el Day_sin y no daría el valor de referencia.
    message = _proto_report()
    message.date.FromDatetime(datetime(2025, 1, 1, 5, 58, tzinfo=UTC))
    assert grpc_stub.Predict(message).probability == pytest.approx(REFERENCE_PROBABILITY)


def test_predict_rejects_a_report_without_latitude(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    with pytest.raises(grpc.RpcError) as error:
        grpc_stub.Predict(_proto_report(latitude=None))
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "latitude" in error.value.details()


def test_predict_rejects_an_unknown_primary_type(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    with pytest.raises(grpc.RpcError) as error:
        grpc_stub.Predict(_proto_report(primary_type="BANANA"))
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "primary_type" in error.value.details()


def test_predict_stream_returns_one_prediction_per_item_in_order(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    # Diez items alternando dos reportes distintos: sirve para ver que se respeta el orden.
    batch = scoring_pb2.CrimeBatch(items=[_proto_report(), _proto_report(primary_type="THEFT")] * 5)
    predictions = list(grpc_stub.PredictStream(batch))
    assert len(predictions) == 10
    assert predictions[0].probability == pytest.approx(REFERENCE_PROBABILITY)
    assert predictions[8].probability == pytest.approx(REFERENCE_PROBABILITY)
    assert predictions[1].probability != predictions[0].probability
    assert [p.probability for p in predictions[::2]] == [predictions[0].probability] * 5
    assert [p.probability for p in predictions[1::2]] == [predictions[1].probability] * 5


def test_predict_stream_rejects_an_empty_batch(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    with pytest.raises(grpc.RpcError) as error:
        list(grpc_stub.PredictStream(scoring_pb2.CrimeBatch()))
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_predict_stream_fails_before_emitting_anything_if_an_item_is_invalid(
    grpc_stub: scoring_pb2_grpc.ArrestScoringStub,
) -> None:
    batch = scoring_pb2.CrimeBatch(
        items=[_proto_report(), _proto_report(primary_type="BANANA"), _proto_report()]
    )
    stream = grpc_stub.PredictStream(batch)
    # El primer next() ya tiene que fallar: se valida todo el lote antes de puntuar nada.
    with pytest.raises(grpc.RpcError) as error:
        next(stream)
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "item 1" in error.value.details()
    assert "primary_type" in error.value.details()
