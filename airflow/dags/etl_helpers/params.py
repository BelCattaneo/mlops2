"""Los parámetros de preprocesamiento que el ETL ajusta, en la forma que el modelo consume.

El pipeline ajusta frecuencias y escaladores sobre su propia ventana de datos. Si el modelo se
entrena con esos parámetros y después se sirve con otros, lo que el modelo recibe en producción
deja de corresponder a lo que vio entrenando: es training/serving skew, y está medido —el modelo
entregado, alimentado con datos codificados por el ETL, predice arresto en el 99% de las filas.

Por eso los parámetros viajan con el modelo. Este módulo los pasa de la forma del ETL a la que
espera `arrest_model.features`, que es la codificación que usan los cuatro protocolos.
"""

import json
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer

# El modelo usa tres de las diez columnas que el ETL codifica por frecuencia.
FREQ_COLUMNS = ("iucr", "primary_type", "location_description")

# Los nombres del ETL contra los que lee el codificador. El tercero es la distancia, que llega
# ya pasada por log1p: el escalador se ajusta sobre el logaritmo, no sobre los metros.
SCALE_KEYS = {
    "x_coordinate": "x",
    "y_coordinate": "y",
    "distance_crime_to_police_station": "log_distance",
}

# El CRS en el que el codificador mide la distancia a la comisaría.
STATIONS_CRS = "EPSG:26971"


def project_stations(stations: pd.DataFrame) -> np.ndarray:
    """Proyecta las comisarías al CRS de la distancia, como un par por comisaría."""
    latitudes = stations["latitude"].to_numpy(dtype=float)
    longitudes = stations["longitude"].to_numpy(dtype=float)
    transformador = Transformer.from_crs("EPSG:4326", STATIONS_CRS, always_xy=True)
    x, y = transformador.transform(longitudes, latitudes)
    return np.column_stack([x, y]).astype(np.float64)


def build_params(
    frequencies: dict[str, pd.Series],
    scale: dict[str, tuple[float, float]],
    stations: pd.DataFrame,
) -> dict[str, Any]:
    """Arma el diccionario de parámetros que `arrest_model.features` espera recibir.

    Falla si falta algún estadístico de escala: codificar con un hueco daría una feature en cero
    y un modelo que parece funcionar.
    """
    faltan = [columna for columna in SCALE_KEYS if columna not in scale]
    if faltan:
        raise ValueError(f"faltan los estadísticos de escala de {', '.join(faltan)}")
    return {
        "freq": {
            columna: dict(frequencies[columna])
            for columna in FREQ_COLUMNS
            if columna in frequencies
        },
        "scale": {destino: tuple(scale[origen]) for origen, destino in SCALE_KEYS.items()},
        "stations": project_stations(stations),
    }


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
