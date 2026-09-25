"""Mini-TP 4: el flujo de reportes que se puntúa online.

Los reportes son sintéticos: se generan alrededor de la zona donde el modelo vio la mayoría de
los crímenes, variando categorías y coordenadas. Cumplen el mismo contrato que valida la API
REST, así que el flujo ejercita el camino real de datos y no un formato inventado.

El flujo puede correrse los reportes a otra zona a partir de cierto evento. Eso es lo que hace
visible el drift: las coordenadas estandarizadas se alejan de la media con la que se entrenó.
"""

import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from arrest_model.schemas import EXAMPLE_REPORT, PRIMARY_TYPES

# Centro del flujo: la media de las coordenadas de entrenamiento, que el modelo guarda
# proyectada en pies (EPSG:3435) y acá va en grados. Un test la compara contra el .pkl.
BASE_LATITUDE = 41.846943
BASE_LONGITUDE = -87.668933
START = datetime.fromisoformat(str(EXAMPLE_REPORT["date"]))

# Dispersión de los reportes alrededor de la zona base, en grados (unos 800 m).
SPREAD = 0.01
# Cuánto se corren los reportes hacia el norte con el drift, en grados (unos 13 km). Es más de
# un desvío de entrenamiento en ese eje, así que el indicador lo separa del ruido del flujo.
DRIFT_DEGREES = 0.12

IUCRS = ("1310", "0820", "0486", "1320")
LOCATIONS = ("APARTMENT", "STREET", "RESIDENCE", "SIDEWALK")


def crime_stream(
    count: int, *, seed: int = 0, drift_from: int | None = None
) -> Iterator[dict[str, Any]]:
    """Genera `count` reportes; con `drift_from`, los corre de zona desde ese evento.

    La semilla fija el flujo entero: dos corridas con la misma semilla dan los mismos reportes,
    que es lo que permite testear el consumidor y volver a generar lo que muestra el notebook.
    """
    azar = random.Random(seed)
    for index in range(count):
        corrido = drift_from is not None and index >= drift_from
        latitude = BASE_LATITUDE + (DRIFT_DEGREES if corrido else 0.0) + azar.gauss(0, SPREAD)
        yield {
            "iucr": azar.choice(IUCRS),
            "primary_type": azar.choice(PRIMARY_TYPES),
            "location_description": azar.choice(LOCATIONS),
            "date": (START + timedelta(minutes=index)).isoformat(),
            "latitude": round(latitude, 6),
            "longitude": round(BASE_LONGITUDE + azar.gauss(0, SPREAD), 6),
        }
