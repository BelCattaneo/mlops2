"""Qué particiones crudas entran en la ventana de la capa intermedia."""

import datetime

from etl_helpers.partitions import partitions_in_window

CLAVES = [
    "raw/crimes/month=2025-09/crimes.csv",
    "raw/crimes/month=2025-10/crimes.csv",
    "raw/crimes/month=2026-09/crimes.csv",
    "raw/crimes/month=2026-10/crimes.csv",
]


def momento(texto: str) -> datetime.datetime:
    """Un instante en UTC, como los que trae el contexto de Airflow."""
    return datetime.datetime.fromisoformat(texto).replace(tzinfo=datetime.UTC)


def test_keeps_the_partitions_of_the_last_twelve_months() -> None:
    elegidas = partitions_in_window(CLAVES, momento("2026-10-03"), days=365)

    assert elegidas == [
        "raw/crimes/month=2025-10/crimes.csv",
        "raw/crimes/month=2026-09/crimes.csv",
        "raw/crimes/month=2026-10/crimes.csv",
    ]


def test_drops_the_partitions_older_than_the_window() -> None:
    elegidas = partitions_in_window(CLAVES, momento("2026-10-03"), days=365)

    assert "raw/crimes/month=2025-09/crimes.csv" not in elegidas


def test_comes_back_sorted_so_the_concatenation_is_deterministic() -> None:
    desordenadas = list(reversed(CLAVES))

    assert partitions_in_window(desordenadas, momento("2026-10-03"), days=365) == sorted(
        partitions_in_window(CLAVES, momento("2026-10-03"), days=365)
    )


def test_ignores_keys_without_a_month_partition() -> None:
    claves = [*CLAVES, "raw/crimes/suelto.csv", "raw/police_stations/police_stations.csv"]

    elegidas = partitions_in_window(claves, momento("2026-10-03"), days=365)

    assert all("month=" in clave for clave in elegidas)


def test_a_window_that_crosses_the_month_keeps_both_partitions() -> None:
    # La ventana arranca el 18 de septiembre, así que la partición de septiembre la toca:
    # dejarla afuera perdería los reportes del 18 al 30.
    elegidas = partitions_in_window(CLAVES, momento("2026-10-03"), days=15)

    assert elegidas == [
        "raw/crimes/month=2026-09/crimes.csv",
        "raw/crimes/month=2026-10/crimes.csv",
    ]


def test_a_window_inside_one_month_keeps_only_that_partition() -> None:
    elegidas = partitions_in_window(CLAVES, momento("2026-10-30"), days=15)

    assert elegidas == ["raw/crimes/month=2026-10/crimes.csv"]
