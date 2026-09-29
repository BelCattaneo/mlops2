"""Mini-TP 5: entrenamiento federado sobre la muestra de arrestos."""

from collections import Counter

import numpy as np
import pytest

from arrest_model.features import MODEL_FEATURES
from tp5_federated.data import LABEL, load_sample, train_test
from tp5_federated.federated import Update, aggregate, local_update, run_rounds
from tp5_federated.model import Weights, accuracy, initial_weights, probabilities, train
from tp5_federated.partitions import by_zone, iid
from tp5_federated.privacy import noisy_aggregate
from tp5_federated.run import compare, format_results, run_comparison


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


def test_the_iid_split_uses_every_row_once() -> None:
    x_train, _, y_train, _ = train_test()
    clientes = iid(x_train, y_train, clients=5)
    assert len(clientes) == 5
    assert sum(len(c.y) for c in clientes) == len(y_train)
    assert np.array_equal(np.sort(np.concatenate([c.y for c in clientes])), np.sort(y_train))


def test_the_iid_split_gives_every_client_the_same_mix() -> None:
    # Con reparto al azar, cada cliente ve una muestra parecida al total.
    x_train, _, y_train, _ = train_test()
    global_ = y_train.mean()
    tasas = [c.y.mean() for c in iid(x_train, y_train, clients=5)]
    assert max(abs(tasa - global_) for tasa in tasas) < 0.03


def test_the_zone_split_gives_each_client_its_own_area() -> None:
    # Cada cliente es una franja de la ciudad: sus coordenadas no se superponen con las del resto.
    x_train, _, y_train, _ = train_test()
    norte = MODEL_FEATURES.index("Y Coordinate_standardized")
    clientes = by_zone(x_train, y_train, clients=5)
    medias = [c.x[:, norte].mean() for c in clientes]
    assert medias == sorted(medias)
    assert medias[-1] - medias[0] > 1.0


def test_the_zone_split_also_uses_every_row_once() -> None:
    x_train, _, y_train, _ = train_test()
    clientes = by_zone(x_train, y_train, clients=5)
    assert sum(len(c.y) for c in clientes) == len(y_train)
    assert min(len(c.y) for c in clientes) > 100


def test_the_average_weighs_each_client_by_its_data() -> None:
    # El corazón de FedAvg: un cliente con el triple de datos pesa el triple.
    chico = Update(Weights(np.array([0.0, 0.0]), 0.0), samples=1)
    grande = Update(Weights(np.array([4.0, 8.0]), 4.0), samples=3)
    promedio = aggregate([chico, grande])
    assert np.allclose(promedio.w, [3.0, 6.0])
    assert promedio.b == pytest.approx(3.0)


def test_averaging_a_single_client_returns_its_own_model() -> None:
    solo = Update(Weights(np.array([1.5, -2.0]), 0.5), samples=10)
    promedio = aggregate([solo])
    assert np.allclose(promedio.w, solo.weights.w) and promedio.b == solo.weights.b


def test_the_local_training_starts_from_the_global_model() -> None:
    # Cada cliente parte del modelo global de la ronda, no de cero: eso es lo que acumula avance.
    x_train, _, y_train, _ = train_test()
    cliente = iid(x_train, y_train, clients=5)[0]
    global_ = train(x_train, y_train, epochs=5)
    desde_global = local_update(global_, cliente, epochs=0)
    assert np.array_equal(desde_global.weights.w, global_.w)
    assert desde_global.samples == len(cliente.y)


def test_the_history_has_one_accuracy_per_round() -> None:
    x_train, x_test, y_train, y_test = train_test()
    historia = run_rounds(iid(x_train, y_train), x_test, y_test, rounds=4)
    assert len(historia) == 4
    assert all(0.0 <= accuracy <= 1.0 for accuracy in historia)


def test_the_federated_model_learns_along_the_rounds() -> None:
    x_train, x_test, y_train, y_test = train_test()
    historia = run_rounds(iid(x_train, y_train), x_test, y_test, rounds=10)
    assert historia[-1] > historia[0]


def test_with_iid_clients_it_gets_close_to_the_centralized_model() -> None:
    # Repartir al azar es el caso fácil: el federado tiene que quedar cerca del centralizado.
    x_train, x_test, y_train, y_test = train_test()
    centralizado = accuracy(train(x_train, y_train), x_test, y_test)
    federado = run_rounds(iid(x_train, y_train), x_test, y_test, rounds=20)[-1]
    assert centralizado - federado < 0.03


def test_the_rounds_are_reproducible() -> None:
    x_train, x_test, y_train, y_test = train_test()
    clientes = iid(x_train, y_train)
    assert run_rounds(clientes, x_test, y_test, rounds=5) == run_rounds(
        clientes, x_test, y_test, rounds=5
    )


def test_without_noise_the_aggregation_is_the_plain_average() -> None:
    updates = [
        Update(Weights(np.array([1.0, 2.0]), 0.5), samples=10),
        Update(Weights(np.array([3.0, 4.0]), 1.5), samples=30),
    ]
    con_ruido = noisy_aggregate(sigma=0.0)(updates)
    sin_ruido = aggregate(updates)
    assert np.array_equal(con_ruido.w, sin_ruido.w) and con_ruido.b == sin_ruido.b


def test_the_noise_moves_the_aggregated_weights() -> None:
    updates = [Update(Weights(np.array([1.0, 2.0]), 0.5), samples=10)]
    assert not np.allclose(noisy_aggregate(sigma=0.5, seed=1)(updates).w, aggregate(updates).w)


def test_the_same_seed_gives_the_same_noise() -> None:
    updates = [Update(Weights(np.array([1.0, 2.0]), 0.5), samples=10)]
    assert np.array_equal(
        noisy_aggregate(sigma=0.5, seed=7)(updates).w, noisy_aggregate(sigma=0.5, seed=7)(updates).w
    )


def test_more_noise_costs_accuracy() -> None:
    # El trade-off que pide analizar la consigna: más privacidad, menos accuracy.
    x_train, x_test, y_train, y_test = train_test()
    clientes = iid(x_train, y_train)
    sin_ruido = run_rounds(clientes, x_test, y_test, rounds=10)[-1]
    con_ruido = run_rounds(
        clientes, x_test, y_test, rounds=10, aggregator=noisy_aggregate(sigma=0.5, seed=3)
    )[-1]
    assert con_ruido < sin_ruido


def test_the_comparison_covers_the_three_variants() -> None:
    resultados = compare(rounds=3, clients=4)
    assert len(resultados.iid) == len(resultados.zone) == 3
    assert 0.5 < resultados.central < 1.0


def test_the_table_shows_the_three_variants_and_the_privacy_cost() -> None:
    tabla = format_results(compare(rounds=2, clients=4), {0.0: 0.64, 0.5: 0.61})
    assert "| centralizado |" in tabla
    assert "| federado IID |" in tabla
    assert "| federado por zona |" in tabla
    assert "| 0.5 |" in tabla


def test_the_command_prints_the_tables(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_comparison(rounds=2, clients=4, sigmas=(0.0, 0.5)) == 0
    salida = capsys.readouterr().out
    assert "centralizado" in salida and "sigma" in salida
