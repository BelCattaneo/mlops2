"""Modelo empaquetado en model/model.pkl: carga y predicción."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib

from arrest_model.features import to_features
from arrest_model.schemas import CrimeReport, PredictionOut

MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "model.pkl"


def load_bundle(path: Path = MODEL_PATH) -> dict[str, Any]:
    """Lee el bundle {model, params, metadata} generado fuera del TP."""
    if not path.exists():
        raise FileNotFoundError(f"No existe el modelo en {path}")
    return joblib.load(path)


def predict(bundle: dict[str, Any], reports: Sequence[CrimeReport]) -> list[PredictionOut]:
    """Codifica los payloads y predice con una sola llamada al modelo."""
    probabilities = bundle["model"].predict_proba(to_features(reports, bundle["params"]))[:, 1]
    name, version = bundle["metadata"]["name"], bundle["metadata"]["version"]
    # Misma regla que XGBClassifier.predict: clase 1 si la probabilidad supera 0.5.
    return [
        PredictionOut(
            arrest=int(p > 0.5), probability=float(p), model_name=name, model_version=version
        )
        for p in probabilities
    ]
