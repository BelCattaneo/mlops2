"""Mini-TP 4: el mismo conjunto de eventos, puntuado de a uno y puntuado de una vez.

Los dos caminos hacen el mismo trabajo —validar el reporte, codificarlo y predecir— y se miden
del mismo lado, sin la cola ni el ritmo de llegada: lo que se compara es agrupar o no agrupar,
no la simulación del flujo.

Uso: `uv run python -m tp4_streaming.compare [--events N]`, o `make stream-compare`.
"""

import argparse
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from arrest_model.model import load_bundle, predict
from arrest_model.schemas import CrimeReport, PredictionOut
from tp4_streaming.events import crime_stream

EVENTS = 1000


@dataclass(frozen=True)
class Comparison:
    """Lo que costó cada camino y si llegaron al mismo resultado."""

    events: int
    online_seconds: float
    batch_seconds: float
    same_predictions: bool


def score_online(events: Sequence[dict[str, Any]], bundle: dict[str, Any]) -> list[PredictionOut]:
    """Valida y puntúa un evento por vez, como lo hace el consumidor del flujo."""
    return [predict(bundle, [CrimeReport.model_validate(event)])[0] for event in events]


def score_batch(events: Sequence[dict[str, Any]], bundle: dict[str, Any]) -> list[PredictionOut]:
    """Valida todo y puntúa el lote con una sola llamada al modelo."""
    return predict(bundle, [CrimeReport.model_validate(event) for event in events])


def compare(events: Sequence[dict[str, Any]], bundle: dict[str, Any]) -> Comparison:
    """Puntúa los mismos eventos por los dos caminos y devuelve qué costó cada uno."""
    started = time.perf_counter()
    online = score_online(events, bundle)
    online_seconds = time.perf_counter() - started

    started = time.perf_counter()
    batch = score_batch(events, bundle)
    batch_seconds = time.perf_counter() - started

    return Comparison(
        events=len(events),
        online_seconds=online_seconds,
        batch_seconds=batch_seconds,
        same_predictions=online == batch,
    )


def format_comparison(comparison: Comparison) -> str:
    """Arma la tabla en markdown, lista para el notebook o el README."""

    def fila(camino: str, seconds: float) -> str:
        total_ms = seconds * 1000
        return f"| {camino} | {total_ms:.1f} | {total_ms / comparison.events:.3f} |"

    return "\n".join(
        [
            f"Los mismos {comparison.events} eventos, puntuados de las dos formas.",
            "",
            "| camino | total (ms) | por evento (ms) |",
            "|---|---|---|",
            fila("online", comparison.online_seconds),
            fila("batch", comparison.batch_seconds),
            "",
            f"Las predicciones coinciden: {comparison.same_predictions}.",
        ]
    )


def main() -> int:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser(description="Un flujo puntuado de a uno contra en lote")
    parser.add_argument("--events", type=int, default=EVENTS)
    args = parser.parse_args()
    print(format_comparison(compare(list(crime_stream(args.events)), load_bundle())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
