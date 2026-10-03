"""Mini-TP 6: el modelo y los datos viviendo en el data lake."""

import io
import uuid

import pytest

from arrest_model.features import MODEL_FEATURES
from tp5_federated.data import LABEL, load_sample
from tp6_datalake.curated import land_curated
from tp6_datalake.ingest import SNAPSHOT_CRIMES, land_raw
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


class DescargaQueFalla:
    """Socrata sin responder: ni red, ni token, ni portal."""

    def __call__(self, dataset: str, **kwargs: object) -> bytes:
        raise OSError("no hay red")


def test_the_reports_land_partitioned_by_day(bucket: str) -> None:
    s3 = client()
    ensure_bucket(s3, bucket)
    aterrizado = land_raw(
        s3, bucket=bucket, day="2026-10-03", download=lambda *a, **k: b"id,date\n1,x\n"
    )
    assert aterrizado["crimes"].endswith("raw/crimes/dia=2026-10-03/crimes.csv")
    assert "raw/crimes/dia=2026-10-03/crimes.csv" in list_keys(s3, "raw/", bucket)


def test_the_stations_land_without_partition(bucket: str) -> None:
    # Las comisarías son 23 filas que no cambian desde 2016: particionarlas por día sería ruido.
    s3 = client()
    ensure_bucket(s3, bucket)
    aterrizado = land_raw(
        s3, bucket=bucket, day="2026-10-03", download=lambda *a, **k: b"district\n1\n"
    )
    assert aterrizado["stations"].endswith("raw/police_stations/police_stations.csv")


def test_without_the_portal_it_falls_back_to_the_snapshot(bucket: str) -> None:
    # Lo que se corrige acá: en la corrección del TP anterior el pipeline murió porque la
    # descarga falló. El respaldo versionado deja que el flujo corra igual.
    s3 = client()
    ensure_bucket(s3, bucket)
    aterrizado = land_raw(s3, bucket=bucket, day="2026-10-03", download=DescargaQueFalla())
    assert aterrizado["origen"] == "respaldo"
    assert len(get_bytes(s3, "raw/crimes/dia=2026-10-03/crimes.csv", bucket)) > 1000


def test_the_snapshot_has_the_fields_the_model_needs() -> None:
    import pandas as pd

    reportes = pd.read_csv(io.BytesIO(SNAPSHOT_CRIMES.read_bytes()), compression="gzip")
    for campo in ("iucr", "primary_type", "location_description", "date", "latitude", "longitude"):
        assert campo in reportes.columns


def test_the_curated_dataset_lands_as_parquet(bucket: str) -> None:
    import pandas as pd

    s3 = client()
    ensure_bucket(s3, bucket)
    uri = land_curated(s3, bucket=bucket)
    assert uri.endswith("curated/arrests/arrests.parquet")
    tabla = pd.read_parquet(io.BytesIO(get_bytes(s3, "curated/arrests/arrests.parquet", bucket)))
    assert list(tabla.columns) == [*MODEL_FEATURES, LABEL]
    assert len(tabla) == len(load_sample())


def test_parquet_takes_less_room_than_the_same_csv(bucket: str) -> None:
    # Es la razón de usarlo en la zona curada: mismo contenido, tipado y más chico.
    s3 = client()
    ensure_bucket(s3, bucket)
    land_curated(s3, bucket=bucket)
    parquet = len(get_bytes(s3, "curated/arrests/arrests.parquet", bucket))
    csv = len(load_sample().to_csv(index=False).encode())
    assert parquet < csv
