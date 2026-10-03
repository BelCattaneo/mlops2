"""
MinIO/S3 Utility Package

Helper functions for interacting with MinIO storage using boto3.
"""

from .client import (
    get_minio_client,
    set_bucket_lifecycle_policy,
    create_bucket_if_not_exists,
)

from .operations import (
    upload_to_minio,
    download_from_minio,
    check_file_exists,
    list_objects,
    delete_object,
    download_to_dataframe,
    upload_from_dataframe,
)

__all__ = [
    # Client
    "get_minio_client",
    "set_bucket_lifecycle_policy",
    "create_bucket_if_not_exists",
    # Operations
    "upload_to_minio",
    "download_from_minio",
    "check_file_exists",
    "list_objects",
    "delete_object",
    "download_to_dataframe",
    "upload_from_dataframe",
]
