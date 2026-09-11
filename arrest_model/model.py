"""Carga del modelo empaquetado en model/model.pkl."""

from pathlib import Path
from typing import Any

import joblib

MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "model.pkl"


def load_bundle(path: Path = MODEL_PATH) -> dict[str, Any]:
    """Lee el bundle {model, params, metadata} generado fuera del TP."""
    if not path.exists():
        raise FileNotFoundError(f"No existe el modelo en {path}")
    return joblib.load(path)
