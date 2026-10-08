"""Entrenamiento del modelo sobre el dataset curado."""

import numpy as np
import pandas as pd
import pytest
from training_helpers import METRIC_NAMES, evaluate, fit_model

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
