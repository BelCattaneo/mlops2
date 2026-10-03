"""
ETL Helper Modules for Chicago Crime Data Pipeline

Utility functions for:
- MinIO/S3 operations (minio)
- Data loading from Socrata API (data_loader)
- Data preprocessing and transformations
- Monitoring and MLflow logging (monitoring)
"""

import os
import sys

# Setup path once for all modules - enables importing etl_config from parent directory
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Re-export config for convenience
from etl_config import config  # noqa: E402

# Re-export exceptions
from .exceptions import (  # noqa: E402
    DataLoadError,
    DataValidationError,
    EnrichmentError,
    ETLError,
    FeatureEngineeringError,
    MinIOError,
)

# Re-export MinIO functions for backward compatibility
from .minio import (  # noqa: E402
    check_file_exists,
    create_bucket_if_not_exists,
    delete_object,
    download_from_minio,
    download_to_dataframe,
    get_minio_client,
    list_objects,
    set_bucket_lifecycle_policy,
    upload_from_dataframe,
    upload_to_minio,
)

# Re-export monitoring functions for backward compatibility
from .monitoring import (  # noqa: E402
    log_balance_metrics,
    log_feature_selection_metrics,
    log_raw_data_metrics,
    log_split_metrics,
)

__version__ = "2.0.0"

__all__ = [
    # Config
    "config",
    # MinIO
    "get_minio_client",
    "set_bucket_lifecycle_policy",
    "create_bucket_if_not_exists",
    "upload_to_minio",
    "download_from_minio",
    "check_file_exists",
    "list_objects",
    "delete_object",
    "download_to_dataframe",
    "upload_from_dataframe",
    # Monitoring
    "log_raw_data_metrics",
    "log_split_metrics",
    "log_balance_metrics",
    "log_feature_selection_metrics",
    # Exceptions
    "ETLError",
    "DataValidationError",
    "MinIOError",
    "DataLoadError",
    "EnrichmentError",
    "FeatureEngineeringError",
]
