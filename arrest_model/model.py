"""Modelo empaquetado en model/model.pkl: carga y predicción."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib

from arrest_model.features import encode_payload
from arrest_model.schemas import CrimeReport, PredictionOut

MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "model.pkl"

# El corte con el que decide un bundle que no trae uno propio, que es la regla de
# `XGBClassifier.predict` y la que documentan los cuatro protocolos.
DEFAULT_THRESHOLD = 0.5


def load_bundle(path: Path = MODEL_PATH) -> dict[str, Any]:
    """Lee el bundle {model, params, metadata} generado fuera del TP."""
    if not path.exists():
        raise FileNotFoundError(f"No existe el modelo en {path}")
    return joblib.load(path)


def predict(bundle: dict[str, Any], reports: Sequence[CrimeReport]) -> list[PredictionOut]:
    """Codifica los payloads y predice con una sola llamada al modelo."""
    if not reports:
        return []
    features = encode_payload(reports, bundle["params"])
    probabilities = bundle["model"].predict_proba(features)[:, 1]
    name, version = bundle["metadata"]["name"], bundle["metadata"]["version"]
    # El umbral de decisión es un parámetro del modelo, no una constante del servicio: el que
    # entrena puede elegir el que maximiza la métrica sobre un conjunto de validación, y viaja
    # con el modelo como viajan las frecuencias y los escaladores. Sin umbral propio queda el
    # 0.5 de `XGBClassifier.predict`, que es lo que decide el `.pkl` entregado.
    threshold = float(bundle.get("threshold", DEFAULT_THRESHOLD))
    return [
        PredictionOut(
            arrest=int(p > threshold),
            probability=float(p),
            model_name=name,
            model_version=version,
        )
        for p in probabilities
    ]
