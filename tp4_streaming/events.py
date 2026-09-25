"""Mini-TP 4: el flujo de reportes que se puntúa online.

Los reportes son sintéticos: salen del reporte de ejemplo del repo, con variación alrededor de
su zona y de sus categorías. Cumplen el mismo contrato que valida la API REST, así que el flujo
ejercita el camino real de datos y no un formato inventado para la ocasión.

El flujo puede correrse los reportes a otra zona a partir de cierto evento. Eso es lo que hace
visible el drift: las coordenadas estandarizadas se alejan de la media con la que se entrenó.
"""

import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from arrest_model.schemas import EXAMPLE_REPORT, PRIMARY_TYPES

BASE_LATITUDE = float(EXAMPLE_REPORT["latitude"])
BASE_LONGITUDE = float(EXAMPLE_REPORT["longitude"])
START = datetime.fromisoformat(str(EXAMPLE_REPORT["date"]))

# Dispersión de los reportes alrededor de la zona base, en grados (unos 800 m).
SPREAD = 0.01
# Cuánto se corren los reportes hacia el norte con el drift, en grados (unos 5,5 km).
DRIFT_DEGREES = 0.05

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
