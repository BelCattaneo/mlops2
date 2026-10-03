"""
Feature Selection Functions

Functions for selecting relevant features using correlation analysis
and mutual information.
"""

import logging
from typing import List, Optional, Tuple

import pandas as pd
from sklearn.feature_selection import mutual_info_classif

from . import config

logger = logging.getLogger(__name__)


def remove_correlated_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    threshold: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Remove highly correlated features based on Pearson correlation.

    Based on analysis:
    - Remove Beat, Ward, Community Area (correlated with coordinates)
    - Remove Nearest_Police_Station_District_Name_freq (correlated with district)
    - Remove FBI_Code_freq (correlated with IUCR and Primary_Type)

    Args:
        train_df: Training dataframe
        test_df: Test dataframe
        threshold: Correlation threshold (default from config)

    Returns:
        Tuple of (train_filtered, test_filtered)
    """
    if threshold is None:
        threshold = config.CORRELATION_THRESHOLD

    logger.info("Removing highly correlated features...")

    # Use columns from config
    columns_to_drop = list(config.FEATURE_SELECTION_DROP)

    # Only drop columns that exist
    existing_drops = [col for col in columns_to_drop if col in train_df.columns]

    if not existing_drops:
        logger.warning("No correlated columns found to drop")
        return train_df, test_df

    train_filtered = train_df.drop(columns=existing_drops)
    test_filtered = test_df.drop(columns=existing_drops)

    logger.info(f"Dropped {len(existing_drops)} correlated features: {existing_drops}")
    logger.info(f"Remaining features: {train_filtered.shape[1]}")

    return train_filtered, test_filtered


def select_features_mutual_info(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_column: str,
    mi_threshold: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], pd.DataFrame]:
    """
    Select features using Mutual Information with threshold filtering.

    Args:
        train_df: Training dataframe with target
        test_df: Test dataframe with target
        target_column: Target column name
        mi_threshold: Minimum MI score to keep feature (default from config)

    Returns:
        Tuple of (train_selected, test_selected, selected_features, mi_scores_df)
    """
    if mi_threshold is None:
        mi_threshold = config.MI_THRESHOLD

    logger.info(
        f"Applying Mutual Information feature selection (threshold={mi_threshold})..."
    )

    # Separate features and target
    X_train = train_df.drop(columns=[target_column])
    y_train = train_df[target_column]
    X_test = test_df.drop(columns=[target_column])

    # Calculate mutual information
    mi_scores = mutual_info_classif(
        X_train, y_train, random_state=config.SPLIT_RANDOM_STATE
    )

    # Create scores DataFrame
    mi_scores_df = pd.DataFrame(
        {"feature": X_train.columns, "mi_score": mi_scores}
    ).sort_values("mi_score", ascending=False)

    # Select features above threshold
    selected_features = mi_scores_df[mi_scores_df["mi_score"] > mi_threshold][
        "feature"
    ].tolist()

    logger.info("Mutual Information results:")
    logger.info(f"  Features before: {len(X_train.columns)}")
    logger.info(f"  Features after: {len(selected_features)}")
    logger.info(f"  Features removed: {len(X_train.columns) - len(selected_features)}")

    # Log top features
    logger.info("\nTop 10 features by MI score:")
    for _, row in mi_scores_df.head(10).iterrows():
        logger.info(f"  {row['feature']:50s} | MI: {row['mi_score']:.4f}")

    # Filter datasets
    train_selected = X_train[selected_features].copy()
    train_selected[target_column] = y_train

    test_selected = X_test[selected_features].copy()
    test_selected[target_column] = test_df[target_column]

    return train_selected, test_selected, selected_features, mi_scores_df


def select_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_column: Optional[str] = None,
    mi_threshold: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Apply complete feature selection pipeline:
    1. Remove correlated features (correlation analysis)
    2. Select features using Mutual Information

    Note: Mutual Information handles both numerical and categorical features
    effectively, capturing both linear and non-linear relationships.

    Args:
        train_df: Training dataframe
        test_df: Test dataframe
        target_column: Target column name (default from config)
        mi_threshold: MI score threshold (default from config)

    Returns:
        Tuple of (train_selected, test_selected, mi_scores_df)
    """
    # Use config defaults if not provided
    if target_column is None:
        target_column = config.TARGET_COLUMN
    if mi_threshold is None:
        mi_threshold = config.MI_THRESHOLD

    logger.info("Starting feature selection pipeline...")
    logger.info(f"Initial shapes: train={train_df.shape}, test={test_df.shape}")

    # Step 1: Remove correlated features
    train_df, test_df = remove_correlated_features(train_df, test_df)
    logger.info(
        f"After correlation filtering: train={train_df.shape}, test={test_df.shape}"
    )

    # Step 2: Mutual Information selection
    train_selected, test_selected, selected_features, mi_scores = (
        select_features_mutual_info(train_df, test_df, target_column, mi_threshold)
    )

    logger.info("\nFeature selection completed:")
    logger.info(f"  Final train shape: {train_selected.shape}")
    logger.info(f"  Final test shape: {test_selected.shape}")
    logger.info(f"  Selected features: {len(selected_features)}")
    logger.info(f"  Feature list: {selected_features}")

    return train_selected, test_selected, mi_scores
