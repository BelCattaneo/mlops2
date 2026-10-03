"""
MLflow Utility Functions

Helper functions for logging metrics, parameters, and artifacts to MLflow.
"""

import os
import tempfile
import logging
from typing import Dict, Any

import matplotlib.pyplot as plt

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


def save_and_log_artifact(filepath: str, artifact_path: str) -> None:
    """
    Save file artifact to MLflow.

    Args:
        filepath: Local path to the file
        artifact_path: Path in MLflow artifacts
    """
    try:
        import mlflow

        mlflow.log_artifact(filepath, artifact_path)
    except ImportError:
        logger.warning("MLflow not installed, skipping artifact logging")


def save_figure_and_log(
    fig: plt.Figure,
    artifact_path: str,
    dpi: int = 100,
) -> None:
    """
    Save matplotlib figure to temp file and log to MLflow.

    Args:
        fig: Matplotlib figure
        artifact_path: Full path including filename (e.g., 'charts/raw_data_overview.png')
        dpi: Resolution for saved image
    """
    import mlflow

    if "/" in artifact_path:
        artifact_dir = "/".join(artifact_path.split("/")[:-1])
        filename = artifact_path.split("/")[-1]
    else:
        artifact_dir = None
        filename = artifact_path

    temp_dir = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dir, filename)

    try:
        fig.savefig(temp_filepath, dpi=dpi, bbox_inches="tight")
        mlflow.log_artifact(temp_filepath, artifact_dir)
    finally:
        os.unlink(temp_filepath)
        os.rmdir(temp_dir)
        plt.close(fig)


def log_metrics(metrics_dict: Dict[str, Any]) -> None:
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


def log_params(params_dict: Dict[str, Any]) -> None:
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
) -> Dict[Any, float]:
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
