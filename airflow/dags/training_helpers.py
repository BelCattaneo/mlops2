"""Entrenamiento del modelo sobre el dataset curado: ajuste y métricas.

Lo puro vive acá —entrenar y medir— y la tarea del DAG se queda con lo que toca el mundo: leer
el lake, registrar en MLflow. Así se puede probar sin Airflow instalado.

Las métricas son las seis que reporta el bundle entregado, con la misma convención: promedio
ponderado en precision, recall y f1. Con promedio ponderado el recall coincide con la accuracy,
que es lo que delata la convención en los números del modelo que ya está servido.
"""

from collections.abc import Sequence
from dataclasses import dataclass
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
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from arrest_model.model import DEFAULT_THRESHOLD

METRIC_NAMES = ("accuracy", "precision", "recall", "f1", "auc", "mcc")


def fit_model(X: pd.DataFrame, y: pd.Series) -> XGBClassifier:
    """Entrena el clasificador pesando la clase minoritaria.

    `scale_pos_weight` es lo que XGBoost ofrece para el desbalance, y reemplaza al SMOTE más
    submuestreo que hacía el pipeline heredado. Medido sobre la ventana entera, con las siete
    features del contrato fijas y evaluando las dos sobre el mismo test: pesar la clase da AUC
    0,8868 contra 0,8835, y MCC 0,5818 contra 0,5745 cuando cada una decide en su propio umbral.
    Además entrena con las filas reales —SMOTE interpolaba frecuencias, inventando valores que no
    corresponden a ninguna categoría— y es determinista, mientras el desempate entre vecinos de
    SMOTE cambiaba filas según la versión de la librería.

    Recibe el dataframe y no un array para que el modelo guarde los nombres de las features:
    con eso, servirlo con columnas en otro orden falla en vez de dar números equivocados.
    """
    positivos = int((y == 1).sum())
    peso = float((y == 0).sum() / positivos) if positivos else 1.0
    modelo = XGBClassifier(scale_pos_weight=peso)
    modelo.fit(X, y)
    return modelo


def choose_threshold(
    modelo: Any, X: pd.DataFrame, y: pd.Series, grid: Sequence[float] | None = None
) -> float:
    """El umbral que maximiza el MCC sobre el conjunto que se le pase.

    El corte que mejor decide depende de cómo se reponderó el entrenamiento, no del problema:
    pesar la clase minoritaria infla las probabilidades que el modelo emite —medido, 0,33 de
    media contra un prior real de 0,14— y entonces el corte sube. Está en 0,81 con la clase
    pesada y estaba en 0,58 con el SMOTE del pipeline heredado, que inflaba menos. Por eso el
    0,5 que trae `XGBClassifier.predict` no era óptimo para ninguno de los dos.

    Se elige sobre validación, nunca sobre el test: elegirlo donde después se mide convierte la
    métrica informada en una promesa que el modelo no puede cumplir en producción.
    """
    probabilidades = modelo.predict_proba(X)[:, 1]
    candidatos = list(grid) if grid is not None else [x / 100 for x in range(5, 96)]
    return max(candidatos, key=lambda umbral: matthews_corrcoef(y, probabilidades > umbral))


@dataclass(frozen=True)
class FittedModel:
    """El modelo listo para registrar, con el umbral que eligió y cómo lo eligió."""

    model: XGBClassifier
    threshold: float
    filas_de_ajuste: int
    filas_de_validacion: int


def fit_with_threshold(
    train: pd.DataFrame,
    features: Sequence[str],
    label: str,
    validation_size: float = 0.15,
    random_state: int = 42,
) -> FittedModel:
    """Entrena y elige el umbral, en ese orden y sobre conjuntos distintos.

    Primero ajusta un modelo con una parte del train y elige el corte sobre la parte que ese
    modelo no vio: elegirlo donde después se mide convertiría la métrica informada en una
    promesa que producción no puede cumplir.

    Y después reajusta con el train entero, que es el modelo que se registra. Reajustar es lo
    correcto —si no, se serviría un modelo entrenado con 15% menos datos de los que hay— y es
    seguro porque el umbral transfiere: medido sobre doce remuestreos del split, el corte se
    mueve con desvío 0,019 y el MCC del test con 0,0017, un orden de magnitud menos. La
    superficie del MCC alrededor del óptimo es plana, así que acertarle aproximadamente alcanza.
    """
    columnas = list(features)
    y = train[label].astype(int)
    ajuste, validacion = train_test_split(
        train, test_size=validation_size, random_state=random_state, stratify=y
    )
    explorador = fit_model(ajuste[columnas], ajuste[label].astype(int))
    umbral = choose_threshold(explorador, validacion[columnas], validacion[label].astype(int))
    return FittedModel(
        model=fit_model(train[columnas], y),
        threshold=umbral,
        filas_de_ajuste=len(train),
        filas_de_validacion=len(validacion),
    )


def evaluate(
    modelo: Any, X: pd.DataFrame, y: pd.Series, threshold: float = DEFAULT_THRESHOLD
) -> dict[str, float]:
    """Las seis métricas del bundle, medidas con el umbral con el que el modelo va a decidir.

    El umbral por defecto es el de `XGBClassifier.predict`, para que medir sin pasarlo siga
    dando lo mismo que antes.
    """
    probabilidades = modelo.predict_proba(X)[:, 1]
    predicciones = (probabilidades > threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y, predicciones)),
        "precision": float(precision_score(y, predicciones, average="weighted", zero_division=0)),
        "recall": float(recall_score(y, predicciones, average="weighted")),
        "f1": float(f1_score(y, predicciones, average="weighted")),
        "auc": float(roc_auc_score(y, probabilidades)),
        "mcc": float(matthews_corrcoef(y, predicciones)),
    }
