"""Mini-TP 5: corre las tres variantes y muestra qué cuesta federar.

Uso: `uv run python -m tp5_federated.run [--rounds N] [--clients K]`, o `make fed-run`.
"""

import argparse
from typing import NamedTuple

from tp5_federated.data import train_test
from tp5_federated.federated import ROUNDS, run_rounds
from tp5_federated.model import accuracy, train
from tp5_federated.partitions import CLIENTS, by_zone, iid
from tp5_federated.privacy import noisy_aggregate

SIGMAS = (0.0, 0.05, 0.1, 0.2, 0.5)


class Results(NamedTuple):
    """Las tres variantes que compara la consigna."""

    central: float  # el modelo entrenado con todos los datos juntos
    iid: list[float]  # accuracy por ronda, con los datos repartidos al azar
    zone: list[float]  # accuracy por ronda, con cada cliente en su zona de la ciudad


def compare(rounds: int = ROUNDS, clients: int = CLIENTS, seed: int = 0) -> Results:
    """Entrena el modelo centralizado y las dos variantes federadas sobre el mismo corte."""
    x_train, x_test, y_train, y_test = train_test()
    return Results(
        central=accuracy(train(x_train, y_train), x_test, y_test),
        iid=run_rounds(iid(x_train, y_train, clients), x_test, y_test, rounds=rounds, seed=seed),
        zone=run_rounds(
            by_zone(x_train, y_train, clients), x_test, y_test, rounds=rounds, seed=seed
        ),
    )


def privacy_cost(
    sigmas: tuple[float, ...] = SIGMAS, rounds: int = ROUNDS, clients: int = CLIENTS, seed: int = 0
) -> dict[float, float]:
    """Accuracy federada con cada nivel de ruido sobre los pesos agregados."""
    x_train, x_test, y_train, y_test = train_test()
    particion = iid(x_train, y_train, clients)
    return {
        sigma: run_rounds(
            particion,
            x_test,
            y_test,
            rounds=rounds,
            seed=seed,
            aggregator=noisy_aggregate(sigma=sigma, seed=seed),
        )[-1]
        for sigma in sigmas
    }


def format_results(results: Results, privacy: dict[float, float]) -> str:
    """Arma las dos tablas en markdown, listas para el notebook o el README."""
    lineas = [
        f"Federado con {len(results.iid)} rondas.",
        "",
        "| variante | accuracy |",
        "|---|---|",
        f"| centralizado | {results.central:.4f} |",
        f"| federado IID | {results.iid[-1]:.4f} |",
        f"| federado por zona | {results.zone[-1]:.4f} |",
        "",
        "Costo de la privacidad, con ruido sobre los pesos agregados:",
        "",
        "| sigma | accuracy |",
        "|---|---|",
    ]
    lineas += [f"| {sigma} | {valor:.4f} |" for sigma, valor in privacy.items()]
    return "\n".join(lineas)


def run_comparison(
    rounds: int = ROUNDS,
    clients: int = CLIENTS,
    sigmas: tuple[float, ...] = SIGMAS,
    seed: int = 0,
) -> int:
    """Corre todo e imprime las tablas; devuelve 0."""
    print(
        format_results(compare(rounds, clients, seed), privacy_cost(sigmas, rounds, clients, seed))
    )
    return 0


def main() -> int:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Federado contra centralizado, y el costo del ruido"
    )
    parser.add_argument("--rounds", type=int, default=ROUNDS)
    parser.add_argument("--clients", type=int, default=CLIENTS)
    args = parser.parse_args()
    return run_comparison(args.rounds, args.clients)


if __name__ == "__main__":
    raise SystemExit(main())
