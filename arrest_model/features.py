"""Codificación del payload crudo en las 7 features del modelo.

Aplica el preprocesamiento del TP-final (notebooks 1, 3 y 4) con los parámetros guardados en
model/model.pkl: frecuencias de train, media y desvío, y ubicación de las comisarías.
"""

import threading
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer

from arrest_model.schemas import CrimeReport

MODEL_FEATURES = [
    "IUCR_freq",
    "Primary_Type_freq",
    "Location_Description_freq",
    "Day_sin",
    "X Coordinate_standardized",
    "Y Coordinate_standardized",
    "Distance Crime To Police Station_standardized",
]
CATEGORICAL = ["iucr", "primary_type", "location_description"]  # codificadas por frecuencia
XY_FEET = "EPSG:3435"  # X/Y Coordinate del dataset de Chicago
XY_METERS = "EPSG:26971"  # CRS de la distancia a la comisaría (nb1 celda 10)

_local = threading.local()


def _project(lon: Any, lat: Any, crs: str) -> tuple[np.ndarray, np.ndarray]:
    """Proyecta lon/lat (EPSG:4326) a `crs`; un Transformer por hilo porque no se comparten."""
    transformers = _local.__dict__.setdefault("transformers", {})
    if crs not in transformers:
        transformers[crs] = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return transformers[crs].transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))


def _standardize(values: Any, stats: tuple[float, float]) -> np.ndarray:
    mean, std = stats
    return (np.asarray(values, dtype=float) - mean) / std


def transform(frame: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    """Columnas crudas → las 7 features, en el orden del modelo.

    `frame` tiene iucr, primary_type, location_description, day_num (Sunday=1), latitude y
    longitude.
    """
    x, y = _project(frame["longitude"], frame["latitude"], XY_FEET)
    mx, my = _project(frame["longitude"], frame["latitude"], XY_METERS)
    stations = params["stations"]
    distance = np.hypot(mx[:, None] - stations[:, 0], my[:, None] - stations[:, 1]).min(axis=1)
    columns = [
        # Categoría que no apareció en train → frecuencia 0 (nb3 celda 58).
        *(frame[f].astype(object).map(params["freq"][f]).fillna(0.0) for f in CATEGORICAL),
        np.sin(2 * np.pi * frame["day_num"].to_numpy(dtype=float) / 7),
        _standardize(x, params["scale"]["x"]),
        _standardize(y, params["scale"]["y"]),
        _standardize(np.log1p(distance), params["scale"]["log_distance"]),
    ]
    return pd.DataFrame(
        {
            name: np.asarray(col, dtype=float)
            for name, col in zip(MODEL_FEATURES, columns, strict=True)
        }
    )


def to_features(reports: Sequence[CrimeReport], params: dict[str, Any]) -> pd.DataFrame:
    """Payloads validados → las 7 features del modelo."""
    frame = pd.DataFrame(
        {
            "iucr": [r.iucr for r in reports],
            "primary_type": [r.primary_type for r in reports],
            # Lugar vacío → "UNKNOWN", como en nb3 celda 9.
            "location_description": [r.location_description or "UNKNOWN" for r in reports],
            # isoweekday(): Monday=1 ... Sunday=7 → Sunday=1 ... Saturday=7 (nb3 celda 37).
            "day_num": [r.date.isoweekday() % 7 + 1 for r in reports],
            "latitude": [r.latitude for r in reports],
            "longitude": [r.longitude for r in reports],
        }
    )
    return transform(frame, params)
