"""Serialización de los datasets del ETL: qué conserva Parquet que CSV pierde."""

import pandas as pd
import pytest
from etl_helpers.minio.operations import frame_from_bytes, frame_to_bytes


@pytest.fixture
def frame_con_tipos() -> pd.DataFrame:
    """Un dataframe con los tipos que el ETL mueve entre etapas."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02 03:04:05", "2026-07-08 09:10:11"]),
            "district": pd.array([7, None], dtype="Int64"),
            "arrest": [True, False],
            "distance": [1234.567890123456, 0.1 + 0.2],
            "primary_type": ["THEFT", "BATTERY"],
        }
    )


def test_parquet_roundtrip_preserves_dtypes(frame_con_tipos: pd.DataFrame) -> None:
    vuelta = frame_from_bytes(frame_to_bytes(frame_con_tipos, "x/y.parquet"), "x/y.parquet")

    assert list(vuelta.dtypes.astype(str)) == list(frame_con_tipos.dtypes.astype(str))


def test_parquet_roundtrip_preserves_values(frame_con_tipos: pd.DataFrame) -> None:
    vuelta = frame_from_bytes(frame_to_bytes(frame_con_tipos, "x/y.parquet"), "x/y.parquet")

    pd.testing.assert_frame_equal(vuelta, frame_con_tipos)


def test_csv_roundtrip_loses_the_date_type(frame_con_tipos: pd.DataFrame) -> None:
    # Por esto las capas derivadas pasan a Parquet: el CSV no tiene sistema de tipos, así que
    # la fecha vuelve como texto y el entero con nulos vuelve como flotante.
    vuelta = frame_from_bytes(frame_to_bytes(frame_con_tipos, "x/y.csv"), "x/y.csv")

    assert not pd.api.types.is_datetime64_any_dtype(vuelta["date"])
    assert str(vuelta["district"].dtype) != "Int64"


def test_the_format_comes_from_the_key_extension(frame_con_tipos: pd.DataFrame) -> None:
    # Las dos capas conviven: lo crudo sigue en CSV y lo derivado va en Parquet.
    assert frame_to_bytes(frame_con_tipos, "raw/x.csv").startswith(b"date,")
    assert frame_to_bytes(frame_con_tipos, "curated/x.parquet").startswith(b"PAR1")


def test_parquet_is_smaller_than_csv(frame_con_tipos: pd.DataFrame) -> None:
    grande = pd.concat([frame_con_tipos] * 500, ignore_index=True)

    assert len(frame_to_bytes(grande, "x.parquet")) < len(frame_to_bytes(grande, "x.csv"))
