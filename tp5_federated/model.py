"""Mini-TP 5: el modelo que se federa.

Es una regresión logística entrenada por descenso de gradiente, escrita con numpy. No es el
XGBoost que sirve el repo: FedAvg promedia los pesos de los modelos locales, y un ensamble de
árboles no tiene pesos que promediar. Las features son las mismas; lo que cambia es el modelo.
"""

from typing import NamedTuple

import numpy as np

EPOCHS = 300
LEARNING_RATE = 0.5


class Weights(NamedTuple):
    """Los parámetros del modelo: un peso por feature y la ordenada."""

    w: np.ndarray
    b: float


def initial_weights(n_features: int) -> Weights:
    """Modelo en cero, que es de donde arranca cada ronda federada."""
    return Weights(np.zeros(n_features), 0.0)


def probabilities(weights: Weights, x: np.ndarray) -> np.ndarray:
    """Probabilidad de arresto de cada fila."""
    return 1 / (1 + np.exp(-(x @ weights.w + weights.b)))


def gradient_step(weights: Weights, x: np.ndarray, y: np.ndarray, lr: float) -> Weights:
    """Un paso de descenso de gradiente sobre todo el conjunto que recibe."""
    error = probabilities(weights, x) - y
    return Weights(weights.w - lr * (x.T @ error) / len(y), weights.b - lr * error.mean())


def train(
    x: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int = EPOCHS,
    lr: float = LEARNING_RATE,
    start: Weights | None = None,
) -> Weights:
    """Entrena desde cero o desde los pesos que se le pasen, que es lo que hace cada cliente."""
    weights = start if start is not None else initial_weights(x.shape[1])
    for _ in range(epochs):
        weights = gradient_step(weights, x, y, lr)
    return weights


def accuracy(weights: Weights, x: np.ndarray, y: np.ndarray) -> float:
    """Proporción de aciertos, que es la métrica que compara la consigna."""
    return float(((probabilities(weights, x) >= 0.5).astype(int) == y).mean())
