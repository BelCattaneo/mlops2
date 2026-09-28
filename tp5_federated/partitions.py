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

    Es el caso realista —los reportes de un distrito se quedan en el distrito— y también el
    difícil: los modelos locales aprenden de poblaciones distintas y el promedio los concilia.
    """
    return _split(x, y, np.argsort(x[:, NORTH_SOUTH]), clients)
