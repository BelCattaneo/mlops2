"""Mini-TP 5: entrenamiento federado sobre la muestra de arrestos."""

from collections import Counter

import numpy as np

from arrest_model.features import MODEL_FEATURES
from tp5_federated.data import LABEL, load_sample, train_test
from tp5_federated.model import accuracy, initial_weights, probabilities, train


def test_the_sample_has_the_model_features_and_the_label() -> None:
    # La muestra alimenta un modelo distinto, pero las features son las mismas que sirve el repo.
    muestra = load_sample()
    assert list(muestra.columns) == [*MODEL_FEATURES, LABEL]
    assert not muestra.isna().any().any()
    assert len(muestra) >= 10_000


def test_both_classes_are_represented() -> None:
    proporciones = load_sample()[LABEL].value_counts(normalize=True)
    assert set(proporciones.index) == {0, 1}
    assert proporciones.min() > 0.3


def test_the_split_is_deterministic() -> None:
    primera = train_test()
    segunda = train_test()
    for antes, despues in zip(primera, segunda, strict=True):
        assert np.array_equal(antes, despues)


def test_the_split_keeps_the_class_balance() -> None:
    # Si el test quedara con otra proporción de arrestos, la accuracy no sería comparable.
    _, x_test, y_train, y_test = train_test()
    entrenamiento = Counter(y_train)[1] / len(y_train)
    evaluacion = Counter(y_test)[1] / len(y_test)
    assert abs(entrenamiento - evaluacion) < 0.02
    assert len(x_test) == len(y_test)


def test_the_trained_model_beats_always_saying_the_majority_class() -> None:
    # El piso de cualquier clasificador: decir siempre la clase más frecuente.
    x_train, x_test, y_train, y_test = train_test()
    mayoritaria = max(Counter(y_test).values()) / len(y_test)
    pesos = train(x_train, y_train)
    assert accuracy(pesos, x_test, y_test) > mayoritaria


def test_training_twice_gives_the_same_model() -> None:
    # Sin reproducibilidad no se puede comparar el federado contra el centralizado.
    x_train, _, y_train, _ = train_test()
    primero, segundo = train(x_train, y_train), train(x_train, y_train)
    assert np.array_equal(primero.w, segundo.w) and primero.b == segundo.b


def test_the_untrained_model_answers_the_same_thing_for_everyone() -> None:
    # Con los pesos en cero la probabilidad es 0.5 para toda fila: no distingue nada todavía.
    x_train, x_test, _, _ = train_test()
    vacio = initial_weights(x_train.shape[1])
    assert len(set(probabilities(vacio, x_test))) == 1


def test_the_features_arrive_standardized() -> None:
    # Sin estandarizar, las frecuencias y las coordenadas viven en escalas muy distintas y el
    # descenso de gradiente tarda muchísimo en converger.
    x_train, _, _, _ = train_test()
    assert np.allclose(x_train.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(x_train.std(axis=0), 1, atol=1e-9)
