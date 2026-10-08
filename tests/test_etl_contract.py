"""El contrato de features del dataset de entrenamiento."""

import pandas as pd
import pytest
from etl_helpers.contract import (
    CURATED_FEATURES,
    CURATED_RENAMES,
    assert_no_missing,
    enforce_feature_contract,
    rename_to_model,
)

from arrest_model.features import MODEL_FEATURES

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
