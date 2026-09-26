"""Mini-TP 4: las métricas de una ventana del flujo.

Todo entra por parámetro: los datos de la ventana, no el reloj. Así cada métrica se verifica
con valores conocidos, en lugar de depender de cuánto tardó la máquina en esa corrida.
"""

from collections.abc import Sequence

import numpy as np

from arrest_model.features import Params, encode_payload
from arrest_model.schemas import CrimeReport

# Las features que el modelo estandariza con la media y el desvío del entrenamiento: ahí, por
# construcción, tienen media 0 y desvío 1. Cuánto se alejan de 0 es cuánto se corrió la entrada.
STANDARDIZED_FEATURES = (
    "X Coordinate_standardized",
    "Y Coordinate_standardized",
    "Distance Crime To Police Station_standardized",
)


def window_throughput(count: int, seconds: float) -> float:
    """Eventos por segundo de la ventana; 0 si la ventana todavía no abarca tiempo."""
    return count / seconds if seconds > 0 else 0.0


def p95(latencies: Sequence[float]) -> float:
    """Latencia que el 95% de los eventos no supera; 0 si la ventana está vacía.

    Se informa el percentil y no el promedio porque el promedio esconde los casos malos: unos
    pocos eventos muy lentos casi no lo mueven, y son justamente los que se quieren ver.
    """
    return float(np.percentile(latencies, 95)) if len(latencies) else 0.0


def drift_indicator(reports: Sequence[CrimeReport], params: Params) -> float:
    """Cuánto se corrieron las entradas respecto del entrenamiento, en desvíos.

    Codifica los reportes de la ventana y devuelve la mayor desviación absoluta entre las medias
    de las features estandarizadas. Cerca de 0 significa que llegan datos parecidos a los de
    entrenamiento; con las tres se cubre cualquiera que se mueva, sin elegir una de antemano.
    """
    if not reports:
        return 0.0
    features = encode_payload(reports, params)
    return max(abs(float(features[name].mean())) for name in STANDARDIZED_FEATURES)
