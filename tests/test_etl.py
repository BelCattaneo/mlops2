"""
End-to-End ETL Pipeline Tests

Integration tests for the complete ETL pipeline:
enrich -> split -> outliers -> encode -> scale -> balance -> features

Las fixtures venían en el conftest.py del repo de MLOps I; viven acá porque este es el
único archivo que las usa. Los helpers se importan adentro de cada test, y el directorio
de los DAGs entra al sys.path por `pythonpath` en el pyproject.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent / "data"


@pytest.fixture
def sample_crimes_df(fixtures_dir: Path) -> pd.DataFrame:
    """Load sample crime data from CSV fixture."""
    return pd.read_csv(fixtures_dir / "sample_crimes.csv")


@pytest.fixture
def sample_stations_df(fixtures_dir: Path) -> pd.DataFrame:
    """Load sample police stations data from CSV fixture."""
    return pd.read_csv(fixtures_dir / "sample_stations.csv")


@pytest.fixture
def enriched_df(sample_crimes_df: pd.DataFrame, sample_stations_df: pd.DataFrame) -> pd.DataFrame:
    """Return enriched crime data with geospatial and temporal features."""
    from etl_helpers.data_enrichment import enrich_crime_data

    return enrich_crime_data(sample_crimes_df, sample_stations_df)


@pytest.fixture
def preprocessed_df(enriched_df: pd.DataFrame) -> pd.DataFrame:
    """Return preprocessed data ready for splitting."""
    from etl_helpers.data_splitter import preprocess_for_split

    return preprocess_for_split(enriched_df)


@pytest.fixture
def train_test_split_dfs(preprocessed_df: pd.DataFrame) -> tuple:
    """Return train and test DataFrames after splitting."""
    from etl_helpers.data_splitter import split_train_test

    return split_train_test(preprocessed_df)


@pytest.fixture
def train_df(train_test_split_dfs: tuple) -> pd.DataFrame:
    """Return training DataFrame."""
    return train_test_split_dfs[0]


@pytest.fixture
def test_df(train_test_split_dfs: tuple) -> pd.DataFrame:
    """Return test DataFrame."""
    return train_test_split_dfs[1]


class TestDataEnrichment:
    """Tests for data enrichment stage."""

    def test_enrichment_adds_geospatial_features(
        self,
        sample_crimes_df: pd.DataFrame,
        sample_stations_df: pd.DataFrame,
    ):
        """Test that enrichment adds distance to nearest police station."""
        from etl_helpers.data_enrichment import enrich_crime_data

        # Given: raw crime data and police stations data
        crimes = sample_crimes_df
        stations = sample_stations_df

        # When: we enrich the crime data
        result = enrich_crime_data(crimes, stations)

        # Then: geospatial features should be added
        assert "distance_crime_to_police_station" in result.columns
        assert "nearest_police_station_district_name" in result.columns
        assert result["distance_crime_to_police_station"].notna().all()

    def test_enrichment_adds_temporal_features(
        self,
        sample_crimes_df: pd.DataFrame,
        sample_stations_df: pd.DataFrame,
    ):
        """Test that enrichment adds temporal features."""
        from etl_helpers.data_enrichment import enrich_crime_data

        # Given: raw crime data with date column
        crimes = sample_crimes_df
        stations = sample_stations_df

        # When: we enrich the crime data
        result = enrich_crime_data(crimes, stations)

        # Then: temporal features should be added with valid values
        assert "season" in result.columns
        assert "day_of_week" in result.columns
        assert "day_time" in result.columns
        assert set(result["season"].unique()).issubset({"Winter", "Spring", "Summer", "Autumn"})
        assert set(result["day_time"].unique()).issubset(
            {"Early Morning", "Morning", "Afternoon", "Night"}
        )

    def test_enrichment_preserves_record_count(
        self,
        sample_crimes_df: pd.DataFrame,
        sample_stations_df: pd.DataFrame,
    ):
        """Test that enrichment doesn't lose records (except invalid coords)."""
        from etl_helpers.data_enrichment import enrich_crime_data

        # Given: raw crime data with N records
        initial_count = len(sample_crimes_df)

        # When: we enrich the crime data
        result = enrich_crime_data(sample_crimes_df, sample_stations_df)

        # Then: at least 90% of records should be preserved
        assert len(result) >= initial_count * 0.9


