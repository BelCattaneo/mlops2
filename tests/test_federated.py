"""Mini-TP 5: entrenamiento federado sobre la muestra de arrestos."""

from collections import Counter

import numpy as np

from arrest_model.features import MODEL_FEATURES
from tp5_federated.data import LABEL, load_sample, train_test


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
