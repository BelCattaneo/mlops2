"""El contrato de features del dataset de entrenamiento."""

import pandas as pd
import pytest
from etl_helpers.contract import enforce_feature_contract

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
