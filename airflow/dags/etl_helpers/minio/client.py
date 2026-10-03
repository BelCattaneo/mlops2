"""
MinIO Client and Bucket Management

Functions for initializing MinIO client and managing buckets.
"""

import logging
import os

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


NONCURRENT_DAYS = 7


def lifecycle_rules(policy: dict[str, int]) -> dict:
    """Arma la configuración de ciclo de vida a partir de un TTL por prefijo.

    Las capas que no figuran en la política no reciben regla: así se conservan. Cada regla
    expira además las versiones no actuales, que en un bucket versionado es lo único que libera
    espacio: `Expiration` por sí sola no borra bytes, pone una marca de borrado y deja la
    versión vieja como no actual.
    """
    return {
        "Rules": [
            {
                "ID": f"Delete-{prefix.replace('/', '-')}-after-{days}-days",
                "Status": "Enabled",
                "Filter": {"Prefix": prefix},
                "Expiration": {"Days": days},
                "NoncurrentVersionExpiration": {"NoncurrentDays": NONCURRENT_DAYS},
            }
            for prefix, days in sorted(policy.items())
        ]
    }


def enable_versioning(bucket_name: str) -> bool:
    """Habilita el versionado del bucket, que es lo que hace recuperable un borrado.

    Con versionado, borrar una clave no borra bytes: agrega una marca de borrado y el objeto
    sigue estando, recuperable por `VersionId`. Es lo que vuelve exigible la inmutabilidad que
    la capa cruda promete. Correrlo de nuevo no cambia nada.
    """
    try:
        get_minio_client().put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )
        logger.info(f"Versioning enabled on '{bucket_name}'")
        return True
    except Exception as e:
        logger.error(f"Error enabling versioning: {e}")
        raise MinIOError(f"Error enabling versioning: {e}") from e


def set_bucket_lifecycle_policy(bucket_name: str, policy: dict[str, int]) -> bool:
    """
    Set the lifecycle policy of the bucket from a per-prefix TTL in days.

    Args:
        bucket_name: Name of the MinIO bucket
        policy: Prefix -> days after which its objects are deleted

    Returns:
        True if policy set successfully

    Raises:
        MinIOError: If setting lifecycle policy fails
    """
    client = get_minio_client()
    lifecycle_config = lifecycle_rules(policy)

    try:
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name, LifecycleConfiguration=lifecycle_config
        )
        logger.info(
            f"Lifecycle policy set for '{bucket_name}': "
            f"{len(lifecycle_config['Rules'])} rules ({', '.join(sorted(policy))})"
        )
        return True
    except Exception as e:
        logger.error(f"Error setting lifecycle policy: {e}")
        raise MinIOError(f"Error setting lifecycle policy: {e}") from e


def create_bucket_if_not_exists(
    bucket_name: str,
    lifecycle_prefix: str | None = None,
    lifecycle_days: int | None = None,
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
