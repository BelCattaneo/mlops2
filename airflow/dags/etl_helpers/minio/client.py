"""
MinIO Client and Bucket Management

Functions for initializing MinIO client and managing buckets.
"""

import os
import logging
from typing import List, Optional, Union

import boto3
from botocore.exceptions import ClientError

from ..exceptions import MinIOError

logger = logging.getLogger(__name__)


def get_minio_client() -> boto3.client:
    """
    Initialize and return a boto3 S3 client configured for MinIO.

    Reads configuration from environment variables:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - MLFLOW_S3_ENDPOINT_URL (defaults to http://s3:9000)

    Returns:
        boto3.client: Configured S3 client for MinIO

    Raises:
        MinIOError: If client initialization fails
    """
    try:
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "minio")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
        endpoint_url = os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://s3:9000")

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

        logger.info(f"MinIO client initialized with endpoint: {endpoint_url}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize MinIO client: {e}")
        raise MinIOError(f"Failed to initialize MinIO client: {e}") from e


def set_bucket_lifecycle_policy(
    bucket_name: str,
    prefixes: Union[List[str], str],
    expiration_days: int,
) -> bool:
    """
    Set lifecycle policy to automatically delete objects after specified days.

    Args:
        bucket_name: Name of the MinIO bucket
        prefixes: Prefix(es) for objects to apply policy
        expiration_days: Number of days after which objects are deleted

    Returns:
        True if policy set successfully

    Raises:
        MinIOError: If setting lifecycle policy fails
    """
    client = get_minio_client()

    if isinstance(prefixes, str):
        prefixes = [prefixes]

    rules = []
    for prefix in prefixes:
        rules.append(
            {
                "ID": f"Delete-{prefix.replace('/', '-')}-after-{expiration_days}-days",
                "Status": "Enabled",
                "Filter": {"Prefix": prefix},
                "Expiration": {"Days": expiration_days},
            }
        )

    lifecycle_config = {"Rules": rules}

    try:
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name, LifecycleConfiguration=lifecycle_config
        )
        logger.info(
            f"Lifecycle policy set for '{bucket_name}': "
            f"{len(prefixes)} prefixes with {expiration_days} days TTL"
        )
        return True
    except Exception as e:
        logger.error(f"Error setting lifecycle policy: {e}")
        raise MinIOError(f"Error setting lifecycle policy: {e}") from e


def create_bucket_if_not_exists(
    bucket_name: str,
    lifecycle_prefix: Optional[str] = None,
    lifecycle_days: Optional[int] = None,
) -> bool:
    """
    Create a MinIO bucket if it doesn't already exist.
    Optionally set lifecycle policy for automatic file deletion.

    Args:
        bucket_name: Name of the bucket to create
        lifecycle_prefix: Prefix for lifecycle policy (e.g., 'raw-data/')
        lifecycle_days: Days before automatic deletion (TTL)

    Returns:
        True if bucket exists or was created successfully

    Raises:
        MinIOError: If bucket creation or check fails
    """
    client = get_minio_client()

    try:
        client.head_bucket(Bucket=bucket_name)
        logger.info(f"Bucket '{bucket_name}' already exists")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            try:
                client.create_bucket(Bucket=bucket_name)
                logger.info(f"Bucket '{bucket_name}' created successfully")
            except Exception as create_error:
                logger.error(f"Error creating bucket '{bucket_name}': {create_error}")
                raise MinIOError(
                    f"Error creating bucket '{bucket_name}': {create_error}"
                ) from create_error
        else:
            logger.error(f"Error checking bucket '{bucket_name}': {e}")
            raise MinIOError(f"Error checking bucket '{bucket_name}': {e}") from e

    if lifecycle_prefix and lifecycle_days:
        set_bucket_lifecycle_policy(bucket_name, lifecycle_prefix, lifecycle_days)

    return True
