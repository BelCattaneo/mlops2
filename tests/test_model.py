"""Carga del modelo empaquetado en model/model.pkl."""

from pathlib import Path

import pytest

from arrest_model.model import load_bundle


def test_load_bundle_reads_committed_model() -> None:
    metadata = load_bundle()["metadata"]
    assert (metadata["name"], metadata["version"]) == ("chicago-arrest-xgboost", 1)


def test_load_bundle_explains_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No existe el modelo"):
        load_bundle(tmp_path / "model.pkl")
