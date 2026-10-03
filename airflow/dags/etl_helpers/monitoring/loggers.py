"""
MLflow Logging Functions

Functions for logging metrics and visualizations to MLflow for each pipeline stage.
"""

import logging
from typing import Dict, Optional, Any

import pandas as pd

from .mlflow_utils import (
    log_metrics,
    log_params,
    save_figure_and_log,
    get_value_distribution,
)
from .charts import (
    create_bar_chart,
    create_comparison_bar_chart,
    create_raw_data_overview_chart,
    create_correlation_heatmap,
    create_pipeline_flow_chart,
)

logger = logging.getLogger(__name__)

# Import config for default values
import sys  # noqa: E402
import os  # noqa: E402

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from etl_config import config  # noqa: E402


def log_raw_data_metrics(
    df: pd.DataFrame,
    run_name: str = "raw_data",
) -> Dict[str, Any]:
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

        fig = create_raw_data_overview_chart(df)
        save_figure_and_log(fig, "charts/raw_data_overview.png")

        logger.info("Raw data metrics logged successfully")
        return {
            "total_records": total_records,
            "arrest_rate": arrest_dist.get(True, 0) if "arrest" in df.columns else None,
        }


def log_split_metrics(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_column: Optional[str] = None,
    run_name: str = "split",
) -> Dict[str, Any]:
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

            # Generate comparison chart
            train_values = [train_dist.get(0, 0), train_dist.get(1, 0)]
            test_values = [test_dist.get(0, 0), test_dist.get(1, 0)]

            fig = create_comparison_bar_chart(
                train_values,
                test_values,
                labels=["Class 0", "Class 1"],
                label1="Train",
                label2="Test",
                title=f"Train/Test Class Distribution - {target_column}",
                xlabel="Class",
                ylabel="Percentage (%)",
            )
            save_figure_and_log(fig, "charts/split_distribution.png")

        log_metrics(metrics)

        logger.info("Split metrics logged successfully")
        return {
            "train_size": len(train_df),
            "test_size": len(test_df),
        }