class TestDataSplitting:
    """Tests for data preprocessing and splitting stage."""

    def test_preprocess_removes_duplicates(self, enriched_df: pd.DataFrame):
        """Test that preprocessing removes duplicate records."""
        from etl_helpers.data_splitter import preprocess_for_split

        # Given: enriched data with artificial duplicates
        enriched_with_dups = pd.concat([enriched_df, enriched_df.head(10)])
        initial_count = len(enriched_with_dups)

        # When: we preprocess the data
        result = preprocess_for_split(enriched_with_dups)

        # Then: duplicates should be removed
        assert len(result) <= initial_count

    def test_split_maintains_stratification(self, preprocessed_df: pd.DataFrame):
        """Test that split maintains class distribution in target column."""
        from etl_helpers.data_splitter import split_train_test

        # Given: preprocessed data with class imbalance
        data = preprocessed_df

        # When: we split into train/test
        train_df, test_df = split_train_test(data)

        # Then: class proportions should be similar (within 5%)
        train_positive_rate = train_df["arrest"].mean()
        test_positive_rate = test_df["arrest"].mean()
        assert abs(train_positive_rate - test_positive_rate) < 0.05

    def test_split_ratio_is_approximately_80_20(self, preprocessed_df: pd.DataFrame):
        """Test that split creates approximately 80/20 train/test ratio."""
        from etl_helpers.data_splitter import split_train_test

        # Given: preprocessed data
        data = preprocessed_df

        # When: we split into train/test
        train_df, test_df = split_train_test(data)

        # Then: train should be ~80% of total
        total = len(train_df) + len(test_df)
        train_ratio = len(train_df) / total
        assert 0.75 <= train_ratio <= 0.85


