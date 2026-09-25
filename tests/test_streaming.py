"""Mini-TP 4: el flujo de eventos que se puntúa evento por evento."""

import threading
from collections.abc import Iterator
from statistics import mean
from typing import Any

import pytest
from pyproj import Transformer

from arrest_model.schemas import CrimeReport
from tp4_streaming.events import BASE_LATITUDE, BASE_LONGITUDE, crime_stream
from tp4_streaming.metrics import drift_indicator, p95, window_throughput
from tp4_streaming.sources import QueueSource


def test_the_same_seed_gives_the_same_stream() -> None:
    # El flujo tiene que ser reproducible: si no, ni los tests ni el notebook sirven de evidencia.
    assert list(crime_stream(20, seed=7)) == list(crime_stream(20, seed=7))


def test_another_seed_gives_another_stream() -> None:
    assert list(crime_stream(20, seed=7)) != list(crime_stream(20, seed=8))


def test_every_event_satisfies_the_contract() -> None:
    # Los eventos entran al mismo `CrimeReport` que valida la API REST: si el generador se
    # desviara del contrato, el flujo probaría algo que el servicio no acepta.
    for evento in crime_stream(50, seed=0):
        CrimeReport.model_validate(evento)


def test_the_drift_moves_the_reports_north() -> None:
    # A mitad del flujo los reportes se corren de zona. Eso es lo que después detecta el drift.
    eventos = list(crime_stream(40, seed=0, drift_from=20))
    antes = mean(evento["latitude"] for evento in eventos[:20])
    despues = mean(evento["latitude"] for evento in eventos[20:])
    assert despues > antes + 0.02


def test_without_drift_the_stream_keeps_its_distribution() -> None:
    eventos = list(crime_stream(40, seed=0))
    antes = mean(evento["latitude"] for evento in eventos[:20])
    despues = mean(evento["latitude"] for evento in eventos[20:])
    assert abs(despues - antes) < 0.02


def test_the_queue_source_delivers_every_event_in_order() -> None:
    eventos = list(crime_stream(30, seed=1))
    assert list(QueueSource(eventos)) == eventos


def test_the_queue_source_produces_on_another_thread() -> None:
    # El productor no puede correr en el hilo que consume: si lo hiciera, generar un evento
    # frenaría el scoring, y el flujo dejaría de ser un flujo.
    hilos: dict[str, int] = {}

    def eventos() -> Iterator[dict[str, Any]]:
        hilos["productor"] = threading.get_ident()
        yield from crime_stream(5, seed=1)

    for _ in QueueSource(eventos()):
        hilos["consumidor"] = threading.get_ident()
    assert hilos["productor"] != hilos["consumidor"]


def test_the_stream_starts_at_the_training_mean(bundle: dict[str, Any]) -> None:
    # El flujo normal tiene que salir de la zona donde el modelo vio la mayoría de los crímenes.
    # Si el modelo se reentrena con otros datos, esta comparación avisa que hay que recalcular.
    escala = bundle["params"]["scale"]
    longitud, latitud = Transformer.from_crs("EPSG:3435", "EPSG:4326", always_xy=True).transform(
        escala["x"][0], escala["y"][0]
    )
    assert (BASE_LATITUDE, BASE_LONGITUDE) == (pytest.approx(latitud), pytest.approx(longitud))


def test_the_throughput_counts_events_per_second() -> None:
    # Diez eventos repartidos en dos segundos son cinco por segundo.
    assert window_throughput(count=10, seconds=2.0) == pytest.approx(5.0)


def test_the_throughput_of_an_instant_window_is_zero() -> None:
    # Sin tiempo transcurrido no hay tasa que informar, y dividir por cero no es una opción.
    assert window_throughput(count=10, seconds=0.0) == 0.0


def test_the_p95_leaves_out_the_worst_five_percent() -> None:
    # Con 100 latencias de 1 a 100, el 95% no supera 95.
    assert p95([float(x) for x in range(1, 101)]) == pytest.approx(95.0, abs=1.0)


def test_the_p95_of_an_empty_window_is_zero() -> None:
    assert p95([]) == 0.0


def test_there_is_no_drift_when_the_reports_come_from_the_training_zone(
    bundle: dict[str, Any],
) -> None:
    # Las tres features estandarizadas tienen media 0 en entrenamiento: un flujo parecido a
    # aquellos datos tiene que dar un indicador chico.
    reportes = [CrimeReport.model_validate(e) for e in crime_stream(60, seed=3)]
    assert drift_indicator(reportes, bundle["params"]) < 0.5


def test_moving_the_reports_out_of_the_zone_raises_the_drift(bundle: dict[str, Any]) -> None:
    normales = [CrimeReport.model_validate(e) for e in crime_stream(60, seed=3)]
    corridos = [CrimeReport.model_validate(e) for e in crime_stream(60, seed=3, drift_from=0)]
    assert drift_indicator(corridos, bundle["params"]) > drift_indicator(normales, bundle["params"])
