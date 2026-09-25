"""Mini-TP 4: el consumidor que puntúa el flujo evento por evento.

Cada evento se valida con el mismo contrato que la API REST, se codifica y se puntúa apenas
llega: eso es inferencia online. Cada tantos eventos se cierra una ventana y se informa cómo
viene el flujo, que es lo que se monitorea en producción.
"""

import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from statistics import mean
from typing import Any

from arrest_model.model import predict
from arrest_model.schemas import CrimeReport
from tp4_streaming.metrics import drift_indicator, p95, window_throughput

WINDOW_SECONDS = 10.0
REPORT_EVERY = 50
# Medio desvío de corrimiento sostenido respecto del entrenamiento ya es un cambio real y no
# ruido del flujo, que se mueve alrededor de 0.3.
DRIFT_THRESHOLD = 0.5


@dataclass(frozen=True)
class WindowReport:
    """Cómo venía el flujo en una ventana."""

    scored: int  # eventos puntuados desde que arrancó el flujo
    events: int  # eventos dentro de la ventana
    throughput: float  # eventos por segundo
    p95_ms: float  # latencia que el 95% de los eventos de la ventana no supera
    drift: float  # desvíos de distancia entre las entradas de la ventana y el entrenamiento
    mean_probability: float  # probabilidad media de arresto que predijo el modelo
    alert: bool  # True solo en la ventana en la que el drift cruza el umbral


def score_stream(
    source: Iterable[dict[str, Any]],
    bundle: dict[str, Any],
    *,
    window_seconds: float = WINDOW_SECONDS,
    report_every: int = REPORT_EVERY,
    threshold: float = DRIFT_THRESHOLD,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[WindowReport]:
    """Puntúa cada evento del flujo y cierra una ventana cada `report_every` eventos.

    La ventana es deslizante: guarda lo que llegó en los últimos `window_seconds` y descarta lo
    viejo, así las métricas describen cómo viene el flujo ahora y no desde que arrancó. El corte
    es semiabierto, así que con un evento por segundo una ventana de 10 segundos tiene 10
    eventos y no 11.

    La alerta salta en la ventana en la que el drift cruza el umbral, no en todas las que siguen:
    mientras el drift dure, repetir el aviso en cada ventana sería ruido.

    El reloj entra por parámetro para que los tests fijen los tiempos y las métricas no dependan
    de cuánto tarde la máquina.
    """
    window: deque[tuple[float, CrimeReport, float, float]] = deque()
    scored = 0
    drifting = False
    for event in source:
        report = CrimeReport.model_validate(event)
        started = time.perf_counter()
        prediction = predict(bundle, [report])[0]
        latency_ms = (time.perf_counter() - started) * 1000

        now = clock()
        window.append((now, report, latency_ms, prediction.probability))
        while window and now - window[0][0] >= window_seconds:
            window.popleft()

        scored += 1
        if scored % report_every == 0:
            elapsed = window[-1][0] - window[0][0]
            drift = drift_indicator([item[1] for item in window], bundle["params"])
            crossed = drift > threshold and not drifting
            drifting = drift > threshold
            yield WindowReport(
                scored=scored,
                events=len(window),
                throughput=window_throughput(len(window), elapsed),
                p95_ms=p95([item[2] for item in window]),
                drift=drift,
                mean_probability=mean(item[3] for item in window),
                alert=crossed,
            )
