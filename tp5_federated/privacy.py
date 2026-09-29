"""Mini-TP 5: ruido sobre los pesos agregados, la parte opcional de la consigna.

Que los datos no se muevan no alcanza para decir que son privados: los pesos que manda cada
cliente llevan información sobre las filas con las que se entrenaron. Sumarle ruido al promedio
la desdibuja, y cuesta accuracy. Ese intercambio es lo que la consigna pide analizar.

Es la versión simple: ruido gaussiano sobre el modelo agregado. La privacidad diferencial de
verdad además acota cuánto puede aportar cada cliente y lleva la cuenta de lo que se gastó de
presupuesto de privacidad a lo largo de las rondas.
"""

from collections.abc import Callable, Sequence

import numpy as np

from tp5_federated.federated import Update, aggregate
from tp5_federated.model import Weights

Aggregator = Callable[[Sequence[Update]], Weights]


def noisy_aggregate(sigma: float, seed: int = 0) -> Aggregator:
    """Devuelve un agregador que promedia como FedAvg y le suma ruido gaussiano.

    Con `sigma` en 0 es exactamente FedAvg, así que la misma corrida sirve de línea de base.
    """
    rng = np.random.default_rng(seed)

    def aggregator(updates: Sequence[Update]) -> Weights:
        weights = aggregate(updates)
        if sigma == 0:
            return weights
        return Weights(
            weights.w + rng.normal(0, sigma, size=weights.w.shape),
            weights.b + float(rng.normal(0, sigma)),
        )

    return aggregator
