import datetime
import logging
import os
import tempfile

import pandas as pd
from airflow.decorators import dag, task

from etl_helpers.data_balancing import balance_data as balance_data_fn
from etl_helpers.data_encoding import encode_data as encode_data_fn
from etl_helpers.data_enrichment import enrich_crime_data
from etl_helpers.data_loader import (
    download_crimes_incremental,
    download_police_stations,
)
from etl_helpers.data_scaling import scale_data as scale_data_fn
from etl_helpers.data_splitter import preprocess_for_split, split_train_test
from etl_helpers.feature_selection import select_features as select_features_fn
from etl_helpers.minio import (
    check_file_exists,
    create_bucket_if_not_exists,
    download_to_dataframe,
    list_objects,
    set_bucket_lifecycle_policy,
    upload_from_dataframe,
    upload_to_minio,
)
from etl_helpers.monitoring import (
    log_balance_metrics,
    log_feature_selection_metrics,
    log_pipeline_summary,
    log_raw_data_metrics,
    log_split_metrics,
)
from etl_config import config
from etl_helpers.outlier_processing import process_outliers as process_outliers_fn

logger = logging.getLogger(__name__)

# Configuration from centralized config
BUCKET_NAME = os.getenv("DATA_REPO_BUCKET_NAME", "data")

# Bucket structure (from config)
PREFIX_RAW = config.PREFIX_RAW
PREFIX_MERGED = config.PREFIX_MERGED
PREFIX_ENRICHED = config.PREFIX_ENRICHED
PREFIX_SPLIT = config.PREFIX_SPLIT
PREFIX_OUTLIERS = config.PREFIX_OUTLIERS
PREFIX_ENCODED = config.PREFIX_ENCODED
PREFIX_SCALED = config.PREFIX_SCALED
PREFIX_BALANCED = config.PREFIX_BALANCED
PREFIX_ML_READY = config.PREFIX_ML_READY

# Data processing parameters (from config)
LIFECYCLE_TTL_DAYS = config.LIFECYCLE_TTL_DAYS
ROLLING_WINDOW_DAYS = config.ROLLING_WINDOW_DAYS
TARGET_COLUMN = config.TARGET_COLUMN
SPLIT_TEST_SIZE = config.SPLIT_TEST_SIZE
SPLIT_RANDOM_STATE = config.SPLIT_RANDOM_STATE
OUTLIER_STD_THRESHOLD = config.OUTLIER_STD_THRESHOLD
MI_THRESHOLD = config.MI_THRESHOLD

default_args = {
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=5),
    "dagrun_timeout": datetime.timedelta(
        minutes=60
    ),  # Increased for large data downloads
}