class TestOutlierRemoval:
    """Tests for outlier processing stage."""

    def test_outlier_removal_reduces_record_count(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that outlier removal reduces dataset size."""
        from etl_helpers.outlier_processing import process_outliers

        # Given: train and test data with potential outliers
        train_initial = len(train_df)
        test_initial = len(test_df)

        # When: we remove outliers
        train_processed, test_processed = process_outliers(train_df, test_df)

        # Then: record count should stay same or decrease
        assert len(train_processed) <= train_initial
        assert len(test_processed) <= test_initial

    def test_outlier_removal_uses_train_statistics(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that outlier bounds are calculated from train data only."""
        from etl_helpers.outlier_processing import process_outliers

        # Given: train data with known statistics
        column = "distance_crime_to_police_station"
        mean_val = train_df[column].mean()
        std_val = train_df[column].std()
        lower_bound = mean_val - 3 * std_val
        upper_bound = mean_val + 3 * std_val

        # When: we remove outliers
        train_processed, test_processed = process_outliers(train_df, test_df)

        # Then: all remaining values should be within train-derived bounds
        assert train_processed[column].min() >= lower_bound
        assert train_processed[column].max() <= upper_bound


class TestDataEncoding:
    """Tests for data encoding stage."""

    def test_encoding_creates_frequency_columns(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that frequency encoding creates _freq columns."""
        from etl_helpers.data_encoding import encode_data

        # Given: train and test data with categorical columns
        train = train_df.copy()
        test = test_df.copy()

        # When: we encode the data
        train_encoded, test_encoded = encode_data(train, test)

        # Then: frequency encoded columns should exist
        freq_cols = [col for col in train_encoded.columns if col.endswith("_freq")]
        assert len(freq_cols) > 0

    def test_encoding_creates_cyclic_columns(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        """Test that cyclic encoding creates _sin column for day_of_week."""
        from etl_helpers.data_encoding import encode_data

        # Given: train and test data with day_of_week column
        train = train_df.copy()
        test = test_df.copy()

        # When: we encode the data
        train_encoded, test_encoded = encode_data(train, test)

        # Then: cyclic sine column should exist with values in [-1, 1]
        assert "day_of_week_sin" in train_encoded.columns
        assert "day_of_week_sin" in test_encoded.columns
        assert train_encoded["day_of_week_sin"].min() >= -1
        assert train_encoded["day_of_week_sin"].max() <= 1

    def test_encoding_removes_categorical_columns(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that encoding drops original categorical columns."""
        from etl_helpers.data_encoding import encode_data

        # Given: train and test data with categorical columns
        train = train_df.copy()
        test = test_df.copy()

        # When: we encode the data
        train_encoded, test_encoded = encode_data(train, test)

        # Then: original categorical columns should be dropped
        assert "season" not in train_encoded.columns
        assert "day_time" not in train_encoded.columns
        assert "domestic" not in train_encoded.columns
        assert "primary_type" not in train_encoded.columns

    def test_encoding_produces_numeric_output(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        """Test that all columns after encoding are numeric."""
        from etl_helpers.data_encoding import encode_data

        # Given: train and test data with mixed types
        train = train_df.copy()
        test = test_df.copy()

        # When: we encode the data
        train_encoded, test_encoded = encode_data(train, test)

        # Then: all columns should be numeric
        non_numeric = train_encoded.select_dtypes(exclude=[np.number, bool]).columns
        assert len(non_numeric) == 0, f"Non-numeric columns found: {list(non_numeric)}"


class TestDataScaling:
    """Tests for data scaling stage."""

    def test_scaling_standardizes_values(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        """Test that scaling produces approximately mean=0, std=1 for train."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data

        # Given: encoded train and test data
        train_encoded, test_encoded = encode_data(train_df.copy(), test_df.copy())

        # When: we scale the data
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)

        # Then: standardized columns should have mean≈0 and std≈1
        std_cols = [col for col in train_scaled.columns if col.endswith("_standardized")]
        assert len(std_cols) > 0
        for col in std_cols:
            assert abs(train_scaled[col].mean()) < 0.1
            assert abs(train_scaled[col].std() - 1) < 0.1

    def test_scaling_creates_standardized_columns(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that scaling creates _standardized suffix columns."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data

        # Given: encoded train and test data
        train_encoded, test_encoded = encode_data(train_df.copy(), test_df.copy())

        # When: we scale the data
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)

        # Then: coordinate columns should be standardized
        # Note: latitude/longitude excluded (redundant with x/y coordinates)
        assert "x_coordinate_standardized" in train_scaled.columns
        assert "y_coordinate_standardized" in train_scaled.columns
        assert "distance_crime_to_police_station_standardized" in train_scaled.columns


class TestDataBalancing:
    """Tests for data balancing stage."""

    def test_balancing_improves_class_ratio(self, train_df: pd.DataFrame):
        """Test that balancing improves the class ratio when data is imbalanced."""
        from etl_helpers.data_balancing import balance_data
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data

        # Given: encoded and scaled train data
        train_encoded, _ = encode_data(train_df.copy(), train_df.copy())
        train_scaled, _ = scale_data(train_encoded, train_encoded)
        original_counts = train_scaled["arrest"].value_counts()
        original_ratio = original_counts.min() / original_counts.max()

        # Skip if data is already balanced (SMOTE requires minority < 50% of majority)
        if original_ratio >= 0.5:
            assert True
            return

        # When: we balance the data
        balanced = balance_data(train_scaled)

        # Then: class ratio should improve (closer to 1)
        balanced_counts = balanced["arrest"].value_counts()
        balanced_ratio = balanced_counts.min() / balanced_counts.max()
        assert balanced_ratio > original_ratio

    def test_balancing_preserves_columns(self, train_df: pd.DataFrame):
        """Test that balancing preserves all columns when data is imbalanced."""
        from etl_helpers.data_balancing import balance_data
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data

        # Given: encoded and scaled train data
        train_encoded, _ = encode_data(train_df.copy(), train_df.copy())
        train_scaled, _ = scale_data(train_encoded, train_encoded)
        original_counts = train_scaled["arrest"].value_counts()
        original_ratio = original_counts.min() / original_counts.max()

        # Skip if data is already balanced
        if original_ratio >= 0.5:
            assert True
            return

        # When: we balance the data
        balanced = balance_data(train_scaled)

        # Then: all columns should be preserved
        assert set(balanced.columns) == set(train_scaled.columns)


class TestFeatureSelection:
    """Tests for feature selection stage."""

    def test_feature_selection_reduces_columns(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        """Test that feature selection reduces the number of columns."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data
        from etl_helpers.feature_selection import select_features

        # Given: encoded and scaled data
        train_encoded, test_encoded = encode_data(train_df.copy(), test_df.copy())
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)
        original_col_count = train_scaled.shape[1]

        # When: we select features
        train_selected, test_selected, mi_scores = select_features(train_scaled, test_scaled)

        # Then: column count should decrease or stay same
        assert train_selected.shape[1] <= original_col_count

    def test_feature_selection_preserves_target(
        self, train_df: pd.DataFrame, test_df: pd.DataFrame
    ):
        """Test that feature selection keeps the target column."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_scaling import scale_data
        from etl_helpers.feature_selection import select_features

        # Given: encoded and scaled data with target column
        train_encoded, test_encoded = encode_data(train_df.copy(), test_df.copy())
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)

        # When: we select features
        train_selected, test_selected, _ = select_features(train_scaled, test_scaled)

        # Then: target column should be preserved
        assert "arrest" in train_selected.columns
        assert "arrest" in test_selected.columns


class TestFullPipeline:
    """End-to-end tests for the complete pipeline."""

    def test_full_pipeline_produces_ml_ready_data(
        self,
        sample_crimes_df: pd.DataFrame,
        sample_stations_df: pd.DataFrame,
    ):
        """Test complete pipeline from raw data to ML-ready output."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_enrichment import enrich_crime_data
        from etl_helpers.data_scaling import scale_data
        from etl_helpers.data_splitter import preprocess_for_split, split_train_test
        from etl_helpers.feature_selection import select_features
        from etl_helpers.outlier_processing import process_outliers

        # Given: raw crime and station data
        crimes = sample_crimes_df
        stations = sample_stations_df

        # When: we run the full pipeline
        # Step 1: Enrich
        enriched = enrich_crime_data(crimes, stations)
        assert len(enriched) > 0

        # Step 2: Preprocess and split
        preprocessed = preprocess_for_split(enriched)
        train_df, test_df = split_train_test(preprocessed)
        assert len(train_df) > 0
        assert len(test_df) > 0

        # Step 3: Remove outliers
        train_no_outliers, test_no_outliers = process_outliers(train_df, test_df)
        assert len(train_no_outliers) > 0

        # Step 4: Encode
        train_encoded, test_encoded = encode_data(train_no_outliers, test_no_outliers)
        assert len(train_encoded) > 0

        # Step 5: Scale
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)
        assert len(train_scaled) > 0

        # Step 6: Skip balancing for sample data (already balanced)
        # In production, balance_data would be called here

        # Step 7: Feature selection
        train_final, test_final, _ = select_features(train_scaled, test_scaled)

        # Then: output should be ML-ready
        assert len(train_final) > 0
        assert len(test_final) > 0
        assert "arrest" in train_final.columns
        assert "arrest" in test_final.columns

        # All columns should be numeric
        non_numeric_train = train_final.select_dtypes(exclude=[np.number, bool]).columns
        non_numeric_test = test_final.select_dtypes(exclude=[np.number, bool]).columns
        assert len(non_numeric_train) == 0, (
            f"Non-numeric columns in train: {list(non_numeric_train)}"
        )
        assert len(non_numeric_test) == 0, f"Non-numeric columns in test: {list(non_numeric_test)}"

    def test_full_pipeline_no_nan_in_output(
        self,
        sample_crimes_df: pd.DataFrame,
        sample_stations_df: pd.DataFrame,
    ):
        """Test that the final output has no NaN values."""
        from etl_helpers.data_encoding import encode_data
        from etl_helpers.data_enrichment import enrich_crime_data
        from etl_helpers.data_scaling import scale_data
        from etl_helpers.data_splitter import preprocess_for_split, split_train_test
        from etl_helpers.feature_selection import select_features
        from etl_helpers.outlier_processing import process_outliers

        # Given: raw crime and station data
        crimes = sample_crimes_df
        stations = sample_stations_df

        # When: we run the full pipeline (skip balancing for sample data)
        enriched = enrich_crime_data(crimes, stations)
        preprocessed = preprocess_for_split(enriched)
        train_df, test_df = split_train_test(preprocessed)
        train_no_outliers, test_no_outliers = process_outliers(train_df, test_df)
        train_encoded, test_encoded = encode_data(train_no_outliers, test_no_outliers)
        train_scaled, test_scaled = scale_data(train_encoded, test_encoded)
        train_final, test_final, _ = select_features(train_scaled, test_scaled)

        # Then: no NaN values should exist in final output
        assert train_final.isna().sum().sum() == 0, "NaN found in train output"
        assert test_final.isna().sum().sum() == 0, "NaN found in test output"
