"""Qué particiones crudas entran en la ventana de la capa intermedia."""

import datetime

from etl_helpers.partitions import download_window, partition_date, partitions_in_window

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


def test_the_window_is_the_run_interval_when_there_is_one() -> None:
    inicio, fin = download_window(
        momento("2026-10-01"), momento("2026-11-01"), now=momento("2026-10-03T15:00:00")
    )

    assert (inicio, fin) == (momento("2026-10-01"), momento("2026-11-01"))


def test_without_an_interval_the_window_is_the_current_month() -> None:
    # Un trigger manual sin fecha lógica deja el intervalo en None, y antes de esto la tarea
    # se caía con AttributeError en su cuarta línea.
    inicio, fin = download_window(None, None, now=momento("2026-10-03T15:00:00"))

    assert inicio == momento("2026-10-01T00:00:00")
    assert fin == momento("2026-10-03T15:00:00")


def test_a_half_missing_interval_also_falls_back() -> None:
    inicio, fin = download_window(momento("2026-10-01"), None, now=momento("2026-10-03T15:00:00"))

    assert inicio == momento("2026-10-01T00:00:00")
    assert fin == momento("2026-10-03T15:00:00")


def test_the_partition_is_valid_either_way() -> None:
    con_intervalo, _ = download_window(
        momento("2026-10-01"), momento("2026-11-01"), now=momento("2026-10-03")
    )
    sin_intervalo, _ = download_window(None, None, now=momento("2026-10-03"))

    assert con_intervalo.strftime("%Y-%m") == "2026-10"
    assert sin_intervalo.strftime("%Y-%m") == "2026-10"


def test_the_window_keeps_the_timezone_so_it_can_be_compared() -> None:
    inicio, fin = download_window(None, None, now=momento("2026-10-03T15:00:00"))

    assert inicio.tzinfo is not None
    assert fin.tzinfo is not None


def test_the_key_suffix_is_the_logical_date_when_there_is_one() -> None:
    assert partition_date("2026-10-02", momento("2026-10-03T15:00:00")) == "2026-10-02"


def test_without_a_logical_date_the_suffix_is_the_end_of_the_window() -> None:
    # Sin fecha lógica no hay `ds`, y las claves derivadas lo usan de sufijo.
    assert partition_date(None, momento("2026-10-03T15:00:00")) == "2026-10-03"
