"""Los parámetros de preprocesamiento que el ETL ajusta y exporta."""

import json

import numpy as np
import pandas as pd
import pytest
from etl_helpers.params import (
    SCALE_KEYS,
    build_params,
    dump_params,
    load_params,
    project_stations,
)

from arrest_model.features import encode_frame

FRECUENCIAS = {
    "iucr": pd.Series({"0820": 0.3, "1310": 0.7}),
    "primary_type": pd.Series({"THEFT": 0.4, "BATTERY": 0.6}),
    "location_description": pd.Series({"STREET": 0.5, "APARTMENT": 0.5}),
    "fbi_code": pd.Series({"06": 1.0}),
}
ESCALA = {
    "x_coordinate": (1165275.0, 16217.0),
    "y_coordinate": (1887516.0, 31618.0),
    "distance_crime_to_police_station": (7.45, 0.6),
}
COMISARIAS = pd.DataFrame(
    {"latitude": [41.85, 41.90], "longitude": [-87.65, -87.70]},
)


def test_the_params_have_the_three_keys_the_encoder_reads() -> None:
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)

    assert sorted(params) == ["freq", "scale", "stations"]


def test_only_the_three_frequency_maps_of_the_model_travel() -> None:
    # El ETL codifica diez columnas por frecuencia y el modelo usa tres: las otras siete no
    # tienen por qué viajar con el artefacto.
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)

    assert sorted(params["freq"]) == ["iucr", "location_description", "primary_type"]


def test_the_frequency_maps_keep_their_values() -> None:
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)

    assert params["freq"]["iucr"]["1310"] == pytest.approx(0.7)


def test_the_scale_keys_are_renamed_to_what_the_encoder_expects() -> None:
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)

    assert sorted(params["scale"]) == sorted(SCALE_KEYS.values())
    assert params["scale"]["log_distance"] == (7.45, 0.6)


def test_the_stations_come_projected_as_a_pair_per_station() -> None:
    proyectadas = project_stations(COMISARIAS)

    assert proyectadas.shape == (2, 2)
    assert proyectadas.dtype == np.float64


def test_a_missing_scale_column_fails_instead_of_encoding_with_a_hole() -> None:
    incompleta = {k: v for k, v in ESCALA.items() if k != "y_coordinate"}

    with pytest.raises(ValueError, match="y_coordinate"):
        build_params(FRECUENCIAS, incompleta, COMISARIAS)


def test_the_params_work_with_the_encoder_of_the_shared_package() -> None:
    # La prueba que importa: que lo que el ETL exporta se le pueda pasar a la codificación que
    # usan los cuatro protocolos para servir.
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)
    reporte = pd.DataFrame(
        {
            "iucr": ["1310"],
            "primary_type": ["THEFT"],
            "location_description": ["STREET"],
            "day_num": [1],
            "latitude": [41.77],
            "longitude": [-87.59],
        }
    )

    features = encode_frame(reporte, params)

    assert len(features) == 1
    assert features.notna().all().all()


def test_the_dump_is_plain_json_so_anyone_can_read_it() -> None:
    # Los parámetros son datos planos. Guardarlos como pickle ataría al lector a las librerías
    # del escritor: medido, el pickle que escribía el contenedor arrastraba una referencia a
    # `dill`, que no está ni en el venv ni en las imágenes de las APIs.
    crudo = dump_params(build_params(FRECUENCIAS, ESCALA, COMISARIAS))

    recuperado = json.loads(crudo.decode("utf-8"))

    assert sorted(recuperado) == ["freq", "scale", "stations"]


def test_the_round_trip_keeps_the_values() -> None:
    params = build_params(FRECUENCIAS, ESCALA, COMISARIAS)

    vuelta = load_params(dump_params(params))

    assert vuelta["freq"] == params["freq"]
    assert vuelta["scale"] == params["scale"]
    assert np.allclose(vuelta["stations"], params["stations"])


def test_the_stations_come_back_as_an_array_because_the_encoder_indexes_them() -> None:
    vuelta = load_params(dump_params(build_params(FRECUENCIAS, ESCALA, COMISARIAS)))

    assert isinstance(vuelta["stations"], np.ndarray)
    assert vuelta["stations"].shape == (2, 2)


def test_the_round_tripped_params_still_encode() -> None:
    vuelta = load_params(dump_params(build_params(FRECUENCIAS, ESCALA, COMISARIAS)))
    reporte = pd.DataFrame(
        {
            "iucr": ["1310"],
            "primary_type": ["THEFT"],
            "location_description": ["STREET"],
            "day_num": [1],
            "latitude": [41.77],
            "longitude": [-87.59],
        }
    )

    assert encode_frame(reporte, vuelta).notna().all().all()
