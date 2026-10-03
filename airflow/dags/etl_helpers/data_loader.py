"""
Data Loading Functions

Functions for downloading Chicago crime data from Socrata API.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from sodapy import Socrata

from . import config
from .exceptions import DataLoadError

logger = logging.getLogger(__name__)

# Dataset IDs (from config)
CRIME_DATASET_ID = config.CRIME_DATASET_ID
POLICE_STATIONS_DATASET_ID = config.POLICE_STATIONS_DATASET_ID
SOCRATA_DOMAIN = config.SOCRATA_DOMAIN


def get_socrata_client() -> Socrata:
    """
    Initialize Socrata client with app token from environment.

    Returns:
        Configured Socrata client

    Raises:
        DataLoadError: If client initialization fails
    """
    try:
        app_token = os.getenv("SOCRATA_APP_TOKEN")
        if not app_token:
            logger.warning(
                "SOCRATA_APP_TOKEN not found in environment. API rate limits will apply."
            )

        client = Socrata(SOCRATA_DOMAIN, app_token, timeout=config.API_TIMEOUT)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Socrata client: {e}")
        raise DataLoadError(f"Failed to initialize Socrata client: {e}") from e


def download_crimes_full(output_file: Optional[str] = None) -> pd.DataFrame:
    """
    Download all crime records from the past year.
    Used for initial/first run when no historical data exists.

    Args:
        output_file: Path to save CSV output (optional)

    Returns:
        Crime data for the past year

    Raises:
        DataLoadError: If download fails
    """
    client = get_socrata_client()

    try:
        one_year_ago = (
            datetime.now() - timedelta(days=config.ROLLING_WINDOW_DAYS)
        ).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"Downloading full crime dataset from {one_year_ago} to {today}...")

        results = client.get_all(
            CRIME_DATASET_ID,
            where=f"date >= '{one_year_ago}' AND date <= '{today}'",
            order=":id",
        )

        df = pd.DataFrame.from_records(results)
        logger.info(f"Downloaded {len(df)} crime records (full dataset)")

        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Saved to {output_file}")

        return df

    except Exception as e:
        logger.error(f"Error downloading full crime dataset: {e}")
        raise DataLoadError(f"Error downloading full crime dataset: {e}") from e
    finally:
        client.close()


def download_crimes_incremental(
    start_date: str | datetime,
    end_date: str | datetime,
    output_file: Optional[str] = None,
) -> pd.DataFrame:
    """
    Download crime records for a specific date range (incremental update).

    Args:
        start_date: Start date in YYYY-MM-DD format or datetime
        end_date: End date in YYYY-MM-DD format or datetime
        output_file: Path to save CSV output (optional)

    Returns:
        Crime data for the specified date range

    Raises:
        DataLoadError: If download fails
    """
    client = get_socrata_client()

    try:
        if isinstance(start_date, datetime):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime):
            end_date = end_date.strftime("%Y-%m-%d")

        logger.info(
            f"Downloading incremental crime data from {start_date} to {end_date}..."
        )

        results = client.get_all(
            CRIME_DATASET_ID,
            where=f"date >= '{start_date}' AND date < '{end_date}'",
            order=":id",
        )

        df = pd.DataFrame.from_records(results)
        logger.info(f"Downloaded {len(df)} crime records (incremental)")

        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Saved to {output_file}")

        return df

    except Exception as e:
        logger.error(f"Error downloading incremental crime data: {e}")
        raise DataLoadError(f"Error downloading incremental crime data: {e}") from e
    finally:
        client.close()


def download_police_stations(output_file: Optional[str] = None) -> pd.DataFrame:
    """
    Download Chicago police stations dataset.

    Args:
        output_file: Path to save CSV output (optional)

    Returns:
        Police stations data with coordinates

    Raises:
        DataLoadError: If download fails
    """
    client = get_socrata_client()

    try:
        logger.info("Downloading police stations dataset...")

        results = client.get_all(POLICE_STATIONS_DATASET_ID, order=":id")

        df = pd.DataFrame.from_records(results)
        logger.info(f"Downloaded {len(df)} police stations")

        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Saved to {output_file}")

        return df

    except Exception as e:
        logger.error(f"Error downloading police stations: {e}")
        raise DataLoadError(f"Error downloading police stations: {e}") from e
    finally:
        client.close()
