"""Mini-TP 4: el flujo de eventos que se puntúa evento por evento."""

from statistics import mean

from arrest_model.schemas import CrimeReport
from tp4_streaming.events import crime_stream


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
