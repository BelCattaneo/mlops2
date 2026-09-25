"""Mini-TP 4: el flujo de eventos que se puntúa evento por evento."""

import itertools
import socket
import threading
import uuid
from collections.abc import Callable, Iterator
from statistics import mean
from typing import Any

import pytest
from pyproj import Transformer

from arrest_model.schemas import CrimeReport
from tp4_streaming.compare import compare, format_comparison, score_online
from tp4_streaming.consumer import DRIFT_THRESHOLD, score_stream
from tp4_streaming.events import BASE_LATITUDE, BASE_LONGITUDE, crime_stream
from tp4_streaming.metrics import drift_indicator, p95, window_throughput
from tp4_streaming.run import run_stream
from tp4_streaming.sources import KafkaSource, QueueSource, publish


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


def reloj_de_un_segundo() -> Callable[[], float]:
    """Reloj falso que avanza un segundo por lectura, para fijar las ventanas en los tests."""
    tiempos = itertools.count(0.0)
    return lambda: next(tiempos)


def test_every_event_of_the_stream_gets_scored(bundle: dict[str, Any]) -> None:
    ventanas = list(
        score_stream(
            crime_stream(100, seed=2), bundle, report_every=50, clock=reloj_de_un_segundo()
        )
    )
    assert [v.scored for v in ventanas] == [50, 100]


def test_the_window_drops_what_is_older_than_its_length(bundle: dict[str, Any]) -> None:
    # Con un evento por segundo y una ventana de 10, adentro quedan los últimos 10 eventos.
    ventanas = list(
        score_stream(
            crime_stream(60, seed=2),
            bundle,
            window_seconds=10.0,
            report_every=30,
            clock=reloj_de_un_segundo(),
        )
    )
    assert [v.events for v in ventanas] == [10, 10]


def test_the_window_reports_throughput_p95_and_drift(bundle: dict[str, Any]) -> None:
    # Un evento por segundo es un evento por segundo de throughput.
    ventana = next(
        iter(
            score_stream(
                crime_stream(40, seed=2),
                bundle,
                window_seconds=5.0,
                report_every=20,
                clock=reloj_de_un_segundo(),
            )
        )
    )
    assert ventana.throughput == pytest.approx(1.0, abs=0.3)
    assert ventana.p95_ms > 0
    assert 0.0 <= ventana.mean_probability <= 1.0
    assert ventana.drift < 0.5


def ventanas_de(bundle: dict[str, Any], **kwargs: Any) -> list[Any]:
    """Corre 200 eventos con el reloj falso y devuelve las ventanas informadas."""
    return list(
        score_stream(
            crime_stream(200, seed=4, **kwargs),
            bundle,
            report_every=50,
            clock=reloj_de_un_segundo(),
        )
    )


def test_a_stable_stream_raises_no_alert(bundle: dict[str, Any]) -> None:
    assert [v.alert for v in ventanas_de(bundle)] == [False, False, False, False]


def test_the_alert_fires_when_the_drift_crosses_the_threshold(bundle: dict[str, Any]) -> None:
    ventanas = ventanas_de(bundle, drift_from=100)
    alertadas = [v for v in ventanas if v.alert]
    assert alertadas and alertadas[0].drift > DRIFT_THRESHOLD


def test_the_alert_does_not_repeat_while_the_drift_lasts(bundle: dict[str, Any]) -> None:
    # Avisar una vez por ventana mientras el drift dure sería ruido: se avisa al cruzar.
    ventanas = ventanas_de(bundle, drift_from=100)
    assert sum(v.alert for v in ventanas) == 1
    assert ventanas[-1].drift > DRIFT_THRESHOLD and ventanas[-1].alert is False


def test_the_command_scores_the_stream_and_reports_each_window(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_stream(events=100, report_every=50, drift_from=None) == 0
    salida = capsys.readouterr().out
    assert len(salida.strip().splitlines()) == 2
    assert "throughput" in salida and "p95" in salida and "drift" in salida


def test_the_command_marks_the_window_that_alerts(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_stream(events=200, report_every=50, drift_from=100) == 0
    assert "ALERTA" in capsys.readouterr().out


def test_online_and_batch_agree_on_every_prediction(bundle: dict[str, Any]) -> None:
    # El invariante del TP: puntuar de a uno o de a mil tiene que dar exactamente lo mismo.
    # Si difieren, el camino online ordenó mal las features, perdió un evento o codificó distinto.
    comparacion = compare(list(crime_stream(200, seed=6)), bundle)
    assert comparacion.same_predictions
    assert comparacion.events == 200


def test_the_comparison_reports_the_time_of_each_path(bundle: dict[str, Any]) -> None:
    comparacion = compare(list(crime_stream(50, seed=6)), bundle)
    assert comparacion.online_seconds > 0 and comparacion.batch_seconds > 0
    tabla = format_comparison(comparacion)
    assert "| online |" in tabla and "| batch |" in tabla


def topic_nuevo(nombre: str) -> str:
    """Un topic distinto por corrida: el consumidor lee desde el principio, así que reusar el
    mismo topic haría que una corrida encontrara también los eventos de la anterior."""
    return f"tp4-test-{nombre}-{uuid.uuid4().hex[:8]}"


def _broker_escuchando() -> bool:
    """Dice si hay algo aceptando conexiones en el puerto de Kafka."""
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", 9092)) == 0


@pytest.mark.kafka
@pytest.mark.skipif(not _broker_escuchando(), reason="no hay broker escuchando en 9092")
def test_the_broker_delivers_the_same_events_that_were_published() -> None:
    topic = topic_nuevo("eventos")
    eventos = list(crime_stream(30, seed=9))
    publish(eventos, topic=topic)
    assert list(KafkaSource(topic=topic, timeout_ms=5000)) == eventos


@pytest.mark.kafka
@pytest.mark.skipif(not _broker_escuchando(), reason="no hay broker escuchando en 9092")
def test_the_stream_scores_the_same_from_the_queue_and_from_the_broker(
    bundle: dict[str, Any],
) -> None:
    # La fuente no puede cambiar el resultado: el consumidor no sabe de dónde vienen los eventos.
    topic = topic_nuevo("scoring")
    eventos = list(crime_stream(60, seed=9))
    publish(eventos, topic=topic)
    desde_cola = score_online(eventos, bundle)
    desde_broker = score_online(list(KafkaSource(topic=topic, timeout_ms=5000)), bundle)
    assert desde_broker == desde_cola
