"""Codificación del payload: se compara contra las features del TP-final."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from arrest_model.features import ENCODERS, MODEL_FEATURES, encode_frame, encode_payload
from arrest_model.schemas import CrimeReport

CASES = Path(__file__).parent / "data" / "encoding_cases.csv"
DISTANCE = "Distance Crime To Police Station_standardized"


@pytest.fixture(scope="module")
def cases() -> pd.DataFrame:
    """50 filas de test del TP-final: los campos crudos y las 7 features de final_test.csv."""
    return pd.read_csv(CASES, dtype={"iucr": str}, keep_default_na=False)


def test_encoding_matches_tp_final(bundle: dict[str, Any], cases: pd.DataFrame) -> None:
    diff = (encode_frame(cases, bundle["params"]) - cases[MODEL_FEATURES]).abs().max()
    assert (diff.drop(DISTANCE) < 1e-6).all()
    assert diff[DISTANCE] < 1e-3  # pyproj vs geopandas: hasta ~0.03 m de diferencia


def test_predicted_class_matches_tp_final(bundle: dict[str, Any], cases: pd.DataFrame) -> None:
    model = bundle["model"]
    from_raw = model.predict(encode_frame(cases, bundle["params"]))
    assert (from_raw == model.predict(cases[MODEL_FEATURES])).all()


def test_unseen_categories_get_zero_frequency(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    report = CrimeReport.model_validate(
        valid_payload | {"iucr": "999Z", "location_description": "MOON BASE"}
    )
    row = encode_payload([report], bundle["params"]).iloc[0]
    assert row["IUCR_freq"] == row["Location_Description_freq"] == 0.0
    assert row["Primary_Type_freq"] > 0.0


@pytest.mark.parametrize(
    ("date", "day_num"),
    [("2024-12-29T12:00:00", 1), ("2024-12-31T23:58:00", 3), ("2024-12-28T12:00:00", 7)],
)
def test_day_sine_counts_sunday_as_one(
    bundle: dict[str, Any], valid_payload: dict[str, Any], date: str, day_num: int
) -> None:
    report = CrimeReport.model_validate(valid_payload | {"date": date})
    row = encode_payload([report], bundle["params"]).iloc[0]
    assert row["Day_sin"] == pytest.approx(np.sin(2 * np.pi * day_num / 7))


def test_missing_location_is_encoded_as_unknown(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    report = CrimeReport.model_validate(valid_payload | {"location_description": None})
    row = encode_payload([report], bundle["params"]).iloc[0]
    unknown = bundle["params"]["freq"]["location_description"]["UNKNOWN"]
    assert row["Location_Description_freq"] == unknown


def test_encoders_define_the_model_feature_order(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    features = encode_payload([CrimeReport.model_validate(valid_payload)], bundle["params"])
    assert list(ENCODERS) == MODEL_FEATURES == list(bundle["model"].feature_names_in_)
    assert list(features.columns) == MODEL_FEATURES
