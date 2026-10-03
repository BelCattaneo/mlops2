"""
Data Scaling Functions

Functions for scaling numerical features using StandardScaler.
"""

import logging
from typing import List, Optional, Tuple

import pandas as pd
from sklearn.preprocessing import StandardScaler

from . import config
from .exceptions import DataValidationError

logger = logging.getLogger(__name__)


def scale_data(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Scale numerical features using StandardScaler.
    Fits scaler on train data and transforms both train and test.

    Args:
        train_df: Training dataframe
        test_df: Test dataframe
        columns: Columns to scale (default: spatial columns from config)

    Returns:
        Tuple of (train_scaled, test_scaled)

    Raises:
        DataValidationError: If data contains NaN values
    """
    if columns is None:
        columns = list(config.SCALING_COLUMNS)

    logger.info(f"Scaling {len(columns)} numerical features...")

    train_scaled = train_df.copy()
    test_scaled = test_df.copy()

    # Check which columns exist
    existing_columns = [col for col in columns if col in train_df.columns]
    missing_columns = [col for col in columns if col not in train_df.columns]

    if missing_columns:
        logger.warning(f"Columns not found: {missing_columns}")

    if not existing_columns:
        logger.warning("No columns to scale found in DataFrame")
        return train_scaled, test_scaled

    # Extract columns to scale
    train_subset = train_df[existing_columns]
    test_subset = test_df[existing_columns]

    # Validate: check for NaN values before scaling
    train_nan = train_subset.isna().sum()
    test_nan = test_subset.isna().sum()

    if train_nan.any():
        nan_cols = train_nan[train_nan > 0].to_dict()
        logger.error(f"NaN values found in train data before scaling: {nan_cols}")
        raise DataValidationError(
            f"Cannot scale data with NaN values. Columns with NaN: {list(nan_cols.keys())}"
        )

    if test_nan.any():
        nan_cols = test_nan[test_nan > 0].to_dict()
        logger.error(f"NaN values found in test data before scaling: {nan_cols}")
        raise DataValidationError(
            f"Cannot scale data with NaN values. Columns with NaN: {list(nan_cols.keys())}"
        )

    # Fit scaler on train data
    scaler = StandardScaler()
    train_array = scaler.fit_transform(train_subset)
    test_array = scaler.transform(test_subset)

    # Create scaled DataFrames with _standardized suffix
    train_scaled_df = pd.DataFrame(
        train_array,
        columns=[f"{col}_standardized" for col in existing_columns],
        index=train_df.index,
    )
    test_scaled_df = pd.DataFrame(
        test_array,
        columns=[f"{col}_standardized" for col in existing_columns],
        index=test_df.index,
    )

    # Join scaled columns and drop originals
    train_scaled = train_scaled.join(train_scaled_df)
    test_scaled = test_scaled.join(test_scaled_df)

    train_scaled = train_scaled.drop(columns=existing_columns)
    test_scaled = test_scaled.drop(columns=existing_columns)

    logger.info(f"Scaled {len(existing_columns)} columns using StandardScaler")
    logger.info(f"  Train shape: {train_scaled.shape}")
    logger.info(f"  Test shape: {test_scaled.shape}")

    return train_scaled, test_scaled
