"""ETL de los reportes de crímenes de Chicago, en tres capas.

`raw` guarda lo que llegó del portal tal como llegó, partido por mes. `enriched` tiene el
dataset limpio, con la comisaría más cercana y las features temporales. `curated` tiene el par
de entrenamiento y prueba que consume el modelo.

Una tarea por capa, y no una por transformación: en Airflow la granularidad de tarea es la de
materialización, porque XCom no transporta dataframes, así que una tarea por paso obligaría a
escribir el dataset entero entre paso y paso. Los conteos de cada paso interno viajan igual, en
el XCom de su capa, y de ahí sale el resumen de la corrida.
"""

import datetime
import logging
import os
import tempfile

import pandas as pd
from airflow.decorators import dag, task
from etl_config import BUCKET_NAME, DEFAULT_ARGS, config
from etl_helpers.contract import (
    CURATED_FEATURES,
    assert_no_missing,
    enforce_feature_contract,
    rename_to_model,
)
from etl_helpers.data_balancing import balance_data as balance_data_fn
from etl_helpers.data_encoding import encode_data as encode_data_fn
from etl_helpers.data_enrichment import enrich_crime_data
from etl_helpers.data_loader import (
    download_crimes_incremental,
    download_police_stations,
)
from etl_helpers.data_scaling import scale_data as scale_data_fn
from etl_helpers.data_splitter import preprocess_for_split, split_train_test
from etl_helpers.feature_selection import select_features as select_features_fn
from etl_helpers.minio import (
    check_file_exists,
    create_bucket_if_not_exists,
    download_to_dataframe,
    enable_versioning,
    list_objects,
    set_bucket_lifecycle_policy,
    upload_from_dataframe,
    upload_to_minio,
)
from etl_helpers.monitoring import (
    log_balance_metrics,
    log_feature_selection_metrics,
    log_pipeline_summary,
    log_raw_data_metrics,
    log_split_metrics,
)
from etl_helpers.outlier_processing import process_outliers as process_outliers_fn
from etl_helpers.partitions import download_window, partition_date, partitions_in_window
from etl_helpers.summary import summary_counts

logger = logging.getLogger(__name__)


STATIONS_KEY = f"{config.PREFIX_RAW}police_stations/police_stations.csv"


