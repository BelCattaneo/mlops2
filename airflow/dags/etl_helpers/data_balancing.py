"""
Data Balancing Functions

Functions for balancing the training dataset using SMOTE and undersampling.
"""

import logging
from typing import Optional

import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import RandomUnderSampler
from imblearn.pipeline import Pipeline

from . import config
from .exceptions import DataValidationError

logger = logging.getLogger(__name__)


def balance_data(
    train_df: pd.DataFrame,
    target_column: Optional[str] = None,
) -> pd.DataFrame:
    """
    Balance training data using combined SMOTE + RandomUnderSampler strategy.

    Strategy:
    1. SMOTE (oversample to 0.5): Generate synthetic samples for minority class
       - Minority class will be 50% of majority class size
    2. RandomUnderSampler (undersample to 0.8): Reduce majority class
       - Final ratio: minority = 80% of majority

    Args:
        train_df: Training dataframe
        target_column: Target column name (default from config)

    Returns:
        Balanced training dataframe

    Raises:
        DataValidationError: If data contains NaN or non-numeric values
    """
    # Use config default if not provided
    if target_column is None:
        target_column = config.TARGET_COLUMN

    logger.info("Starting data balancing...")

    # Separate features and target
    if target_column not in train_df.columns:
        logger.error(f"Target column '{target_column}' not found in DataFrame")
        raise DataValidationError(f"Target column '{target_column}' not found")

    X = train_df.drop(columns=[target_column])
    y = train_df[target_column]

    # Validate: check for non-numeric columns before SMOTE
    non_numeric_cols = X.select_dtypes(include=["object"]).columns.tolist()
    if non_numeric_cols:
        logger.error(f"Non-numeric columns found: {non_numeric_cols}")
        logger.error(f"Column types: {X[non_numeric_cols].dtypes.to_dict()}")
        logger.error(f"Sample values: {X[non_numeric_cols].head(1).to_dict('records')}")
        raise DataValidationError(
            f"Cannot balance data with non-numeric columns: {non_numeric_cols}. "
            f"All features must be numeric for SMOTE."
        )

    # Validate: check for NaN values before SMOTE
    # NaN values should have been handled upstream (enrichment, encoding steps)
    # If we find NaN here, it indicates a bug in the pipeline
    nan_counts = X.isna().sum()
    if nan_counts.any():
        nan_cols = nan_counts[nan_counts > 0].to_dict()
        logger.error(
            f"NaN values found in columns (this should not happen): {nan_cols}"
        )
        logger.error(
            "NaN values should be handled in upstream steps (enrichment, encoding)"
        )
        raise DataValidationError(
            f"Unexpected NaN values in {len(nan_cols)} columns: {list(nan_cols.keys())}. "
            f"Check data_enrichment.py and data_encoding.py for missing NaN handling."
        )

    # Log original class distribution
    original_counts = y.value_counts()
    original_ratio = original_counts.min() / original_counts.max()
    logger.info("Original class distribution:")
    class_0_count = original_counts.loc[0] if 0 in original_counts.index else 0
    class_1_count = original_counts.loc[1] if 1 in original_counts.index else 0
    logger.info(f"  Class 0: {class_0_count} ({100 * class_0_count / len(y):.1f}%)")
    logger.info(f"  Class 1: {class_1_count} ({100 * class_1_count / len(y):.1f}%)")
    logger.info(f"  Original ratio (min/max): {original_ratio:.3f}")

    # Create balancing pipeline (using config values)
    # Step 1: SMOTE - oversample minority to configured ratio of majority
    over = SMOTE(
        sampling_strategy=config.SMOTE_SAMPLING_STRATEGY,
        random_state=config.BALANCING_RANDOM_STATE,
    )

    # Step 2: RandomUnderSampler - reduce majority to configured ratio
    under = RandomUnderSampler(
        sampling_strategy=config.UNDERSAMPLE_STRATEGY,
        random_state=config.BALANCING_RANDOM_STATE,
    )

    # Combine both steps
    steps = [("oversample", over), ("undersample", under)]
    pipeline = Pipeline(steps=steps)

    # Apply balancing
    logger.info("Applying SMOTE + RandomUnderSampler...")
    X_resampled, y_resampled = pipeline.fit_resample(X, y)

    # Log final class distribution
    final_counts = y_resampled.value_counts()
    final_ratio = final_counts.min() / final_counts.max()
    logger.info("Balanced class distribution:")
    final_class_0 = final_counts.loc[0] if 0 in final_counts.index else 0
    final_class_1 = final_counts.loc[1] if 1 in final_counts.index else 0
    logger.info(
        f"  Class 0: {final_class_0} ({100 * final_class_0 / len(y_resampled):.1f}%)"
    )
    logger.info(
        f"  Class 1: {final_class_1} ({100 * final_class_1 / len(y_resampled):.1f}%)"
    )
    logger.info(f"  Final ratio (min/max): {final_ratio:.3f}")

    # Combine back into DataFrame
    balanced_df = pd.concat([X_resampled, y_resampled], axis=1)

    logger.info(f"Balancing completed: {len(train_df)} -> {len(balanced_df)} samples")

    return balanced_df
