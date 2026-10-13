"""Cuánto se movieron los datos respecto de los que vio el champion."""

import pytest
from drift import drift_metrics

CHAMPION = {
    "freq": {
        "iucr": {"0820": 0.30, "1310": 0.70},
        "primary_type": {"THEFT": 0.40, "BATTERY": 0.60},
        "location_description": {"STREET": 0.50, "APARTMENT": 0.50},
    },
    "scale": {"x": (1165275.0, 16000.0), "y": (1887516.0, 32000.0), "log_distance": (7.40, 0.67)},
}


def mover(params: dict, clave: str, delta: float) -> dict:
    """Los mismos parámetros con la media de una feature escalada corrida."""
    media, desvio = params["scale"][clave]
    return {**params, "scale": {**params["scale"], clave: (media + delta, desvio)}}


def test_without_movement_every_metric_is_zero() -> None:
    metricas = drift_metrics(CHAMPION, CHAMPION)

    assert metricas["drift_max_sigma"] == 0.0
    assert metricas["drift_freq_max"] == 0.0
    assert metricas["drift_freq_new_categories"] == 0.0


def test_the_shift_is_measured_in_standard_deviations_of_the_champion() -> None:
    # Medir en desvíos y no en unidades es lo que hace comparables features con escalas
    # distintas, y lo que permite leer el número contra lo ya medido: el bug del CRS movía una
    # feature 1,69 desvíos.
    corrido = mover(CHAMPION, "log_distance", 0.67)

    metricas = drift_metrics(CHAMPION, corrido)

    assert metricas["drift_scale_log_distance"] == pytest.approx(1.0)
    assert metricas["drift_max_sigma"] == pytest.approx(1.0)


def test_the_largest_shift_is_the_one_reported() -> None:
    corrido = mover(mover(CHAMPION, "x", 8000.0), "log_distance", 0.335)

    metricas = drift_metrics(CHAMPION, corrido)

    assert metricas["drift_scale_x"] == pytest.approx(0.5)
    assert metricas["drift_scale_log_distance"] == pytest.approx(0.5)
    assert metricas["drift_max_sigma"] == pytest.approx(0.5)


def test_a_frequency_that_moves_is_reported() -> None:
    nuevo = {**CHAMPION, "freq": {**CHAMPION["freq"], "iucr": {"0820": 0.35, "1310": 0.65}}}

    metricas = drift_metrics(CHAMPION, nuevo)

    assert metricas["drift_freq_max"] == pytest.approx(0.05)


def test_a_category_that_did_not_exist_before_is_counted() -> None:
    # Una categoría nueva entra al modelo con frecuencia 0 por el camino de servicio: conviene
    # saber cuántas aparecieron sin que el número se pierda entre las que solo se movieron.
    nuevo = {**CHAMPION, "freq": {**CHAMPION["freq"], "primary_type": {"THEFT": 0.4, "ARSON": 0.6}}}

    metricas = drift_metrics(CHAMPION, nuevo)

    assert metricas["drift_freq_new_categories"] == 1.0


def test_without_a_champion_there_is_nothing_to_compare() -> None:
    # La primera corrida no tiene contra qué medirse y eso no es un error.
    assert drift_metrics(None, CHAMPION) == {}