@dag(
    dag_id="etl_with_taskflow",
    description="Chicago Crime Data ETL Pipeline with TaskFlow API",
    default_args=DEFAULT_ARGS,
    schedule="@monthly",  # Run monthly for incremental updates
    start_date=datetime.datetime(2024, 1, 1),
    catchup=False,
    tags=["ETL", "Chicago", "Crime", "TaskFlow"],
)
def process_etl_taskflow():
    @task.python
    def setup_s3():
        """Crea el bucket, lo versiona y le pone la retención de cada capa."""
        create_bucket_if_not_exists(BUCKET_NAME)
        enable_versioning(BUCKET_NAME)
        set_bucket_lifecycle_policy(BUCKET_NAME, {config.PREFIX_ENRICHED: config.ENRICHED_TTL_DAYS})

    @task.python
    def land_raw(**context):
        """Deja en la capa cruda los reportes del período y las comisarías, sin tocarlos."""
        inicio, fin = download_window(
            context.get("data_interval_start"),
            context.get("data_interval_end"),
            now=datetime.datetime.now(datetime.UTC),
        )
        crimes_key = f"{config.PREFIX_RAW}crimes/month={inicio.strftime('%Y-%m')}/crimes.csv"
        # La ventana y el sufijo viajan en el XCom: así las capas de una misma corrida no
        # pueden escribir en particiones distintas, y no dependen de que haya fecha lógica.
        ventana = {
            "window_end": fin.isoformat(),
            "partition_date": partition_date(context.get("ds"), fin),
        }

        # Las dos claves se chequean por separado. Si se chequeara solo la de crímenes, una
        # corrida cortada entre las dos subidas dejaría la capa sin comisarías para siempre: el
        # reintento saltearía todo y la capa intermedia fallaría en cada corrida. Y separarlas
        # evita bajar de nuevo el año entero cuando lo único que falta son 23 comisarías.
        faltan_reportes = not check_file_exists(BUCKET_NAME, crimes_key)
        faltan_comisarias = not check_file_exists(BUCKET_NAME, STATIONS_KEY)
        if not faltan_reportes and not faltan_comisarias:
            return {"status": "success", "crimes_file": crimes_key, "rows": None, **ventana}

        filas = None
        with tempfile.TemporaryDirectory() as temporal:
            if faltan_comisarias:
                comisarias = os.path.join(temporal, "police_stations.csv")
                download_police_stations(output_file=comisarias)
                upload_to_minio(comisarias, BUCKET_NAME, STATIONS_KEY)

            if faltan_reportes:
                # Sin particiones previas hay que traer la ventana entera; con particiones, solo
                # el período de la corrida, porque el resto ya está en la capa cruda.
                previas = partitions_in_window(
                    list_objects(BUCKET_NAME, prefix=f"{config.PREFIX_RAW}crimes/"),
                    fin,
                    config.ROLLING_WINDOW_DAYS,
                )
                desde = (
                    inicio if previas else fin - datetime.timedelta(days=config.ROLLING_WINDOW_DAYS)
                )
                reportes = os.path.join(temporal, "crimes.csv")
                crimes_df = download_crimes_incremental(desde, fin, output_file=reportes)
                if len(crimes_df) == 0:
                    return {"status": "no_data", "rows": 0, **ventana}
                upload_to_minio(reportes, BUCKET_NAME, crimes_key)
                filas = len(crimes_df)

        return {"status": "success", "crimes_file": crimes_key, "rows": filas, **ventana}

    @task.python
    def build_enriched(raw, **context):
        """Junta las particiones de la ventana, enriquece y limpia."""
        if raw.get("status") == "no_data":
            return {"status": "no_data"}

        sufijo = raw["partition_date"]
        destino = f"{config.PREFIX_ENRICHED}crimes/date={sufijo}/crimes.parquet"
        if check_file_exists(BUCKET_NAME, destino):
            return {
                "status": "success",
                "enriched_file": destino,
                "partition_date": sufijo,
            }

        particiones = partitions_in_window(
            list_objects(BUCKET_NAME, prefix=f"{config.PREFIX_RAW}crimes/"),
            datetime.datetime.fromisoformat(raw["window_end"]),
            config.ROLLING_WINDOW_DAYS,
        )
        if not particiones:
            raise ValueError(
                f"no hay particiones crudas en los últimos {config.ROLLING_WINDOW_DAYS} días "
                f"bajo {config.PREFIX_RAW}crimes/: la capa cruda está vacía o quedó fuera de "
                "la ventana"
            )
        logger.info("Capa cruda: %d particiones en la ventana", len(particiones))
        crimenes = pd.concat(
            [download_to_dataframe(BUCKET_NAME, clave) for clave in particiones],
            ignore_index=True,
        )
        comisarias = download_to_dataframe(BUCKET_NAME, STATIONS_KEY)

        log_raw_data_metrics(crimenes, run_name=f"raw_data_{sufijo}")
        enriquecido = preprocess_for_split(enrich_crime_data(crimenes, comisarias))
        upload_from_dataframe(enriquecido, BUCKET_NAME, destino)

        return {
            "status": "success",
            "enriched_file": destino,
            "partition_date": sufijo,
            "raw_rows": len(crimenes),
            "rows": len(enriquecido),
        }

    @task.python
    def build_curated(enriched):
        """Corta, saca outliers, codifica, escala, balancea y selecciona features."""
        if enriched.get("status") == "no_data":
            return {"status": "no_data"}

        sufijo = enriched["partition_date"]
        train_key = f"{config.PREFIX_CURATED}train/date={sufijo}/train.parquet"
        test_key = f"{config.PREFIX_CURATED}test/date={sufijo}/test.parquet"
        if check_file_exists(BUCKET_NAME, train_key) and check_file_exists(BUCKET_NAME, test_key):
            return {"status": "success", "train_file": train_key, "test_file": test_key}

        limpio = download_to_dataframe(BUCKET_NAME, enriched["enriched_file"])

        train, test = split_train_test(
            limpio,
            test_size=config.SPLIT_TEST_SIZE,
            random_state=config.SPLIT_RANDOM_STATE,
            stratify_column=config.TARGET_COLUMN,
        )
        log_split_metrics(
            train, test, target_column=config.TARGET_COLUMN, run_name=f"split_{sufijo}"
        )
        filas_corte = (len(train), len(test))

        train, test = process_outliers_fn(train, test, n_std=config.OUTLIER_STD_THRESHOLD)

        train, test = encode_data_fn(train, test)
        train, test = scale_data_fn(train, test)

        balanceado = balance_data_fn(train, target_column=config.TARGET_COLUMN)
        log_balance_metrics(
            train, balanceado, target_column=config.TARGET_COLUMN, run_name=f"balance_{sufijo}"
        )

        elegidas_train, elegidas_test, mi_scores = select_features_fn(
            balanceado,
            test,
            target_column=config.TARGET_COLUMN,
            mi_threshold=config.MI_THRESHOLD,
        )
        log_feature_selection_metrics(
            balanceado,
            elegidas_train,
            mi_scores_df=mi_scores,
            target_column=config.TARGET_COLUMN,
            run_name=f"features_{sufijo}",
        )

        # Las columnas pasan a los nombres del modelo y ahí se verifica el contrato: si la
        # selección cambió de features, la tarea falla en vez de dejar en el lake un dataset que
        # el modelo no puede consumir. El contrato sale de `arrest_model`, no de una lista propia.
        elegidas_train = assert_no_missing(
            enforce_feature_contract(
                rename_to_model(elegidas_train), CURATED_FEATURES, config.TARGET_COLUMN
            ),
            "curated/train",
        )
        elegidas_test = assert_no_missing(
            enforce_feature_contract(
                rename_to_model(elegidas_test), CURATED_FEATURES, config.TARGET_COLUMN
            ),
            "curated/test",
        )

        upload_from_dataframe(elegidas_train, BUCKET_NAME, train_key)
        upload_from_dataframe(elegidas_test, BUCKET_NAME, test_key)

        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
            "split_rows": filas_corte,
            "balanced_rows": len(balanceado),
            "rows": (len(elegidas_train), len(elegidas_test)),
            "features": len([c for c in elegidas_train.columns if c != config.TARGET_COLUMN]),
        }

    @task.python
    def log_summary(raw, enriched, curated):
        """Registra el resumen de la corrida con los conteos que trae cada capa.

        Los conteos vienen por XCom y no de volver a bajar los datasets: cada capa sabe cuántas
        filas dejó en cada paso interno, así que el resumen no necesita leer nada del bucket.
        """
        conteos = summary_counts(raw, enriched, curated)
        if conteos is None:
            logger.info("Las capas no recalcularon nada: no hay corrida que resumir")
            return {"status": "skipped"}

        log_pipeline_summary(**conteos, run_name=f"pipeline_summary_{raw['partition_date']}")
        return {"status": "success"}

    crudo = land_raw()
    limpio = build_enriched(crudo)
    final = build_curated(limpio)
    setup_s3() >> crudo >> limpio >> final >> log_summary(crudo, limpio, final)


dag = process_etl_taskflow()
