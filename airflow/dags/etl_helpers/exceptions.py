"""
Custom Exceptions for ETL Pipeline

Centralized exception definitions for the Chicago Crime ETL pipeline.
"""


class ETLError(Exception):
    """Base exception for all ETL pipeline errors."""

    pass


class DataValidationError(ETLError):
    """
    Error raised when data validation fails.

    Examples:
        - NaN values found where not allowed
        - Invalid data types
        - Missing required columns
    """

    pass


class MinIOError(ETLError):
    """
    Error raised during MinIO/S3 operations.

    Examples:
        - Connection failures
        - Bucket not found
        - Upload/download failures
    """

    pass


class DataLoadError(ETLError):
    """
    Error raised when loading data from external sources fails.

    Examples:
        - Socrata API failures
        - Network timeouts
        - Invalid API responses
    """

    pass


class EnrichmentError(ETLError):
    """
    Error raised during data enrichment operations.

    Examples:
        - Geospatial join failures
        - Missing reference data
        - CRS transformation errors
    """

    pass


class FeatureEngineeringError(ETLError):
    """
    Error raised during feature engineering operations.

    Examples:
        - Encoding failures
        - Scaling errors
        - Feature selection issues
    """

    pass
