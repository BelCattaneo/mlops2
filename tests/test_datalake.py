"""Mini-TP 6: el modelo y los datos viviendo en el data lake."""

import uuid

import pytest

from tp6_datalake.lake import (
    ZONES,
    client,
    ensure_bucket,
    get_bytes,
    lake_available,
    list_keys,
    put_bytes,
)

pytestmark = [
    pytest.mark.minio,
    pytest.mark.skipif(not lake_available(), reason="no hay MinIO escuchando en 9000"),
]


@pytest.fixture
def bucket() -> str:
    """Un bucket propio por test: los objetos del lake sobreviven entre corridas."""
    return f"test-lake-{uuid.uuid4().hex[:8]}"


def test_the_bucket_starts_with_its_three_zones(bucket: str) -> None:
    s3 = client()
    ensure_bucket(s3, bucket)
    for zona in ZONES:
        assert list_keys(s3, f"{zona}/", bucket)


def test_creating_the_bucket_twice_changes_nothing(bucket: str) -> None:
    # El flujo se corre muchas veces: tiene que poder repetirse sin romper ni duplicar.
    s3 = client()
    ensure_bucket(s3, bucket)
    antes = list_keys(s3, "", bucket)
    ensure_bucket(s3, bucket)
    assert list_keys(s3, "", bucket) == antes


def test_what_goes_up_comes_back_identical(bucket: str) -> None:
    s3 = client()
    ensure_bucket(s3, bucket)
    contenido = b"iucr,primary_type\n1310,CRIMINAL DAMAGE\n"
    put_bytes(s3, "raw/prueba.csv", contenido, bucket)
    assert get_bytes(s3, "raw/prueba.csv", bucket) == contenido


def test_the_zones_are_prefixes_not_folders(bucket: str) -> None:
    # En S3 no hay carpetas: la zona es el principio de la clave, y por eso se puede listar.
    s3 = client()
    ensure_bucket(s3, bucket)
    put_bytes(s3, "raw/crimes/dia=2026-10-03/crimes.csv", b"x", bucket)
    put_bytes(s3, "curated/arrests.parquet", b"y", bucket)
    assert "raw/crimes/dia=2026-10-03/crimes.csv" in list_keys(s3, "raw/", bucket)
    assert "raw/crimes/dia=2026-10-03/crimes.csv" not in list_keys(s3, "curated/", bucket)
