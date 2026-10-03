"""
MinIO File Operations

Functions for uploading, downloading, and managing files in MinIO.
"""

import os
import logging
from io import BytesIO, StringIO
from typing import List

import pandas as pd
from botocore.exceptions import ClientError

from .client import get_minio_client, create_bucket_if_not_exists
from ..exceptions import MinIOError

logger = logging.getLogger(__name__)


def upload_to_minio(
    file_path: str,
    bucket_name: str,
    object_key: str,
) -> bool:
    """
    Upload a file to MinIO.

    Args:
        file_path: Local path to the file to upload
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) for the object in MinIO

    Returns:
        True if upload successful

    Raises:
        FileNotFoundError: If local file doesn't exist
        MinIOError: If upload fails
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    client = get_minio_client()

    try:
        create_bucket_if_not_exists(bucket_name)
        client.upload_file(file_path, bucket_name, object_key)
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(
            f"Uploaded '{file_path}' ({file_size:.2f} MB) to '{bucket_name}/{object_key}'"
        )
        return True
    except Exception as e:
        logger.error(f"Error uploading file to MinIO: {e}")
        raise MinIOError(f"Error uploading file to MinIO: {e}") from e


def download_from_minio(
    bucket_name: str,
    object_key: str,
    file_path: str,
) -> bool:
    """
    Download a file from MinIO.

    Args:
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) of the object in MinIO
        file_path: Local path where to save the downloaded file

    Returns:
        True if download successful

    Raises:
        MinIOError: If download fails or object doesn't exist
    """
    client = get_minio_client()

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        client.download_file(bucket_name, object_key, file_path)
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(
            f"Downloaded '{bucket_name}/{object_key}' ({file_size:.2f} MB) to '{file_path}'"
        )
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            logger.warning(f"Object not found: '{bucket_name}/{object_key}'")
            raise MinIOError(f"Object not found: '{bucket_name}/{object_key}'") from e
        else:
            logger.error(f"Error downloading file from MinIO: {e}")
            raise MinIOError(f"Error downloading file from MinIO: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error downloading file: {e}")
        raise MinIOError(f"Unexpected error downloading file: {e}") from e


def check_file_exists(bucket_name: str, object_key: str) -> bool:
    """
    Check if a file exists in MinIO.

    Args:
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) of the object in MinIO

    Returns:
        True if file exists, False otherwise

    Raises:
        MinIOError: If check fails (other than 404)
    """
    client = get_minio_client()

    try:
        client.head_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"File exists: '{bucket_name}/{object_key}'")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            logger.info(f"File does not exist: '{bucket_name}/{object_key}'")
            return False
        else:
            logger.error(f"Error checking file existence: {e}")
            raise MinIOError(f"Error checking file existence: {e}") from e


def list_objects(bucket_name: str, prefix: str = "") -> List[str]:
    """
    List objects in a MinIO bucket with optional prefix filter.

    Args:
        bucket_name: Name of the MinIO bucket
        prefix: Prefix to filter objects (e.g., 'raw-data/')

    Returns:
        List of object keys matching the prefix

    Raises:
        MinIOError: If listing fails
    """
    client = get_minio_client()

    try:
        response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        if "Contents" not in response:
            logger.info(f"No objects found in '{bucket_name}' with prefix '{prefix}'")
            return []

        objects = [obj["Key"] for obj in response["Contents"]]
        logger.info(
            f"Found {len(objects)} objects in '{bucket_name}' with prefix '{prefix}'"
        )
        return objects
    except Exception as e:
        logger.error(f"Error listing objects: {e}")
        raise MinIOError(f"Error listing objects: {e}") from e


def delete_object(bucket_name: str, object_key: str) -> bool:
    """
    Delete an object from MinIO.

    Args:
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) of the object to delete

    Returns:
        True if deletion successful

    Raises:
        MinIOError: If deletion fails
    """
    client = get_minio_client()

    try:
        client.delete_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"Deleted object: '{bucket_name}/{object_key}'")
        return True
    except Exception as e:
        logger.error(f"Error deleting object: {e}")
        raise MinIOError(f"Error deleting object: {e}") from e


def download_to_dataframe(bucket_name: str, object_key: str) -> pd.DataFrame:
    """
    Download a CSV file from MinIO directly to a pandas DataFrame.
    No temporary files needed - works entirely in memory.

    Args:
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) of the CSV object in MinIO

    Returns:
        DataFrame with the CSV data

    Raises:
        MinIOError: If download fails or object doesn't exist
    """
    client = get_minio_client()

    try:
        logger.info(f"Downloading '{bucket_name}/{object_key}' to DataFrame...")
        response = client.get_object(Bucket=bucket_name, Key=object_key)
        csv_bytes = response["Body"].read()
        df = pd.read_csv(BytesIO(csv_bytes))
        file_size = len(csv_bytes) / (1024 * 1024)
        logger.info(
            f"Downloaded {len(df)} records ({file_size:.2f} MB) "
            f"from '{bucket_name}/{object_key}'"
        )
        return df
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            logger.error(f"Object not found: '{bucket_name}/{object_key}'")
            raise MinIOError(f"Object not found: '{bucket_name}/{object_key}'") from e
        else:
            logger.error(f"Error downloading to DataFrame: {e}")
            raise MinIOError(f"Error downloading to DataFrame: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error downloading to DataFrame: {e}")
        raise MinIOError(f"Unexpected error downloading to DataFrame: {e}") from e


def upload_from_dataframe(
    df: pd.DataFrame,
    bucket_name: str,
    object_key: str,
    index: bool = False,
) -> bool:
    """
    Upload a pandas DataFrame directly to MinIO as a CSV file.
    No temporary files needed - works entirely in memory.

    Args:
        df: DataFrame to upload
        bucket_name: Name of the MinIO bucket
        object_key: Key (path) for the object in MinIO
        index: Whether to include DataFrame index in CSV (default: False)

    Returns:
        True if upload successful

    Raises:
        MinIOError: If upload fails
    """
    client = get_minio_client()

    try:
        create_bucket_if_not_exists(bucket_name)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=index)
        csv_bytes = csv_buffer.getvalue().encode("utf-8")

        client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=BytesIO(csv_bytes),
            ContentLength=len(csv_bytes),
        )

        file_size = len(csv_bytes) / (1024 * 1024)
        logger.info(
            f"Uploaded {len(df)} records ({file_size:.2f} MB) "
            f"to '{bucket_name}/{object_key}'"
        )
        return True
    except Exception as e:
        logger.error(f"Error uploading DataFrame to MinIO: {e}")
        raise MinIOError(f"Error uploading DataFrame to MinIO: {e}") from e
