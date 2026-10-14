"""
MLflow Logging Functions

Functions for logging metrics and visualizations to MLflow for each pipeline stage.
"""

import logging
from typing import Any

import pandas as pd
from etl_config import ETL_EXPERIMENT, config

from .mlflow_utils import (
    get_value_distribution,
    log_metrics,
    log_params,
)

logger = logging.getLogger(__name__)


def log_raw_data_metrics(
    df: pd.DataFrame,
    run_name: str = "raw_data",
) -> dict[str, Any]:
    """
    Log raw data quality metrics and visualizations to MLflow.

    Args:
        df: Raw crime data
        run_name: MLflow run name

    Returns:
        Summary metrics dictionary
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow not installed, skipping monitoring")
        return {}

    logger.info(f"Logging raw data metrics to MLflow: {run_name}")

    mlflow.set_experiment(ETL_EXPERIMENT)
    with mlflow.start_run(run_name=run_name):
        total_records = len(df)
        metrics = {
            "total_records": total_records,
            "total_columns": len(df.columns),
        }

        params = {}
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            start_date = df["date"].min()
            end_date = df["date"].max()
            params["start_date"] = start_date.strftime("%Y-%m-%d")
            params["end_date"] = end_date.strftime("%Y-%m-%d")
            metrics["days_coverage"] = (end_date - start_date).days

        missing_pct = (df.isnull().sum() / len(df) * 100).to_dict()
        for col, pct in missing_pct.items():
            if pct > 0:
                metrics[f"missing_pct_{col}"] = pct

        arrest_dist = {}
        if "arrest" in df.columns:
            arrest_dist = get_value_distribution(df["arrest"])
            metrics["arrest_rate_pct"] = arrest_dist.get(True, 0)
            metrics["no_arrest_rate_pct"] = arrest_dist.get(False, 0)

        key_columns = ["district", "primary_type", "location_description"]
        for col in key_columns:
            if col in df.columns:
                metrics[f"unique_{col}"] = df[col].nunique()

        log_metrics(metrics)
        log_params(params)

        logger.info("Raw data metrics logged successfully")
        return {
            "total_records": total_records,
            "arrest_rate": arrest_dist.get(True, 0) if "arrest" in df.columns else None,
        }


def log_split_metrics(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_column: str | None = None,
    run_name: str = "split",
) -> dict[str, Any]:
    """
    Log train/test split metrics to MLflow.

    Args:
        train_df: Training data
        test_df: Test data
        target_column: Target column name (default from config)
        run_name: MLflow run name

    Returns:
        Summary metrics dictionary
    """
    if target_column is None:
        target_column = config.TARGET_COLUMN

    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow not installed, skipping monitoring")
        return {}

    logger.info(f"Logging split metrics to MLflow: {run_name}")

    mlflow.set_experiment(ETL_EXPERIMENT)
    with mlflow.start_run(run_name=run_name):
        metrics = {
            "train_size": len(train_df),
            "test_size": len(test_df),
            "train_test_ratio": len(train_df) / (len(train_df) + len(test_df)),
        }

        if target_column in train_df.columns:
            train_dist = get_value_distribution(train_df[target_column])
            test_dist = get_value_distribution(test_df[target_column])

            for class_val, pct in train_dist.items():
                metrics[f"train_class_{class_val}_pct"] = pct
            for class_val, pct in test_dist.items():
                metrics[f"test_class_{class_val}_pct"] = pct

        log_metrics(metrics)

        logger.info("Split metrics logged successfully")
        return {
            "train_size": len(train_df),
            "test_size": len(test_df),
        }


def log_pipeline_summary(
    raw_count: int,
    enriched_count: int,
    train_count: int,
    test_count: int,
    final_train_count: int,
    final_test_count: int,
    feature_count: int,
    lineage_written: float = 1.0,
    run_name: str = "pipeline_summary",
) -> dict[str, Any]:
    """
    Log overall pipeline summary showing data flow through all stages.

    Args:
        raw_count: Number of raw records
        enriched_count: Number of enriched records (after cleaning)
        train_count: Number of training records after split
        test_count: Number of test records after split
        final_train_count: Number of final training records after feature selection
        final_test_count: Number of final test records after feature selection
        feature_count: Number of final features
        lineage_written: 1 si las tres capas escribieron su linaje, 0 si alguna no pudo
        run_name: MLflow run name

    Returns:
        Summary metrics dictionary
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow not installed, skipping monitoring")
        return {}

    logger.info(f"Logging pipeline summary to MLflow: {run_name}")

    mlflow.set_experiment(ETL_EXPERIMENT)
    with mlflow.start_run(run_name=run_name):
        metrics = {
            "raw_records": raw_count,
            "enriched_records": enriched_count,
            "train_records": train_count,
            "test_records": test_count,
            "final_train_records": final_train_count,
            "final_test_records": final_test_count,
            "final_features": feature_count,
            "lineage_written": lineage_written,
            "enrichment_retention_pct": (enriched_count / raw_count * 100) if raw_count > 0 else 0,
            "total_final_records": final_train_count + final_test_count,
            "overall_retention_pct": ((final_train_count + final_test_count) / raw_count * 100)
            if raw_count > 0
            else 0,
        }

        log_metrics(metrics)

        logger.info("Pipeline summary logged successfully")
        return metrics
