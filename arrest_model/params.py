"""El formato de los parámetros del modelo, los de codificar y el de decidir.

Las frecuencias, la media y el desvío y las comisarías proyectadas son la otra mitad del modelo:
con los parámetros equivocados, el mismo estimador predice cualquier cosa. El umbral es la otra
mitad de la decisión: con 0,5 en vez del elegido sobre validación, el mismo estimador decide
peor —MCC 0,4765 contra 0,5775, medido sobre el test de la versión 14—.

Los tres viajan en el mismo archivo y por eso están acá: el que carga el artefacto puede
codificar y decidir sin preguntarle nada al registro. El umbral es opcional porque los
artefactos escritos antes de esto no lo traen, y esos deciden con el 0,5 de siempre.
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
    if "threshold" in params:
        serializable["threshold"] = float(params["threshold"])
    return json.dumps(serializable, indent=2, sort_keys=True).encode("utf-8")


def load_params(data: bytes) -> dict[str, Any]:
    """Reconstruye los parámetros desde el JSON, con las comisarías como array.

    Devuelve `threshold` solo si el artefacto lo trae: quien lo consume lo saca con `pop` antes
    de codificar, porque el codificador recibe parámetros de codificación y nada más.
    """
    crudo = json.loads(data.decode("utf-8"))
    parametros = {
        "freq": crudo["freq"],
        "scale": {clave: tuple(valores) for clave, valores in crudo["scale"].items()},
        "stations": np.asarray(crudo["stations"], dtype=np.float64),
    }
    if "threshold" in crudo:
        parametros["threshold"] = float(crudo["threshold"])
    return parametros
