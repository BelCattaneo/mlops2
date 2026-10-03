"""
Data Enrichment Functions

Functions for enriching Chicago crime data with geospatial and temporal features.
"""

import os
import logging
from typing import Optional

import pandas as pd
import geopandas as gpd

from . import config
from .exceptions import EnrichmentError

logger = logging.getLogger(__name__)


def calculate_nearest_station(
    crimes_df: pd.DataFrame,
    stations_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate distance from each crime to the nearest police station.
    Uses X/Y coordinates if available (already projected), otherwise lat/lon.

    Args:
        crimes_df: Crime data with x/y coordinates or latitude/longitude
        stations_df: Police stations with x/y coordinates or latitude/longitude

    Returns:
        Crime data with nearest station distance (in meters) and district

    Raises:
        EnrichmentError: If spatial join fails
    """
    logger.info("Calculating distances to nearest police stations...")

    try:
        # Check if X/Y coordinates are available (already projected)
        has_xy_crimes = (
            "x_coordinate" in crimes_df.columns and "y_coordinate" in crimes_df.columns
        )
        has_xy_stations = (
            "x_coordinate" in stations_df.columns
            and "y_coordinate" in stations_df.columns
        )

        if has_xy_crimes and has_xy_stations:
            # Use X/Y coordinates directly (already projected, likely Illinois State Plane)
            logger.info("Using X/Y coordinates (projected)")
            crimes_gdf = gpd.GeoDataFrame(
                crimes_df,
                geometry=gpd.points_from_xy(
                    crimes_df["x_coordinate"].astype(float),
                    crimes_df["y_coordinate"].astype(float),
                ),
                crs=config.CRS_ILLINOIS_STATE_PLANE,
            )

            stations_gdf = gpd.GeoDataFrame(
                stations_df,
                geometry=gpd.points_from_xy(
                    stations_df["x_coordinate"].astype(float),
                    stations_df["y_coordinate"].astype(float),
                ),
                crs=config.CRS_ILLINOIS_STATE_PLANE,
            )
        else:
            # Fallback to lat/lon and convert to projected CRS
            logger.info("Using latitude/longitude coordinates")
            crimes_gdf = gpd.GeoDataFrame(
                crimes_df,
                geometry=gpd.points_from_xy(
                    crimes_df["longitude"].astype(float),
                    crimes_df["latitude"].astype(float),
                ),
                crs=config.CRS_WGS84,
            )

            stations_gdf = gpd.GeoDataFrame(
                stations_df,
                geometry=gpd.points_from_xy(
                    stations_df["longitude"].astype(float),
                    stations_df["latitude"].astype(float),
                ),
                crs=config.CRS_WGS84,
            )

            # Convert to projected CRS for Chicago
            crimes_gdf = crimes_gdf.to_crs(epsg=config.CRS_UTM_ZONE)
            stations_gdf = stations_gdf.to_crs(epsg=config.CRS_UTM_ZONE)

        # Perform spatial join to find nearest station
        crimes_with_stations = gpd.sjoin_nearest(
            crimes_gdf,
            stations_gdf[["district", "district_name", "geometry"]],
            how="left",
            distance_col="distance_crime_to_police_station",
        )

        # Convert back to regular DataFrame
        result_df = pd.DataFrame(crimes_with_stations.drop(columns="geometry"))

        # Drop index_right column created by sjoin_nearest
        if "index_right" in result_df.columns:
            result_df = result_df.drop(columns=["index_right"])
            logger.info("Dropped 'index_right' column from spatial join")

        # Rename columns to match expected format
        result_df = result_df.rename(
            columns={
                "district": "nearest_police_station_district",
                "district_name": "nearest_police_station_district_name",
            }
        )

        logger.info(f"Calculated distances for {len(result_df)} crime records")
        return result_df

    except Exception as e:
        logger.error(f"Error calculating nearest stations: {e}")
        raise EnrichmentError(f"Error calculating nearest stations: {e}") from e


def create_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create temporal features from the date column.
    Creates: Season, Day of Week, Day Time (morning/afternoon/evening/night).

    Args:
        df: DataFrame with 'date' column

    Returns:
        DataFrame with added temporal features

    Raises:
        EnrichmentError: If temporal feature creation fails
    """
    logger.info("Creating temporal features...")

    try:
        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])

        # Extract month and hour
        df["month"] = df["date"].dt.month
        df["hour"] = df["date"].dt.hour
        df["day_of_week"] = df["date"].dt.dayofweek  # 0=Monday, 6=Sunday

        # Create Season feature
        def get_season(month: int) -> str:
            if month in [12, 1, 2]:
                return "Winter"
            elif month in [3, 4, 5]:
                return "Spring"
            elif month in [6, 7, 8]:
                return "Summer"
            else:  # 9, 10, 11
                return "Autumn"

        df["season"] = df["month"].apply(get_season)

        # Create Day Time feature (4 periods)
        def get_day_time(hour: int) -> str:
            if 0 <= hour < 6:
                return "Early Morning"
            elif 6 <= hour < 12:
                return "Morning"
            elif 12 <= hour < 18:
                return "Afternoon"
            else:  # 18-23
                return "Night"

        df["day_time"] = df["hour"].apply(get_day_time)

        # Drop temporary columns
        df = df.drop(columns=["month", "hour"])

        logger.info("Temporal features created: season, day_of_week, day_time")
        return df

    except Exception as e:
        logger.error(f"Error creating temporal features: {e}")
        raise EnrichmentError(f"Error creating temporal features: {e}") from e


