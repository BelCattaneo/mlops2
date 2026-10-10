"""Entrenamiento del modelo sobre el dataset curado."""

import numpy as np
import pandas as pd
import pytest
from training_helpers import METRIC_NAMES, choose_threshold, evaluate, fit_model

from arrest_model.features import MODEL_FEATURES


@pytest.fixture
def dataset() -> tuple[pd.DataFrame, pd.Series]:
    """Un dataset separable con las columnas del modelo, para que entrenar signifique algo."""
    generador = np.random.default_rng(7)
    filas = 400
    X = pd.DataFrame(
        {feature: generador.normal(size=filas) for feature in MODEL_FEATURES},
    )
    # La etiqueta depende de una sola feature: un modelo que aprende tiene que superar al azar.
    y = pd.Series((X[MODEL_FEATURES[0]] > 0).astype(int), name="arrest")
    return X, y


def test_the_fitted_model_learns_the_signal(dataset: tuple[pd.DataFrame, pd.Series]) -> None:
    X, y = dataset

    modelo = fit_model(X, y)

    assert (modelo.predict(X) == y).mean() > 0.9


def test_the_model_keeps_the_feature_names_so_serving_can_check_them(
    dataset: tuple[pd.DataFrame, pd.Series],
) -> None:
    X, y = dataset

    modelo = fit_model(X, y)

    assert modelo.get_booster().feature_names == list(MODEL_FEATURES)


def test_evaluate_returns_the_six_metrics_of_the_bundle(
    dataset: tuple[pd.DataFrame, pd.Series],
) -> None:
    X, y = dataset
    modelo = fit_model(X, y)

    metricas = evaluate(modelo, X, y)

    assert sorted(metricas) == sorted(METRIC_NAMES)
    assert all(isinstance(valor, float) for valor in metricas.values())


def test_recall_equals_accuracy_because_the_average_is_weighted(
    dataset: tuple[pd.DataFrame, pd.Series],
) -> None:
    # Es la convención del modelo entregado, y la que hace comparables los números: con promedio
    # ponderado el recall coincide con la accuracy.
    X, y = dataset
    metricas = evaluate(fit_model(X, y), X, y)

    assert metricas["recall"] == pytest.approx(metricas["accuracy"])


def test_a_model_trained_on_noise_does_not_generalize() -> None:
    # Medido sobre datos que el modelo no vio: entrenando sobre ruido memoriza su conjunto, así
    # que la prueba de que `evaluate` discrimina es evaluarlo contra otra muestra.
    generador = np.random.default_rng(3)

    def ruido(filas: int) -> tuple[pd.DataFrame, pd.Series]:
        """Features y etiqueta sin ninguna relación entre sí."""
        X = pd.DataFrame({f: generador.normal(size=filas) for f in MODEL_FEATURES})
        return X, pd.Series(generador.integers(0, 2, size=filas), name="arrest")

    X_entrena, y_entrena = ruido(300)
    X_prueba, y_prueba = ruido(300)

    metricas = evaluate(fit_model(X_entrena, y_entrena), X_prueba, y_prueba)

    assert abs(metricas["mcc"]) < 0.2
    assert 0.3 < metricas["auc"] < 0.7


@pytest.fixture
def desbalanceado() -> tuple[pd.DataFrame, pd.Series]:
    """Un dataset separable con 15% de positivos, como la ventana real del lake."""
    generador = np.random.default_rng(11)
    filas = 2000
    X = pd.DataFrame({feature: generador.normal(size=filas) for feature in MODEL_FEATURES})
    # El positivo es la cola de una sola feature: separable, pero minoritario.
    y = pd.Series((X[MODEL_FEATURES[0]] > 1.04).astype(int), name="arrest")
    return X, y


def test_the_fitted_model_weighs_the_minority_class(
    desbalanceado: tuple[pd.DataFrame, pd.Series],
) -> None:
    # Es lo que XGBoost ofrece para el desbalance, en lugar de sintetizar filas: medido sobre la
    # ventana entera, pesar la clase da mejor AUC (0,8868 contra 0,8835) y mejor MCC en su propio
    # umbral (0,5818 contra 0,5745) que SMOTE más submuestreo.
    X, y = desbalanceado

    modelo = fit_model(X, y)

    esperado = (y == 0).sum() / (y == 1).sum()
    assert modelo.get_params()["scale_pos_weight"] == pytest.approx(esperado)


def test_the_chosen_threshold_is_at_least_as_good_as_a_half(
    desbalanceado: tuple[pd.DataFrame, pd.Series],
) -> None:
    # El umbral se elige midiendo, no se asume: pesar la clase infla las probabilidades que el
    # modelo emite, así que el corte que maximiza el MCC se corre y 0,5 deja de ser el mejor.
    X, y = desbalanceado
    modelo = fit_model(X, y)

    umbral = choose_threshold(modelo, X, y)

    assert 0.0 < umbral < 1.0
    propio = evaluate(modelo, X, y, threshold=umbral)
    en_la_mitad = evaluate(modelo, X, y, threshold=0.5)
    assert propio["mcc"] >= en_la_mitad["mcc"]


def test_evaluating_with_a_threshold_of_zero_calls_everything_positive(
    desbalanceado: tuple[pd.DataFrame, pd.Series],
) -> None:
    # Fija que el umbral que se le pasa es el que decide, y no el 0.5 de `predict`.
    X, y = desbalanceado
    modelo = fit_model(X, y)

    metricas = evaluate(modelo, X, y, threshold=0.0)

    assert metricas["accuracy"] == pytest.approx(float(y.mean()))
