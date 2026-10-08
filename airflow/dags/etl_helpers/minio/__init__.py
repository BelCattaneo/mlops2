"""
MinIO/S3 Utility Package

Helper functions for interacting with MinIO storage using boto3.
"""

from .client import (
    create_bucket_if_not_exists,
    enable_versioning,
    get_minio_client,
    set_bucket_lifecycle_policy,
)
from .operations import (
    check_file_exists,
    delete_object,
    download_from_minio,
    download_to_dataframe,
    list_objects,
    list_objects_with_times,
    upload_from_dataframe,
    upload_to_minio,
)

__all__ = [
    # Client
    "get_minio_client",
    "enable_versioning",
    "set_bucket_lifecycle_policy",
    "create_bucket_if_not_exists",
    # Operations
    "upload_to_minio",
    "download_from_minio",
    "check_file_exists",
    "list_objects",
    "list_objects_with_times",
    "delete_object",
    "download_to_dataframe",
    "upload_from_dataframe",
]
