"""Mini-TP 5: FedAvg, el promedio de los modelos de cada cliente.

Lo único que viaja del cliente al servidor son los pesos y cuántos datos los entrenaron. Los
datos no se mueven: esa es toda la idea del aprendizaje federado.
"""

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np

from tp5_federated.model import LEARNING_RATE, Weights, train
from tp5_federated.partitions import Client

LOCAL_EPOCHS = 25


class Update(NamedTuple):
    """Lo que un cliente le manda al servidor: su modelo y cuántos datos lo entrenaron."""

    weights: Weights
    samples: int


def local_update(
    global_weights: Weights,
    client: Client,
    epochs: int = LOCAL_EPOCHS,
    lr: float = LEARNING_RATE,
) -> Update:
    """Entrena el modelo global con los datos del cliente y devuelve solo los pesos."""
    weights = train(client.x, client.y, epochs=epochs, lr=lr, start=global_weights)
    return Update(weights, samples=len(client.y))


def aggregate(updates: Sequence[Update]) -> Weights:
    """Promedia los modelos recibidos, pesando a cada cliente por su cantidad de datos.

    Sin esa ponderación, un cliente con cien filas movería el modelo global tanto como uno con
    cien mil.
    """
    total = sum(update.samples for update in updates)
    w = sum(update.weights.w * (update.samples / total) for update in updates)
    b = sum(update.weights.b * (update.samples / total) for update in updates)
    return Weights(np.asarray(w), float(b))