def log_balance_metrics(
    original_df: pd.DataFrame,
    balanced_df: pd.DataFrame,
    target_column: Optional[str] = None,
    run_name: str = "balance",
) -> Dict[str, Any]:
    """
    Log data balancing metrics to MLflow.

    Args:
        original_df: Original training data
        balanced_df: Balanced training data
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

    logger.info(f"Logging balance metrics to MLflow: {run_name}")

    with mlflow.start_run(run_name=run_name):
        metrics = {
            "original_size": len(original_df),
            "balanced_size": len(balanced_df),
            "size_change_pct": (len(balanced_df) - len(original_df))
            / len(original_df)
            * 100,
        }

        if target_column in original_df.columns:
            orig_dist = get_value_distribution(original_df[target_column])
            bal_dist = get_value_distribution(balanced_df[target_column])

            for class_val, pct in orig_dist.items():
                metrics[f"original_class_{class_val}_pct"] = pct
            for class_val, pct in bal_dist.items():
                metrics[f"balanced_class_{class_val}_pct"] = pct

            orig_ratio = orig_dist.get(1, 0) / orig_dist.get(0, 1)
            bal_ratio = bal_dist.get(1, 0) / bal_dist.get(0, 1)
            metrics["original_class_ratio"] = orig_ratio
            metrics["balanced_class_ratio"] = bal_ratio

            # Generate comparison chart
            orig_values = [orig_dist.get(0, 0), orig_dist.get(1, 0)]
            bal_values = [bal_dist.get(0, 0), bal_dist.get(1, 0)]

            fig = create_comparison_bar_chart(
                orig_values,
                bal_values,
                labels=["Class 0", "Class 1"],
                label1="Before Balance",
                label2="After Balance",
                title=f"Class Distribution Before/After Balancing - {target_column}",
                xlabel="Class",
                ylabel="Percentage (%)",
            )
            save_figure_and_log(fig, "charts/balance_comparison.png")

        log_metrics(metrics)

        logger.info("Balance metrics logged successfully")
        return {
            "original_size": len(original_df),
            "balanced_size": len(balanced_df),
        }


def log_feature_selection_metrics(
    original_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    mi_scores_df: Optional[pd.DataFrame] = None,
    target_column: Optional[str] = None,
    run_name: str = "features",
) -> Dict[str, Any]:
    """
    Log feature selection metrics to MLflow.

    Args:
        original_df: Original dataframe before selection
        selected_df: Dataframe after feature selection
        mi_scores_df: Mutual information scores (optional)
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

    logger.info(f"Logging feature selection metrics to MLflow: {run_name}")

    with mlflow.start_run(run_name=run_name):
        orig_features = [c for c in original_df.columns if c != target_column]
        selected_features = [c for c in selected_df.columns if c != target_column]
        dropped_features = list(set(orig_features) - set(selected_features))

        metrics = {
            "original_features": len(orig_features),
            "selected_features": len(selected_features),
            "dropped_features": len(dropped_features),
            "feature_reduction_pct": (len(dropped_features) / len(orig_features)) * 100
            if len(orig_features) > 0
            else 0,
        }

        params = {
            "selected_features_list": ",".join(selected_features),
            "dropped_features_list": ",".join(dropped_features),
        }

        log_metrics(metrics)
        log_params(params)

        # Generate visualizations
        if mi_scores_df is not None:
            top_features = mi_scores_df.head(10)
            fig = create_bar_chart(
                values=top_features["mi_score"].values,
                labels=top_features["feature"].values,
                title="Top 10 Features by Mutual Information",
                xlabel="Mutual Information Score",
                ylabel="Feature",
                horizontal=True,
                figsize=(10, 8),
            )
            save_figure_and_log(fig, "charts/feature_importance.png")

        fig = create_correlation_heatmap(
            selected_df,
            title="Feature Correlation Heatmap (Final Dataset)",
        )
        if fig is not None:
            save_figure_and_log(fig, "charts/correlation_heatmap.png")

        logger.info("Feature selection metrics logged successfully")
        return {
            "selected_features": len(selected_features),
            "dropped_features": len(dropped_features),
        }


def log_pipeline_summary(
    raw_count: int,
    enriched_count: int,
    train_count: int,
    test_count: int,
    balanced_count: int,
    final_train_count: int,
    final_test_count: int,
    feature_count: int,
    run_name: str = "pipeline_summary",
) -> Dict[str, Any]:
    """
    Log overall pipeline summary showing data flow through all stages.

    Args:
        raw_count: Number of raw records
        enriched_count: Number of enriched records (after cleaning)
        train_count: Number of training records after split
        test_count: Number of test records after split
        balanced_count: Number of records after balancing
        final_train_count: Number of final training records after feature selection
        final_test_count: Number of final test records after feature selection
        feature_count: Number of final features
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

    with mlflow.start_run(run_name=run_name):
        metrics = {
            "raw_records": raw_count,
            "enriched_records": enriched_count,
            "train_records": train_count,
            "test_records": test_count,
            "balanced_records": balanced_count,
            "final_train_records": final_train_count,
            "final_test_records": final_test_count,
            "final_features": feature_count,
            "enrichment_retention_pct": (enriched_count / raw_count * 100)
            if raw_count > 0
            else 0,
            "balancing_change_pct": ((balanced_count - train_count) / train_count * 100)
            if train_count > 0
            else 0,
            "total_final_records": final_train_count + final_test_count,
            "overall_retention_pct": (
                (final_train_count + final_test_count) / raw_count * 100
            )
            if raw_count > 0
            else 0,
        }

        log_metrics(metrics)

        fig = create_pipeline_flow_chart(
            raw_count,
            enriched_count,
            train_count,
            test_count,
            balanced_count,
            final_train_count,
            final_test_count,
        )
        save_figure_and_log(fig, "charts/pipeline_flow.png")

        logger.info("Pipeline summary logged successfully")
        return metrics
