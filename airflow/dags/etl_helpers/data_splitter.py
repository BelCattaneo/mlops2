"""
Data Splitting Functions

Functions for preprocessing and splitting Chicago crime data into train/test sets.
"""

import logging
from typing import Optional, Tuple

import pandas as pd
from sklearn.model_selection import train_test_split

from . import config

logger = logging.getLogger(__name__)


def preprocess_for_split(df: pd.DataFrame) -> pd.DataFrame:
    """
    Preprocess data before splitting into train/test.
    Removes duplicates, fills null values, and drops non-feature columns.

    Args:
        df: Raw enriched dataframe

    Returns:
        Preprocessed dataframe ready for splitting
    """
    logger.info("Preprocessing data for split...")

    try:
        initial_count = len(df)
        logger.info(f"Initial dataset: {initial_count} records")

        # Remove duplicates
        df_clean = df.drop_duplicates()
        duplicates_removed = initial_count - len(df_clean)

        if duplicates_removed > 0:
            logger.info(
                f"Removed {duplicates_removed} duplicate records "
                f"({100 * duplicates_removed / initial_count:.2f}%)"
            )
        else:
            logger.info("No duplicates found")

        # Log NaN summary across all columns
        nan_summary = df_clean.isna().sum()
        nan_cols = nan_summary[nan_summary > 0]
        if len(nan_cols) > 0:
            logger.warning(f"NaN values found in {len(nan_cols)} columns:")
            for col, count in nan_cols.items():
                logger.warning(
                    f"  {col}: {count} NaN ({100 * count / len(df_clean):.2f}%)"
                )

        # Fill null values in categorical columns
        categorical_fill_values = {
            "location_description": "UNKNOWN",
            "primary_type": "UNKNOWN",
            "fbi_code": "UNKNOWN",
            "nearest_police_station_district_name": "UNKNOWN",
        }

        df_clean = df_clean.copy()
        for col, fill_value in categorical_fill_values.items():
            if col in df_clean.columns:
                null_count = df_clean[col].isna().sum()
                if null_count > 0:
                    df_clean[col] = df_clean[col].fillna(fill_value)
                    logger.info(
                        f"Filled {null_count} NaN in '{col}' with '{fill_value}'"
                    )

        # Fill null values in numeric columns with median
        # Note: district is now frequency encoded (categorical), not filled with median
        numeric_fill_columns = ["beat", "ward", "community_area"]
        for col in numeric_fill_columns:
            if col in df_clean.columns:
                null_count = df_clean[col].isna().sum()
                if null_count > 0:
                    median_val = df_clean[col].median()
                    df_clean[col] = df_clean[col].fillna(median_val)
                    logger.info(
                        f"Filled {null_count} NaN in '{col}' with median: {median_val}"
                    )

        # Final NaN check - drop any remaining rows with NaN in critical columns
        remaining_nan = df_clean.isna().sum().sum()
        if remaining_nan > 0:
            logger.warning(
                f"Remaining NaN values: {remaining_nan}. Dropping affected rows..."
            )
            rows_before = len(df_clean)
            df_clean = df_clean.dropna()
            logger.info(
                f"Dropped {rows_before - len(df_clean)} rows with remaining NaN"
            )

        # Drop non-feature columns (temporal features already extracted)
        columns_to_drop = list(config.COLUMNS_TO_DROP_PREPROCESS)
        existing_drops = [col for col in columns_to_drop if col in df_clean.columns]
        if existing_drops:
            df_clean = df_clean.drop(columns=existing_drops)
            logger.info(f"Dropped non-feature columns: {existing_drops}")

        logger.info(f"Preprocessing completed: {len(df_clean)} records ready for split")
        return df_clean

    except Exception as e:
        logger.error(f"Error in preprocessing: {e}")
        raise


def split_train_test(
    df: pd.DataFrame,
    test_size: Optional[float] = None,
    random_state: Optional[int] = None,
    stratify_column: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split dataframe into stratified train and test sets.

    Args:
        df: Preprocessed dataframe
        test_size: Proportion of data for test set (default from config)
        random_state: Random seed for reproducibility (default from config)
        stratify_column: Column name to use for stratification (default from config)

    Returns:
        Tuple of (train_df, test_df)
    """
    # Use config defaults if not provided
    if test_size is None:
        test_size = config.SPLIT_TEST_SIZE
    if random_state is None:
        random_state = config.SPLIT_RANDOM_STATE
    if stratify_column is None:
        stratify_column = config.TARGET_COLUMN

    logger.info(
        f"Splitting data: {100 * (1 - test_size):.0f}% train, {100 * test_size:.0f}% test"
    )

    try:
        # Check if stratify column exists
        if stratify_column not in df.columns:
            logger.warning(
                f"Stratify column '{stratify_column}' not found. Performing random split."
            )
            stratify_data = None
        else:
            stratify_data = df[stratify_column]

            # Log class distribution
            class_dist = stratify_data.value_counts()
            logger.info(f"Class distribution in '{stratify_column}':")
            for value, count in class_dist.items():
                logger.info(f"  {value}: {count} ({100 * count / len(df):.2f}%)")

        # Perform split
        train_df, test_df = train_test_split(
            df, test_size=test_size, random_state=random_state, stratify=stratify_data
        )

        logger.info(
            f"Split completed: {len(train_df)} train records, {len(test_df)} test records"
        )

        # Verify stratification
        if stratify_data is not None:
            train_dist = train_df[stratify_column].value_counts(normalize=True)
            test_dist = test_df[stratify_column].value_counts(normalize=True)
            logger.info("Stratification verification:")
            for value in train_dist.index:
                logger.info(
                    f"  {value} - Train: {100 * train_dist[value]:.2f}%, "
                    f"Test: {100 * test_dist[value]:.2f}%"
                )

        return train_df, test_df

    except Exception as e:
        logger.error(f"Error in train/test split: {e}")
        raise
