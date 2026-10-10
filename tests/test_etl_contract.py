"""El contrato de features del dataset de entrenamiento."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from etl_helpers.contract import (
    CURATED_FEATURES,
    CURATED_RENAMES,
    assert_no_missing,
    enforce_feature_contract,
    rename_to_model,
)
from etl_helpers.data_enrichment import enrich_crime_data
from etl_helpers.params import project_stations

from arrest_model.features import (
    MODEL_FEATURES,
    distance_to_station_standardized,
    with_projections,
)

FEATURES = ("a_freq", "b_freq", "c_sin")
ETIQUETA = "arrest"


def frame(columnas: list[str]) -> pd.DataFrame:
    """Un dataframe de dos filas con las columnas pedidas."""
    return pd.DataFrame({columna: [1.0, 2.0] for columna in columnas})


def test_leaves_the_features_in_the_declared_order_with_the_label_last() -> None:
    desordenado = frame(["c_sin", ETIQUETA, "a_freq", "b_freq"])

    ordenado = enforce_feature_contract(desordenado, FEATURES, ETIQUETA)

    assert list(ordenado.columns) == ["a_freq", "b_freq", "c_sin", ETIQUETA]


def test_keeps_the_values_untouched() -> None:
    original = frame([*FEATURES, ETIQUETA])

    resultado = enforce_feature_contract(original, FEATURES, ETIQUETA)

    pd.testing.assert_frame_equal(resultado, original[[*FEATURES, ETIQUETA]])


def test_fails_naming_the_feature_that_is_missing() -> None:
    # Si la selección por información mutua deja de elegir una feature, el modelo que sirve la
    # plataforma deja de corresponder al dataset que la plataforma produce.
    with pytest.raises(ValueError, match="b_freq"):
        enforce_feature_contract(frame(["a_freq", "c_sin", ETIQUETA]), FEATURES, ETIQUETA)


def test_fails_naming_the_feature_that_is_extra() -> None:
    with pytest.raises(ValueError, match="d_freq"):
        enforce_feature_contract(frame([*FEATURES, "d_freq", ETIQUETA]), FEATURES, ETIQUETA)


def test_fails_when_the_label_is_missing() -> None:
    with pytest.raises(ValueError, match=ETIQUETA):
        enforce_feature_contract(frame(list(FEATURES)), FEATURES, ETIQUETA)


def test_the_message_says_what_is_missing_and_what_is_extra() -> None:
    con_las_dos_cosas = frame(["a_freq", "b_freq", "d_freq", ETIQUETA])

    with pytest.raises(ValueError) as error:
        enforce_feature_contract(con_las_dos_cosas, FEATURES, ETIQUETA)

    assert "c_sin" in str(error.value)
    assert "d_freq" in str(error.value)


def test_a_clean_dataset_passes_untouched() -> None:
    limpio = frame([*FEATURES, ETIQUETA])

    pd.testing.assert_frame_equal(assert_no_missing(limpio, "curado"), limpio)


def test_fails_naming_the_column_with_nulls_and_how_many() -> None:
    con_nulos = frame([*FEATURES, ETIQUETA])
    con_nulos.loc[0, "b_freq"] = None

    with pytest.raises(ValueError, match=r"nulos en b_freq \(1\)"):
        assert_no_missing(con_nulos, "curado")


def test_fails_on_infinities_too() -> None:
    # Una división por cero aguas arriba no deja nulos sino infinitos, y rompe el entrenamiento
    # igual que un nulo.
    con_infinitos = frame([*FEATURES, ETIQUETA])
    con_infinitos.loc[1, "c_sin"] = float("inf")

    with pytest.raises(ValueError, match="infinitos en c_sin"):
        assert_no_missing(con_infinitos, "curado")


def test_the_mapping_lands_exactly_on_the_model_features() -> None:
    # Este es el test que impide que las dos cosas se separen: si alguien agrega una feature al
    # modelo y no al mapeo del ETL, o al revés, falla acá y no en producción.
    assert list(CURATED_RENAMES.values()) == list(MODEL_FEATURES)


def test_renames_the_etl_columns_to_the_model_names() -> None:
    del_etl = frame([*CURATED_RENAMES, ETIQUETA])

    renombrado = rename_to_model(del_etl)

    assert list(renombrado.columns) == [*MODEL_FEATURES, ETIQUETA]


def test_leaves_the_label_and_anything_unmapped_untouched() -> None:
    # Una columna que el ETL produzca y el mapeo no conozca tiene que sobrevivir con su nombre,
    # para que el contrato la vea y falle diciendo que sobra.
    con_extra = frame([*CURATED_RENAMES, "fbi_code_freq", ETIQUETA])

    renombrado = rename_to_model(con_extra)

    assert "fbi_code_freq" in renombrado.columns
    assert ETIQUETA in renombrado.columns


def test_the_renamed_frame_passes_the_contract() -> None:
    del_etl = frame([*CURATED_RENAMES, ETIQUETA])

    verificado = enforce_feature_contract(rename_to_model(del_etl), CURATED_FEATURES, ETIQUETA)

    assert list(verificado.columns) == [*MODEL_FEATURES, ETIQUETA]


def test_the_etl_measures_the_distance_where_the_model_measures_it() -> None:
    """La distancia a la comisaría tiene que salir del ETL en el mismo CRS en el que la mide el
    codificador que sirve.

    El modelo recibe esa distancia estandarizada con la media y el desvío que ajustó el ETL. Si
    el ETL la mide en otra unidad, el modelo entrena con una escala y predice con otra, y el
    desajuste no lo avisa nadie: la correlación entre las dos es 1,00000000 porque difieren en un
    factor constante, y después del log1p ese factor se vuelve un corrimiento. Medido con el ETL
    midiendo en pies y el codificador en metros: 1,65 desvíos de corrimiento.
    """
    datos = Path(__file__).parent / "data"
    crimenes = pd.read_csv(datos / "sample_crimes.csv")
    comisarias = pd.read_csv(datos / "sample_stations.csv").dropna(subset=["latitude", "longitude"])
    # El enriquecimiento mide desde x/y y el codificador desde lat/lon, así que para comparar las
    # dos mitades hay que partir del mismo punto. En los datos del portal las dos coordenadas
    # corresponden —medido sobre 4.993 filas, 1e-9 desvíos de diferencia—, pero estos fixtures
    # son sintéticos y su x/y está a 2.500 pies de su lat/lon.
    for marco in (crimenes, comisarias):
        proyectado = with_projections(marco)
        marco["x_coordinate"] = proyectado["x_feet"]
        marco["y_coordinate"] = proyectado["y_feet"]

    enriquecido = enrich_crime_data(crimenes.copy(), comisarias.copy())
    # El codificador de verdad, con escalado identidad: así devuelve el log1p de la distancia
    # cruda en el CRS en el que el modelo la mide, sin que el test lo recalcule por su cuenta.
    identidad = {
        "freq": {},
        "scale": {"log_distance": (0.0, 1.0)},
        "stations": project_stations(comisarias),
    }
    del_codificador = np.expm1(
        distance_to_station_standardized(with_projections(crimenes), identidad)
    )

    assert len(enriquecido) == len(crimenes)  # si no, comparar por posición no valdría
    assert np.allclose(enriquecido["distance_crime_to_police_station"], del_codificador, rtol=1e-6)
