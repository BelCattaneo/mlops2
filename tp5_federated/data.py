"""Mini-TP 5: la muestra de arrestos que se reparte entre los clientes.

Son 20.000 filas del dataset final del TP-final, con las mismas 7 features que consume el modelo
del repo y la etiqueta de arresto. Se versiona la muestra y no el dataset completo, que tiene
casi 200.000 filas; la genera `prep/make_federated_sample.py`, fuera del entregable.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from arrest_model.features import MODEL_FEATURES

SAMPLE = Path(__file__).resolve().parent / "data" / "arrest_sample.csv.gz"
LABEL = "Arrest_tag"
TEST_SIZE = 0.25
SEED = 0

Split = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def load_sample(path: Path = SAMPLE) -> pd.DataFrame:
    """Lee la muestra versionada, con las features en el orden con el que se entrena."""
    if not path.exists():
        raise FileNotFoundError(f"No existe la muestra en {path}")
    return pd.read_csv(path)[[*MODEL_FEATURES, LABEL]]


def train_test(path: Path = SAMPLE, test_size: float = TEST_SIZE, seed: int = SEED) -> Split:
    """Separa entrenamiento y evaluación, estratificando por la etiqueta.

    La semilla es fija: el mismo corte para el modelo centralizado y para el federado es lo que
    hace comparables sus accuracies.
    """
    muestra = load_sample(path)
    features = muestra[list(MODEL_FEATURES)].to_numpy(dtype=float)
    labels = muestra[LABEL].to_numpy(dtype=int)
    return train_test_split(
        features, labels, test_size=test_size, random_state=seed, stratify=labels
    )
