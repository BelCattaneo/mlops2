"""El formato de los parámetros de preprocesamiento del modelo.

Los parámetros —frecuencias, media y desvío, y las comisarías proyectadas— son la otra mitad
del modelo: con los parámetros equivocados, el mismo estimador predice cualquier cosa. Por eso
viajan con él, y por eso su formato lo define este paquete y no quien los produce.
"""

import json
from typing import Any

import numpy as np


def dump_params(params: dict[str, Any]) -> bytes:
    """Serializa los parámetros como JSON, para que cualquiera los pueda leer.

    No va como pickle a propósito. Un pickle ata al lector a las librerías del escritor: el que
    escribía el contenedor de Airflow arrastraba una referencia a `dill`, que no está ni en el
    venv del repo ni en las imágenes de las APIs, así que el artefacto solo se podía leer donde
    se había escrito. Son datos planos y JSON además se puede abrir y revisar a mano.
    """
    serializable = {
        "freq": {columna: dict(mapa) for columna, mapa in params["freq"].items()},
        "scale": {clave: list(valores) for clave, valores in params["scale"].items()},
        "stations": np.asarray(params["stations"]).tolist(),
    }
    return json.dumps(serializable, indent=2, sort_keys=True).encode("utf-8")


def load_params(data: bytes) -> dict[str, Any]:
    """Reconstruye los parámetros desde el JSON, con las comisarías como array."""
    crudo = json.loads(data.decode("utf-8"))
    return {
        "freq": crudo["freq"],
        "scale": {clave: tuple(valores) for clave, valores in crudo["scale"].items()},
        "stations": np.asarray(crudo["stations"], dtype=np.float64),
    }
