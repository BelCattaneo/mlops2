"""Codificación del payload crudo en las 7 features del modelo.

El orden es: primero se proyectan las coordenadas una sola vez y después corre cada codificador.
Cada feature tiene su función y `ENCODERS` fija el orden con el que se entrenó el modelo. Los
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
UNKNOWN = "UNKNOWN"  # cómo codificó el TP-final el lugar vacío (nb3 celda 9)

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


def with_projections(frame: pd.DataFrame) -> pd.DataFrame:
    """Agrega las coordenadas proyectadas que leen los codificadores, calculadas una sola vez."""
    x_feet, y_feet = _project(frame, XY_FEET)
    x_meters, y_meters = _project(frame, XY_METERS)
    return frame.assign(x_feet=x_feet, y_feet=y_feet, x_meters=x_meters, y_meters=y_meters)


def _frequency(values: pd.Series, mapping: dict[str, float]) -> np.ndarray:
    """Reemplaza cada categoría por su frecuencia en train; 0 si no apareció (nb3 celda 58)."""
    return values.astype(object).map(mapping).fillna(0.0).to_numpy(dtype=float)


def _standardize(values: Any, stats: tuple[float, float]) -> np.ndarray:
    """Resta la media y divide por el desvío calculados en train (nb4 celda 16)."""
    mean, std = stats
    return (np.asarray(values, dtype=float) - mean) / std


def iucr_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Código IUCR del delito, codificado por frecuencia."""
    return _frequency(frame["iucr"], params["freq"]["iucr"])


def primary_type_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Tipo de delito, codificado por frecuencia."""
    return _frequency(frame["primary_type"], params["freq"]["primary_type"])


def location_frequency(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Lugar del hecho, codificado por frecuencia; vacío o nulo cuenta como UNKNOWN."""
    location = frame["location_description"].astype(object).fillna(UNKNOWN).replace("", UNKNOWN)
    return _frequency(location, params["freq"]["location_description"])


def day_sine(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Día de la semana como seno, con domingo=1 (nb3 celdas 37 y 39)."""
    return np.sin(2 * np.pi * frame["day_num"].to_numpy(dtype=float) / 7)


def x_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Coordenada X en pies (EPSG:3435), estandarizada."""
    return _standardize(frame["x_feet"], params["scale"]["x"])


def y_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Coordenada Y en pies (EPSG:3435), estandarizada."""
    return _standardize(frame["y_feet"], params["scale"]["y"])


def distance_to_station_standardized(frame: pd.DataFrame, params: Params) -> np.ndarray:
    """Distancia en metros a la comisaría más cercana (EPSG:26971), con log1p y estandarizada."""
    stations = params["stations"]
    x = frame["x_meters"].to_numpy(dtype=float)[:, None]
    y = frame["y_meters"].to_numpy(dtype=float)[:, None]
    distance = np.hypot(x - stations[:, 0], y - stations[:, 1]).min(axis=1)
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
    """Proyecta las coordenadas y aplica cada codificador, conservando el índice de entrada.

    `frame` tiene las columnas crudas: iucr, primary_type, location_description, day_num
    (domingo=1), latitude y longitude.
    """
    prepared = with_projections(frame)
    return pd.DataFrame(
        {name: encoder(prepared, params) for name, encoder in ENCODERS.items()},
        index=frame.index,
    )


def encode_payload(reports: Sequence[CrimeReport], params: Params) -> pd.DataFrame:
    """Convierte los payloads validados en las columnas crudas y las codifica."""
    frame = pd.DataFrame(
        {
            "iucr": [r.iucr for r in reports],
            "primary_type": [r.primary_type for r in reports],
            "location_description": [r.location_description for r in reports],
            # isoweekday(): lunes=1 ... domingo=7 → domingo=1 ... sábado=7 (nb3 celda 37).
            "day_num": [r.date.isoweekday() % 7 + 1 for r in reports],
            "latitude": [r.latitude for r in reports],
            "longitude": [r.longitude for r in reports],
        }
    )
    return encode_frame(frame, params)
