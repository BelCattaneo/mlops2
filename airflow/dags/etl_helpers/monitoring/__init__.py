"""Métricas de cada capa del ETL, registradas en MLflow.

Solo números: los gráficos salieron de acá. Un ETL que genera PNGs en cada corrida carga
matplotlib para producir algo que nadie mira, y la calidad de datos no se vigila con imágenes
sino con métricas y con aserciones del propio pipeline, como el contrato de features.
"""

from .loggers import (
    log_balance_metrics,
    log_feature_selection_metrics,
    log_pipeline_summary,
    log_raw_data_metrics,
    log_split_metrics,
)
from .mlflow_utils import get_value_distribution, log_metrics, log_params

__all__ = [
    "log_raw_data_metrics",
    "log_split_metrics",
    "log_balance_metrics",
    "log_feature_selection_metrics",
    "log_pipeline_summary",
    "log_metrics",
    "log_params",
    "get_value_distribution",
]
