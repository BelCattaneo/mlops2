"""
MLflow Utility Functions

Helper functions for logging metrics, parameters, and artifacts to MLflow.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Configure MLflow tracking URI
try:
    import mlflow

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    logger.info(f"MLflow tracking URI set to: {mlflow.get_tracking_uri()}")
except ImportError:
    logger.warning("MLflow not installed")
except Exception as e:
    logger.warning(f"Failed to configure MLflow: {e}")


def log_metrics(metrics_dict: dict[str, Any]) -> None:
    """
    Log multiple metrics to MLflow.

    Args:
        metrics_dict: Dictionary of metric names and values
    """
    try:
        import mlflow

        for key, value in metrics_dict.items():
            mlflow.log_metric(key, value)
    except ImportError:
        pass


def log_params(params_dict: dict[str, Any]) -> None:
    """
    Log multiple parameters to MLflow.

    Args:
        params_dict: Dictionary of parameter names and values
    """
    try:
        import mlflow

        for key, value in params_dict.items():
            mlflow.log_param(key, value)
    except ImportError:
        pass


def get_value_distribution(
    series,
    normalize: bool = True,
    as_percentage: bool = True,
) -> dict[Any, float]:
    """
    Get value distribution from a pandas Series.

    Args:
        series: Pandas Series
        normalize: Whether to normalize counts
        as_percentage: Whether to return as percentage (multiply by 100)

    Returns:
        Dictionary of value: count/percentage
    """
    dist = series.value_counts(normalize=normalize)
    if as_percentage:
        dist = dist * 100
    return dist.to_dict()
