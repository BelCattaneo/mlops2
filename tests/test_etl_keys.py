"""Las claves que la plataforma escribe en el lake."""

from etl_config import config
from etl_helpers.keys import (
    CURATED_ARTIFACTS,
    curated_params,
    curated_prefix,
    curated_test,
    curated_train,
    enriched_crimes,
    raw_crimes,
    raw_crimes_prefix,
    raw_stations,
)

PARTICION = "2026-10-03"


def test_the_raw_layer_is_partitioned_by_month() -> None:
    assert raw_crimes("2026-10") == "raw/crimes/month=2026-10/crimes.csv"
    assert raw_stations() == "raw/police_stations/police_stations.csv"


def test_the_derived_layers_are_partitioned_by_date() -> None:
    assert enriched_crimes(PARTICION) == "enriched/crimes/date=2026-10-03/crimes.parquet"
    assert curated_train(PARTICION) == "curated/train/date=2026-10-03/train.parquet"
    assert curated_test(PARTICION) == "curated/test/date=2026-10-03/test.parquet"
    assert curated_params(PARTICION) == "curated/params/date=2026-10-03/params.json"


def test_every_key_lives_under_a_layer_so_the_retention_reaches_it() -> None:
    # Una clave fuera de las tres capas no la alcanza ninguna regla de ciclo de vida y queda en
    # el bucket para siempre, sin que nadie se entere.
    capas = (config.PREFIX_RAW, config.PREFIX_ENRICHED, config.PREFIX_CURATED)
    claves = [
        raw_crimes("2026-10"),
        raw_stations(),
        enriched_crimes(PARTICION),
        curated_train(PARTICION),
        curated_test(PARTICION),
        curated_params(PARTICION),
    ]

    assert all(clave.startswith(capas) for clave in claves)


def test_the_prefixes_are_the_prefixes_of_their_keys() -> None:
    # Listar por prefijo y escribir la clave tienen que coincidir: si no, la corrida escribe en
    # un lado y la siguiente busca en otro.
    assert raw_crimes("2026-10").startswith(raw_crimes_prefix())
    assert curated_train(PARTICION).startswith(curated_prefix("train"))


def test_the_curated_layer_declares_its_three_artifacts() -> None:
    # El dataset no está completo sin sus parámetros: el chequeo de idempotencia los mira a los
    # tres, así que una partición vieja sin parámetros se recalcula en vez de darse por hecha.
    claves = [constructor(PARTICION) for constructor in CURATED_ARTIFACTS]

    assert sorted(claves) == sorted(
        [curated_params(PARTICION), curated_test(PARTICION), curated_train(PARTICION)]
    )


def test_the_partition_can_be_read_back_from_the_key() -> None:
    from etl_helpers.partitions import newest_partition

    assert newest_partition([(curated_train(PARTICION), 1.0)]) == PARTICION