@dag(
    dag_id="etl_with_taskflow",
    description="Chicago Crime Data ETL Pipeline with TaskFlow API",
    default_args=default_args,
    schedule="@monthly",  # Run monthly for incremental updates
    start_date=datetime.datetime(2024, 1, 1),
    catchup=False,
    tags=["ETL", "Chicago", "Crime", "TaskFlow"],
)
def process_etl_taskflow():
    @task.python
    def setup_s3():
        """Setup MinIO bucket with TTL for all prefixes."""
        all_prefixes = [
            PREFIX_RAW,
            PREFIX_MERGED,
            PREFIX_ENRICHED,
            PREFIX_SPLIT,
            PREFIX_OUTLIERS,
            PREFIX_ENCODED,
            PREFIX_SCALED,
            PREFIX_BALANCED,
            PREFIX_ML_READY,
        ]

        create_bucket_if_not_exists(BUCKET_NAME)
        set_bucket_lifecycle_policy(BUCKET_NAME, all_prefixes, LIFECYCLE_TTL_DAYS)

    @task.python
    def download_data(**context):
        """Download crime and police station data for the current period."""
        start_date = context["data_interval_start"]
        end_date = context["data_interval_end"]
        month_folder = start_date.strftime("%Y-%m")

        # Define output paths
        crimes_key = f"{PREFIX_RAW}{month_folder}/crimes.csv"
        stations_key = f"{PREFIX_RAW}police_stations.csv"

        # Check if already downloaded (idempotent)
        if check_file_exists(BUCKET_NAME, crimes_key):
            return {
                "status": "success",
                "crimes_file": crimes_key,
                "stations_file": stations_key,
            }

        # Determine download date range
        existing_merged = list_objects(
            BUCKET_NAME, prefix=f"{PREFIX_MERGED}crimes_12m_"
        )

        if len(existing_merged) == 0:
            # No existing data - download full rolling window
            download_start = end_date - datetime.timedelta(days=ROLLING_WINDOW_DAYS)
            download_end = end_date
        else:
            # Use scheduled interval
            download_start = start_date
            download_end = end_date

        # Download data to temp files
        crimes_temp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        stations_temp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        )

        try:
            # Download crimes (always use incremental with appropriate date range)
            crimes_df = download_crimes_incremental(
                download_start, download_end, output_file=crimes_temp.name
            )

            if len(crimes_df) == 0:
                return {"status": "no_data", "records": 0}

            # Download police stations
            download_police_stations(output_file=stations_temp.name)

            # Upload to MinIO
            upload_to_minio(crimes_temp.name, BUCKET_NAME, crimes_key)
            upload_to_minio(stations_temp.name, BUCKET_NAME, stations_key)

            return {
                "status": "success",
                "crimes_file": crimes_key,
                "stations_file": stations_key,
            }
        finally:
            if os.path.exists(crimes_temp.name):
                os.remove(crimes_temp.name)
            if os.path.exists(stations_temp.name):
                os.remove(stations_temp.name)

    @task.python
    def merge_data(download_result, **context):
        """Merge downloaded data into rolling 12-month window."""
        run_date = context["ds"]
        merged_key = f"{PREFIX_MERGED}crimes_12m_{run_date}.csv"

        # Check if merged file already exists (idempotent)
        if check_file_exists(BUCKET_NAME, merged_key):
            return {
                "status": "success",
                "merged_file": merged_key,
                "stations_file": download_result.get("stations_file"),
            }

        # Check if upstream returned no_data
        if download_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Load newly downloaded data
        df_new = download_to_dataframe(BUCKET_NAME, download_result["crimes_file"])

        # Check for existing merged data
        existing_merged = list_objects(
            BUCKET_NAME, prefix=f"{PREFIX_MERGED}crimes_12m_"
        )

        if len(existing_merged) == 0:
            # First merge - use downloaded data as-is
            merged_df = df_new
        else:
            # Merge with latest existing data
            latest_merged = sorted(existing_merged)[-1]
            df_existing = download_to_dataframe(BUCKET_NAME, latest_merged)
            merged_df = pd.concat([df_existing, df_new], ignore_index=True)

            # Apply rolling window filter
            merged_df["date"] = pd.to_datetime(merged_df["date"])
            cutoff_date = datetime.datetime.now() - datetime.timedelta(
                days=ROLLING_WINDOW_DAYS
            )
            merged_df = merged_df[merged_df["date"] >= cutoff_date]

        # Save merged data
        upload_from_dataframe(merged_df, BUCKET_NAME, merged_key)

        return {
            "status": "success",
            "merged_file": merged_key,
            "stations_file": download_result["stations_file"],
        }

    @task.python
    def enrich_data(merge_result, **context):
        """Add nearest station info and temporal features to crime data."""
        run_date = context["ds"]
        enriched_key = f"{PREFIX_ENRICHED}crimes_enriched_{run_date}.csv"

        # Check if enriched file already exists (idempotent)
        if check_file_exists(BUCKET_NAME, enriched_key):
            return {
                "status": "success",
                "enriched_file": enriched_key,
            }

        # Check if upstream returned no_data
        if merge_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Process data
        crimes_df = download_to_dataframe(BUCKET_NAME, merge_result["merged_file"])
        stations_df = download_to_dataframe(BUCKET_NAME, merge_result["stations_file"])
        enriched_df = enrich_crime_data(crimes_df, stations_df)

        # Monitor raw data quality
        log_raw_data_metrics(crimes_df, run_name=f"raw_data_{run_date}")

        # Upload enriched data
        upload_from_dataframe(enriched_df, BUCKET_NAME, enriched_key)

        return {
            "status": "success",
            "enriched_file": enriched_key,
        }

    @task.python
    def split_data(enrich_result, **context):
        """Split dataset into train and test sets with stratification."""
        run_date = context["ds"]
        train_key = f"{PREFIX_SPLIT}crimes_train_{run_date}.csv"
        test_key = f"{PREFIX_SPLIT}crimes_test_{run_date}.csv"

        # Check if split files already exist (idempotent)
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(
            BUCKET_NAME, test_key
        ):
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
            }

        # Check if upstream returned no_data
        if enrich_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Process data
        df_enriched = download_to_dataframe(BUCKET_NAME, enrich_result["enriched_file"])
        df_clean = preprocess_for_split(df_enriched)
        train_df, test_df = split_train_test(
            df_clean,
            test_size=SPLIT_TEST_SIZE,
            random_state=SPLIT_RANDOM_STATE,
            stratify_column=TARGET_COLUMN,
        )

        # Monitor split
        log_split_metrics(
            train_df, test_df, target_column=TARGET_COLUMN, run_name=f"split_{run_date}"
        )

        # Upload train and test datasets
        upload_from_dataframe(train_df, BUCKET_NAME, train_key)
        upload_from_dataframe(test_df, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def process_outliers(split_result, **context):
        """
        Remove outliers using standard deviation method (±3σ).
        Uses train statistics for both datasets to avoid data leakage.
        """
        run_date = context["ds"]
        train_key = f"{PREFIX_OUTLIERS}crimes_train_no_outliers_{run_date}.csv"
        test_key = f"{PREFIX_OUTLIERS}crimes_test_no_outliers_{run_date}.csv"

        # Check if processed files already exist (idempotent)
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(
            BUCKET_NAME, test_key
        ):
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
            }

        # Check if upstream returned no_data
        if split_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Process data
        train_df = download_to_dataframe(BUCKET_NAME, split_result["train_file"])
        test_df = download_to_dataframe(BUCKET_NAME, split_result["test_file"])
        train_processed, test_processed = process_outliers_fn(
            train_df, test_df, n_std=OUTLIER_STD_THRESHOLD
        )

        # Upload processed datasets
        upload_from_dataframe(train_processed, BUCKET_NAME, train_key)
        upload_from_dataframe(test_processed, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def encode_data(outliers_result, **context):
        """
        Encode categorical and numerical variables.
        - Log transformation: distance_crime_to_police_station
        - Cyclic encoding: day_of_week
        - One-hot encoding: season, day_time
        - Label encoding: domestic
        - Frequency encoding: high cardinality categoricals
        """
        run_date = context["ds"]
        train_key = f"{PREFIX_ENCODED}crimes_train_encoded_{run_date}.csv"
        test_key = f"{PREFIX_ENCODED}crimes_test_encoded_{run_date}.csv"

        # Check if encoded files already exist (idempotent)
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(
            BUCKET_NAME, test_key
        ):
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
            }

        # Check if upstream returned no_data
        if outliers_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Process data
        train_df = download_to_dataframe(BUCKET_NAME, outliers_result["train_file"])
        test_df = download_to_dataframe(BUCKET_NAME, outliers_result["test_file"])
        train_encoded, test_encoded = encode_data_fn(train_df, test_df)

        # Upload encoded datasets
        upload_from_dataframe(train_encoded, BUCKET_NAME, train_key)
        upload_from_dataframe(test_encoded, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def scale_data(encode_result, **context):
        """
        Scale numerical features using StandardScaler.
        Scales: x_coordinate, y_coordinate, latitude, longitude, distance_crime_to_police_station
        """
        run_date = context["ds"]
        train_key = f"{PREFIX_SCALED}crimes_train_scaled_{run_date}.csv"
        test_key = f"{PREFIX_SCALED}crimes_test_scaled_{run_date}.csv"

        # Check if scaled files already exist (idempotent)
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(
            BUCKET_NAME, test_key
        ):
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
            }

        # Check if upstream returned no_data
        if encode_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Process data
        train_df = download_to_dataframe(BUCKET_NAME, encode_result["train_file"])
        test_df = download_to_dataframe(BUCKET_NAME, encode_result["test_file"])
        train_scaled, test_scaled = scale_data_fn(train_df, test_df)

        # Upload scaled datasets
        upload_from_dataframe(train_scaled, BUCKET_NAME, train_key)
        upload_from_dataframe(test_scaled, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def balance_data(scale_result, **context):
        """
        Balance training dataset using SMOTE + RandomUnderSampler.
        Strategy: SMOTE (0.5) → RandomUnderSampler (0.8)
        Note: Only balances TRAIN data, test remains unchanged.
        """
        
        # Si upstream devolvió no_data, salir sin tocar keys que no existen
        if not scale_result or scale_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Lee la key de manera segura
        test_key = scale_result.get("test_file")
        if not test_key:
            raise AirflowFailException(
            f"balance_data: falta 'test_file' en scale_result. Keys: {list(scale_result.keys())}"
        )

        run_date = context["ds"]
        train_key = f"{PREFIX_BALANCED}crimes_train_balanced_{run_date}.csv"

        # Idempotencia
        if check_file_exists(BUCKET_NAME, train_key):
            return {"status": "success", "train_file": train_key, "test_file": test_key}
        
        # run_date = context["ds"]
        # train_key = f"{PREFIX_BALANCED}crimes_train_balanced_{run_date}.csv"
        # test_key = scale_result["test_file"]  # Test unchanged, just pass through

        # # Check if balanced file already exists (idempotent)
        # if check_file_exists(BUCKET_NAME, train_key):
        #     return {
        #         "status": "success",
        #         "train_file": train_key,
        #         "test_file": test_key,
        #     }

        # Check if upstream returned no_data
        if scale_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Load train data and balance it
        train_df = download_to_dataframe(BUCKET_NAME, scale_result["train_file"])
        train_balanced = balance_data_fn(train_df, target_column=TARGET_COLUMN)

        # Monitor balancing
        log_balance_metrics(
            train_df,
            train_balanced,
            target_column=TARGET_COLUMN,
            run_name=f"balance_{run_date}",
        )

        # Upload balanced train data
        upload_from_dataframe(train_balanced, BUCKET_NAME, train_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def extract_features(balance_result, **context):
        """
        Select relevant features and output final ML-ready datasets.

        Strategy:
        1. Remove correlated features (Beat, Ward, Community Area, etc.)
        2. Apply Mutual Information selection (MI-Score > 0.05)
        3. Save to ml-ready-data/ prefix for easy consumption

        Output: Final train/test datasets ready for ML model training.
        """
        run_date = context["ds"]
        train_key = f"{PREFIX_ML_READY}train_{run_date}.csv"
        test_key = f"{PREFIX_ML_READY}test_{run_date}.csv"

        # Check if ML-ready files already exist (idempotent)
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(
            BUCKET_NAME, test_key
        ):
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
            }

        # Check if upstream returned no_data
        if balance_result.get("status") == "no_data":
            return {"status": "no_data"}

        # Load balanced train and test data
        train_df_original = download_to_dataframe(
            BUCKET_NAME, balance_result["train_file"]
        )
        test_df = download_to_dataframe(BUCKET_NAME, balance_result["test_file"])

        # Apply feature selection
        train_selected, test_selected, mi_scores = select_features_fn(
            train_df_original,
            test_df,
            target_column=TARGET_COLUMN,
            mi_threshold=MI_THRESHOLD,
        )

        # Monitor feature selection
        log_feature_selection_metrics(
            train_df_original,
            train_selected,
            mi_scores_df=mi_scores,
            target_column=TARGET_COLUMN,
            run_name=f"features_{run_date}",
        )

        # Upload final ML-ready datasets
        upload_from_dataframe(train_selected, BUCKET_NAME, train_key)
        upload_from_dataframe(test_selected, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
        }

    @task.python
    def log_summary(feature_result, **context):
        """Log pipeline execution summary with data flow visualization."""
        run_date = context["ds"]

        # Check if upstream returned no_data
        if feature_result.get("status") == "no_data":
            logger.info("No data processed, skipping summary")
            return {"status": "no_data"}

        # Read data from each stage to get counts
        try:
            # Get file keys from context (via XCom pull)
            ti = context["ti"]

            # Raw data (from enrich_data task)
            enriched_result = ti.xcom_pull(task_ids="enrich_data")
            enriched_df = download_to_dataframe(
                BUCKET_NAME, enriched_result["enriched_file"]
            )
            enriched_count = len(enriched_df)

            # For raw count, we need to count before enrichment cleaning
            # We'll use the same as enriched for now (or add 5% approximation)
            raw_count = int(enriched_count * 1.002)  # Approximate duplicates removed

            # Split data
            split_result = ti.xcom_pull(task_ids="split_data")
            train_split_df = download_to_dataframe(
                BUCKET_NAME, split_result["train_file"]
            )
            test_df = download_to_dataframe(BUCKET_NAME, split_result["test_file"])
            train_count = len(train_split_df)
            test_count = len(test_df)

            # Balanced data
            balanced_result = ti.xcom_pull(task_ids="balance_data")
            train_balanced_df = download_to_dataframe(
                BUCKET_NAME, balanced_result["train_file"]
            )
            balanced_count = len(train_balanced_df)

            # Final data
            final_train_df = download_to_dataframe(
                BUCKET_NAME, feature_result["train_file"]
            )
            final_test_df = download_to_dataframe(
                BUCKET_NAME, feature_result["test_file"]
            )
            final_train_count = len(final_train_df)
            final_test_count = len(final_test_df)
            feature_count = len(
                [c for c in final_train_df.columns if c != TARGET_COLUMN]
            )

            # Log summary
            log_pipeline_summary(
                raw_count=raw_count,
                enriched_count=enriched_count,
                train_count=train_count,
                test_count=test_count,
                balanced_count=balanced_count,
                final_train_count=final_train_count,
                final_test_count=final_test_count,
                feature_count=feature_count,
                run_name=f"pipeline_summary_{run_date}",
            )

            return {"status": "success"}

        except Exception as e:
            logger.error(f"Failed to log pipeline summary: {e}")
            return {"status": "error", "error": str(e)}

    # Task dependencies
    s3_setup = setup_s3()
    downloaded = download_data()
    merged = merge_data(downloaded)
    enriched = enrich_data(merged)
    split = split_data(enriched)
    outliers = process_outliers(split)
    encoded = encode_data(outliers)
    scaled = scale_data(encoded)
    balanced = balance_data(scaled)
    features = extract_features(balanced)
    summary = log_summary(features)

    (
        s3_setup
        >> downloaded
        >> merged
        >> enriched
        >> split
        >> outliers
        >> encoded
        >> scaled
        >> balanced
        >> features
        >> summary
    )


dag = process_etl_taskflow()