def clean_and_select_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean data and select relevant columns.
    Removes ID columns and unnecessary fields as per notebook.

    Args:
        df: Raw merged dataframe

    Returns:
        Cleaned dataframe with selected columns

    Raises:
        EnrichmentError: If cleaning fails
    """
    logger.info("Cleaning and selecting columns...")

    try:
        # Define columns to keep (from config)
        columns_to_keep = list(config.COLUMNS_TO_KEEP)

        # Keep only columns that exist in the dataframe
        existing_columns = [col for col in columns_to_keep if col in df.columns]
        df_cleaned = df[existing_columns].copy()

        # Convert boolean columns to proper type
        if "arrest" in df_cleaned.columns:
            df_cleaned["arrest"] = (
                df_cleaned["arrest"].astype(str).str.lower() == "true"
            )

        if "domestic" in df_cleaned.columns:
            df_cleaned["domestic"] = (
                df_cleaned["domestic"].astype(str).str.lower() == "true"
            )

        # Convert numeric columns
        numeric_cols = [
            "x_coordinate",
            "y_coordinate",
            "latitude",
            "longitude",
            "distance_crime_to_police_station",
        ]
        for col in numeric_cols:
            if col in df_cleaned.columns:
                df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors="coerce")

        # Handle NaN values generated by numeric conversion
        # Coordinates are critical for geospatial operations - rows with invalid coords must be removed
        critical_coords = ["latitude", "longitude", "x_coordinate", "y_coordinate"]
        existing_critical = [
            col for col in critical_coords if col in df_cleaned.columns
        ]
        if existing_critical:
            nan_counts = df_cleaned[existing_critical].isna().sum()
            if nan_counts.any():
                logger.warning(
                    f"NaN values found in coordinates: {nan_counts[nan_counts > 0].to_dict()}"
                )
                rows_before = len(df_cleaned)
                df_cleaned = df_cleaned.dropna(subset=existing_critical)
                rows_dropped = rows_before - len(df_cleaned)
                logger.info(
                    f"Dropped {rows_dropped} rows with invalid coordinates. "
                    f"Remaining: {len(df_cleaned)}"
                )

        # Handle NaN in distance column (fill with median if present)
        if "distance_crime_to_police_station" in df_cleaned.columns:
            dist_nan_count = df_cleaned["distance_crime_to_police_station"].isna().sum()
            if dist_nan_count > 0:
                median_dist = df_cleaned["distance_crime_to_police_station"].median()
                df_cleaned["distance_crime_to_police_station"] = df_cleaned[
                    "distance_crime_to_police_station"
                ].fillna(median_dist)
                logger.info(
                    f"Filled {dist_nan_count} NaN values in distance column "
                    f"with median: {median_dist:.2f}"
                )

        logger.info(
            f"Cleaned data: {len(df_cleaned)} records, {len(df_cleaned.columns)} columns"
        )
        return df_cleaned

    except Exception as e:
        logger.error(f"Error cleaning data: {e}")
        raise EnrichmentError(f"Error cleaning data: {e}") from e


def enrich_crime_data(
    crimes_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    output_file: Optional[str] = None,
) -> pd.DataFrame:
    """
    Enrich crime data by adding nearest station info and temporal features.

    Args:
        crimes_df: Downloaded crime data
        stations_df: Police stations data
        output_file: Path to save enriched CSV (optional)

    Returns:
        Enriched crime data

    Raises:
        EnrichmentError: If enrichment process fails
    """
    logger.info("Starting data enrichment...")

    try:
        if len(crimes_df) == 0:
            logger.warning("No crime data to enrich. Returning empty DataFrame.")
            return pd.DataFrame()

        # Calculate distances to nearest station
        merged_df = calculate_nearest_station(crimes_df, stations_df)

        # Create temporal features
        merged_df = create_temporal_features(merged_df)

        # Clean and select columns
        final_df = clean_and_select_columns(merged_df)

        # Save to file if path provided
        if output_file:
            final_df.to_csv(output_file, index=False)
            file_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
            logger.info(f"Saved enriched data to {output_file} ({file_size:.2f} MB)")

        logger.info(f"Enrichment completed: {len(final_df)} records")
        return final_df

    except EnrichmentError:
        raise
    except Exception as e:
        logger.error(f"Error in data enrichment: {e}")
        raise EnrichmentError(f"Error in data enrichment: {e}") from e
