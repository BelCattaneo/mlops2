"""Entrenamiento del modelo sobre el dataset curado: ajuste y métricas.

Lo puro vive acá —entrenar y medir— y la tarea del DAG se queda con lo que toca el mundo: leer
el lake, registrar en MLflow. Así se puede probar sin Airflow instalado.

Las métricas son las seis que reporta el bundle entregado, con la misma convención: promedio
ponderado en precision, recall y f1. Con promedio ponderado el recall coincide con la accuracy,
que es lo que delata la convención en los números del modelo que ya está servido.
"""

from typing import Any

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

METRIC_NAMES = ("accuracy", "precision", "recall", "f1", "auc", "mcc")


def fit_model(X: pd.DataFrame, y: pd.Series) -> XGBClassifier:
    """Entrena el clasificador con los defaults, igual que el modelo del TP-final.

    Recibe el dataframe y no un array para que el modelo guarde los nombres de las features:
    con eso, servirlo con columnas en otro orden falla en vez de dar números equivocados.
    """
    modelo = XGBClassifier()
    modelo.fit(X, y)
    return modelo


def evaluate(modelo: Any, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """Las seis métricas del bundle, medidas sobre el conjunto que se le pase."""
    predicciones = modelo.predict(X)
    probabilidades = modelo.predict_proba(X)[:, 1]
    return {
        "accuracy": float(accuracy_score(y, predicciones)),
        "precision": float(precision_score(y, predicciones, average="weighted", zero_division=0)),
        "recall": float(recall_score(y, predicciones, average="weighted")),
        "f1": float(f1_score(y, predicciones, average="weighted")),
        "auc": float(roc_auc_score(y, probabilidades)),
        "mcc": float(matthews_corrcoef(y, predicciones)),
    }
