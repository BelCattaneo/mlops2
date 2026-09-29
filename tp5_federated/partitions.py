"""Mini-TP 5: cómo se reparten los datos entre los clientes.

Un cliente es alguien que tiene datos y no los comparte. Las dos particiones son los dos
extremos del problema: repartir al azar, donde todos ven lo mismo, y repartir por zona, donde
cada uno ve su pedazo de ciudad. La segunda es la realista, y la que hace sufrir al promedio.
"""

from typing import NamedTuple

import numpy as np

from arrest_model.features import MODEL_FEATURES

CLIENTS = 5
# La coordenada norte-sur, que es con la que se arman las franjas de ciudad.
NORTH_SOUTH = MODEL_FEATURES.index("Y Coordinate_standardized")


class Client(NamedTuple):
    """Los datos de un cliente, que nunca salen de él."""

    x: np.ndarray
    y: np.ndarray


def _split(x: np.ndarray, y: np.ndarray, order: np.ndarray, clients: int) -> list[Client]:
    """Parte en `clients` pedazos siguiendo el orden que se le pase."""
    return [Client(x[idx], y[idx]) for idx in np.array_split(order, clients)]


def iid(x: np.ndarray, y: np.ndarray, clients: int = CLIENTS, seed: int = 0) -> list[Client]:
    """Reparte las filas al azar: cada cliente termina con una muestra parecida al total."""
    return _split(x, y, np.random.default_rng(seed).permutation(len(y)), clients)


def by_zone(x: np.ndarray, y: np.ndarray, clients: int = CLIENTS) -> list[Client]:
    """Reparte por franjas de norte a sur: cada cliente ve una zona distinta de la ciudad.

    Las franjas son de ancho geográfico fijo, no de igual cantidad de filas, así que cada cliente
    se queda con los reportes que de verdad ocurren en su zona: unas tienen el cuádruple que
    otras. Con tamaños distintos, ponderar por cantidad de datos en el promedio deja de ser un
    detalle.

    Es el caso realista —los reportes de una zona se quedan en la zona— y también el difícil: los
    modelos locales aprenden de poblaciones distintas y el promedio los concilia.
    """
    coordinate = x[:, NORTH_SOUTH]
    edges = np.linspace(coordinate.min(), coordinate.max(), clients + 1)
    # `digitize` numera las franjas desde 1; la última incluye su borde derecho.
    zone = np.clip(np.digitize(coordinate, edges[1:-1]), 0, clients - 1)
    return [Client(x[zone == k], y[zone == k]) for k in range(clients)]
