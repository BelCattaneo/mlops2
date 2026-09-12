"""Codificación del payload crudo en las 7 features del modelo.

Cada feature tiene su función; `ENCODERS` fija el orden con el que se entrenó el modelo. Los
parámetros (frecuencias, media/desvío y comisarías) viajan en model/model.pkl y salen del
preprocesamiento del TP-final (notebooks 1, 3 y 4).
"""

import threading
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer

from arrest_model.schemas import CrimeReport

Params = dict[str, Any]
Encoder = Callable[[pd.DataFrame, Params], np.ndarray]

XY_FEET = "EPSG:3435"  # X/Y Coordinate del dataset de Chicago
XY_METERS = "EPSG:26971"  # CRS de la distancia a la comisaría (nb1 celda 10)

_local = threading.local()


def _project(frame: pd.DataFrame, crs: str) -> tuple[np.ndarray, np.ndarray]:
    """Proyecta las columnas longitude/latitude (EPSG:4326) al CRS pedido.

    Cachea un Transformer por hilo: crearlo es caro y pyproj no los comparte entre hilos.
    """
    transformers = _local.__dict__.setdefault("transformers", {})
    if crs not in transformers:
        transformers[crs] = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    longitude = frame["longitude"].to_numpy(dtype=float)
    latitude = frame["latitude"].to_numpy(dtype=float)
    return transformers[crs].transform(longitude, latitude)


def _frequency(frame: pd.DataFrame, params: Params, field: str) -> np.ndarray:
    """Reemplaza la categoría por su frecuencia en train; 0 si no apareció (nb3 celda 58)."""
    mapped = frame[field].astype(object).map(params["freq"][field])
    return mapped.fillna(0.0).to_numpy(dtype=float)


def _standardize(values: np.ndarray, stats: tuple[float, float]) -> np.ndarray:
    """Resta la media y divide por el desvío calculados en train (nb4 celda 16)."""
    mean, std = stats
    return (np.asarray(values, dtype=float) - mean) / std


def iucr_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Código IUCR del delito, codificado por frecuencia."""
    return _frequency(frame, params, "iucr")


def primary_type_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Tipo de delito, codificado por frecuencia."""
    return _frequency(frame, params, "primary_type")


def location_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Lugar del hecho, codificado por frecuencia."""
    return _frequency(frame, params, "location_description")


def day_sine(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Día de la semana como seno, con domingo=1 (nb3 celdas 37 y 39)."""
    return np.sin(2 * np.pi * frame["day_num"].to_numpy(dtype=float) / 7)


def x_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Coordenada X en pies (EPSG:3435), estandarizada."""
    x, _ = _project(frame, XY_FEET)
    return _standardize(x, params["scale"]["x"])


def y_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Coordenada Y en pies (EPSG:3435), estandarizada."""
    _, y = _project(frame, XY_FEET)
    return _standardize(y, params["scale"]["y"])


def distance_to_station_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Distancia en metros a la comisaría más cercana (EPSG:26971), con log1p y estandarizada."""
    x, y = _project(frame, XY_METERS)
    stations = params["stations"]
    distance = np.hypot(x[:, None] - stations[:, 0], y[:, None] - stations[:, 1]).min(axis=1)
    return _standardize(np.log1p(distance), params["scale"]["log_distance"])


# Nombre de la feature -> función que la calcula, en el orden con el que se entrenó el modelo.
ENCODERS: dict[str, Encoder] = {
    "IUCR_freq": iucr_frequency,
    "Primary_Type_freq": primary_type_frequency,
    "Location_Description_freq": location_frequency,
    "Day_sin": day_sine,
    "X Coordinate_standardized": x_standardized,
    "Y Coordinate_standardized": y_standardized,
    "Distance Crime To Police Station_standardized": distance_to_station_standardized,
}
MODEL_FEATURES = list(ENCODERS)


def encode_frame(frame: pd.DataFrame, params: Params) -> pd.DataFrame:
    """Aplica cada codificador y devuelve las 7 features en el orden del modelo.

    `frame` tiene las columnas crudas: iucr, primary_type, location_description, day_num
    (domingo=1), latitude y longitude.
    """
    return pd.DataFrame({name: encoder(frame, params) for name, encoder in ENCODERS.items()})


def encode_payload(reports: Sequence[CrimeReport], params: Params) -> pd.DataFrame:
    """Convierte los payloads validados en las columnas crudas y las codifica."""
    frame = pd.DataFrame(
        {
            "iucr": [r.iucr for r in reports],
            "primary_type": [r.primary_type for r in reports],
            # Lugar vacío → "UNKNOWN", como en nb3 celda 9.
            "location_description": [r.location_description or "UNKNOWN" for r in reports],
            # isoweekday(): lunes=1 ... domingo=7 → domingo=1 ... sábado=7 (nb3 celda 37).
            "day_num": [r.date.isoweekday() % 7 + 1 for r in reports],
            "latitude": [r.latitude for r in reports],
            "longitude": [r.longitude for r in reports],
        }
    )
    return encode_frame(frame, params)
