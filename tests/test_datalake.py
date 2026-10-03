"""Mini-TP 6: el modelo y los datos viviendo en el data lake."""

import io
import uuid
from collections.abc import Iterator

import pytest
from botocore.exceptions import ClientError

from arrest_model.features import MODEL_FEATURES
from arrest_model.model import load_bundle, predict
from arrest_model.schemas import CrimeReport
from tp4_streaming.events import crime_stream
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
from tp6_datalake.models import load_model, publish_model
from tp6_datalake.run import run_lake
from tp6_datalake.tracking import artifacts_of, log_run, metrics_of, tracking_available

pytestmark = [
    pytest.mark.minio,
    pytest.mark.skipif(not lake_available(), reason="no hay MinIO escuchando en 9000"),
]


@pytest.fixture
def bucket() -> Iterator[str]:
    """Un bucket propio por test, que se borra al terminar.

    Propio porque los objetos del lake sobreviven entre corridas y un nombre fijo haría que
    una corrida vea lo que dejó la anterior. Y se borra porque si no, cada pasada de la suite
    deja sus buckets en el MinIO de la máquina.
    """
    nombre = f"test-lake-{uuid.uuid4().hex[:8]}"
    yield nombre
    s3 = client()
    try:
        for clave in list_keys(s3, bucket=nombre):
            s3.delete_object(Bucket=nombre, Key=clave)
        s3.delete_bucket(Bucket=nombre)
    except ClientError:
        # El test puede no haber llegado a crearlo.
        pass


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


def test_the_model_is_published_under_its_version(bucket: str) -> None:
    s3 = client()
    ensure_bucket(s3, bucket)
    uri = publish_model(s3, bucket=bucket, version="v1")
    assert uri.endswith("models/v1/model.pkl")
    assert "models/v1/model.pkl" in list_keys(s3, "models/", bucket)


def test_the_model_from_the_lake_predicts_exactly_like_the_local_one(bucket: str) -> None:
    # El invariante del TP: el modelo que viajó al lake y volvió tiene que dar lo mismo que el
    # del disco. Si difiere, algo se corrompió en el camino y las predicciones no son confiables.
    s3 = client()
    ensure_bucket(s3, bucket)
    publish_model(s3, bucket=bucket, version="v1")
    reportes = [CrimeReport.model_validate(evento) for evento in crime_stream(50, seed=4)]
    desde_el_lake = load_model(s3, bucket=bucket, version="v1")
    assert predict(desde_el_lake, reportes) == predict(load_bundle(), reportes)


def test_two_versions_live_side_by_side(bucket: str) -> None:
    # Así se publica un modelo nuevo sin tocar el que está sirviendo: cambia el prefijo.
    s3 = client()
    ensure_bucket(s3, bucket)
    publish_model(s3, bucket=bucket, version="v1")
    publish_model(s3, bucket=bucket, version="v2")
    assert {"models/v1/model.pkl", "models/v2/model.pkl"} <= set(list_keys(s3, "models/", bucket))


def test_asking_for_a_version_that_is_not_there_says_so(bucket: str) -> None:
    s3 = client()
    ensure_bucket(s3, bucket)
    with pytest.raises(FileNotFoundError, match="v9"):
        load_model(s3, bucket=bucket, version="v9")


necesita_mlflow = pytest.mark.skipif(
    not tracking_available(), reason="no hay servidor de MLflow en 5001"
)


@pytest.mark.mlflow
@necesita_mlflow
def test_the_run_records_the_metrics_of_the_model() -> None:
    corrida = log_run(experiment="tp6-test")
    metricas = metrics_of(corrida)
    assert metricas["mcc"] == pytest.approx(load_bundle()["metadata"]["metrics"]["mcc"], abs=1e-6)


@pytest.mark.mlflow
@necesita_mlflow
def test_the_artifact_of_the_run_ends_up_in_the_lake() -> None:
    # Lo que se prueba acá es la integración: MLflow guarda su metadata en Postgres, pero el
    # artefacto viaja a MinIO. Si no, el modelo quedaría dentro del contenedor de MLflow.
    corrida = log_run(experiment="tp6-test")
    # MLflow ordena el bucket como experimento/corrida/artifacts/...
    claves = list_keys(client(), bucket="mlflow")
    assert any(clave.endswith(f"{corrida}/artifacts/model.pkl") for clave in claves)
    assert artifacts_of(corrida) == ["model.pkl"]


def test_the_command_walks_the_whole_lake(bucket: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_lake(bucket=bucket, with_mlflow=False) == 0
    salida = capsys.readouterr().out
    for zona in ZONES:
        assert zona in salida
    assert "predicción desde el lake" in salida


def test_the_command_reports_where_the_raw_data_came_from(
    bucket: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # Si cayó al respaldo tiene que verse en la salida, no solo en el log.
    run_lake(bucket=bucket, with_mlflow=False)
    assert "socrata" in capsys.readouterr().out or "respaldo" in capsys.readouterr().out
