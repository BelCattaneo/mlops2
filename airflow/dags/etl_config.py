"""
ETL Pipeline Configuration

Centralized configuration for the Chicago Crime ETL pipeline.
All hardcoded constants are defined here for easy modification.
"""

import datetime
import os
from dataclasses import dataclass

# El bucket y los argumentos por defecto los comparten los dos DAGs: definidos dos veces, se
# separan en silencio el día que alguien cambia uno.
BUCKET_NAME = os.getenv("DATA_REPO_BUCKET_NAME", "data")

DEFAULT_ARGS = {
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=5),
    "dagrun_timeout": datetime.timedelta(minutes=60),
}

# Dos experimentos con nombre, para que nada caiga en "Default": las métricas de cada capa
# del pipeline por un lado y los entrenamientos por el otro. No son lo mismo ni se comparan.
ETL_EXPERIMENT = "chicago-arrest-etl"
TRAINING_EXPERIMENT = "chicago-arrest"


@dataclass(frozen=True)
class ETLConfig:
    """ETL pipeline configuration parameters."""

    # Las tres capas del lake. Los nombres son los del mini-TP 6, donde `curated` es lo que el
    # modelo consume: son las capas del medallón con nombres de dominio.
    PREFIX_RAW: str = "raw/"
    PREFIX_ENRICHED: str = "enriched/"
    PREFIX_CURATED: str = "curated/"

    # Data processing parameters.
    # Solo la capa intermedia expira: es derivable de la cruda en un minuto. La cruda se
    # conserva porque es el sistema de registro, y la final porque es el dataset con el que se
    # entrenó un modelo, que es lo que hace auditable una predicción.
    ENRICHED_TTL_DAYS: int = 30
    ROLLING_WINDOW_DAYS: int = 365
    TARGET_COLUMN: str = "arrest"
    SPLIT_TEST_SIZE: float = 0.2
    SPLIT_RANDOM_STATE: int = 42

    # Outlier detection
    OUTLIER_STD_THRESHOLD: int = 3

    # Feature selection
    MI_THRESHOLD: float = 0.05
    CORRELATION_THRESHOLD: float = 0.65

    # SMOTE balancing
    SMOTE_SAMPLING_STRATEGY: float = 0.5
    UNDERSAMPLE_STRATEGY: float = 0.8
    BALANCING_RANDOM_STATE: int = 17

    # Socrata API
    CRIME_DATASET_ID: str = "ijzp-q8t2"
    POLICE_STATIONS_DATASET_ID: str = "z8bn-74gv"
    SOCRATA_DOMAIN: str = "data.cityofchicago.org"
    API_TIMEOUT: int = 60

    # Geospatial CRS
    CRS_ILLINOIS_STATE_PLANE: str = "EPSG:3435"
    CRS_WGS84: str = "EPSG:4326"
    CRS_UTM_ZONE: int = 32616

    # Columns to keep after enrichment
    # Note: latitude/longitude excluded - redundant with x/y coordinates
    COLUMNS_TO_KEEP: tuple = (
        "date",
        "iucr",
        "primary_type",
        "description",
        "location_description",
        "arrest",
        "domestic",
        "beat",
        "district",
        "ward",
        "community_area",
        "fbi_code",
        "x_coordinate",
        "y_coordinate",
        "distance_crime_to_police_station",
        "nearest_police_station_district",
        "nearest_police_station_district_name",
        "season",
        "day_of_week",
        "day_time",
    )

    # Columns to drop during preprocessing
    COLUMNS_TO_DROP_PREPROCESS: tuple = ("date", "index_right", "description")

    # High cardinality columns for frequency encoding
    FREQUENCY_ENCODING_COLUMNS: tuple = (
        "iucr",
        "primary_type",
        "location_description",
        "fbi_code",
        "district",
        "nearest_police_station_district",
        "nearest_police_station_district_name",
        "beat",
        "ward",
        "community_area",
    )

    # Columns for one-hot encoding
    ONEHOT_ENCODING_COLUMNS: tuple = ("season", "day_time")

    # Numeric columns to scale
    # Note: latitude/longitude excluded - they're redundant with x/y coordinates
    # (which are in Illinois State Plane projection, better for distance calculations)
    SCALING_COLUMNS: tuple = (
        "x_coordinate",
        "y_coordinate",
        "distance_crime_to_police_station",
    )

    # Columns to drop in feature selection (high correlation)
    # These are the encoded column names (_freq suffix) created during encoding
    FEATURE_SELECTION_DROP: tuple = (
        "beat_freq",
        "ward_freq",
        "community_area_freq",
        "nearest_police_station_district_name_freq",
        "fbi_code_freq",
    )


# Singleton instance
config = ETLConfig()
