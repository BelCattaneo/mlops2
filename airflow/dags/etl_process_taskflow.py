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
from airflow.exceptions import AirflowSkipException
from etl_config import BUCKET_NAME, DEFAULT_ARGS, config
from etl_helpers.assets import CURATED_LAYER
from etl_helpers.contract import (
    CURATED_FEATURES,
    assert_no_missing,
    rename_to_model,
    take_contract,
)
from etl_helpers.data_encoding import encode_data as encode_data_fn
from etl_helpers.data_enrichment import enrich_crime_data
from etl_helpers.data_loader import (
    download_crimes_incremental,
    download_police_stations,
)
from etl_helpers.data_scaling import scale_data as scale_data_fn
from etl_helpers.data_splitter import preprocess_for_split, split_train_test
from etl_helpers.keys import (
    CURATED_ARTIFACTS,
    enriched_crimes,
    raw_crimes,
    raw_crimes_prefix,
    raw_stations,
)
from etl_helpers.minio import (
    check_file_exists,
    create_bucket_if_not_exists,
    download_to_dataframe,
    enable_versioning,
    list_objects,
    set_bucket_lifecycle_policy,
    upload_bytes,
    upload_from_dataframe,
    upload_to_minio,
)
from etl_helpers.monitoring import (
    log_pipeline_summary,
    log_raw_data_metrics,
    log_split_metrics,
)
from etl_helpers.outlier_processing import process_outliers as process_outliers_fn
from etl_helpers.params import build_params, dump_params
from etl_helpers.partitions import (
    download_window,
    needs_initial_load,
    partition_date,
    partitions_in_window,
    split_by_month,
)
from etl_helpers.summary import summary_counts, wrote_new_partition
from lineage_graph import curated_statements, enriched_statements, raw_statements, record

logger = logging.getLogger(__name__)


@dag(
    dag_id="etl_with_taskflow",
    description="Chicago Crime Data ETL Pipeline with TaskFlow API",
    default_args=DEFAULT_ARGS,
    schedule="@monthly",  # Run monthly for incremental updates
    start_date=datetime.datetime(2024, 1, 1),
    catchup=False,
    # Dos corridas a la vez se pisan en el lake: `make stack-dag` despausa y dispara, así que en
    # una instalación nueva el scheduler crea su corrida del período y la manual arranca junto.
    # Medido: la manual encontró el mes que la programada acababa de escribir, tomó el atajo y
    # publicó un dataset curado de 429 filas mientras la otra todavía bajaba el histórico.
    max_active_runs=1,
    tags=["ETL", "Chicago", "Crime", "TaskFlow"],
)
def process_etl_taskflow():
    @task.python
    def setup_s3():
        """Crea el bucket, lo versiona y le pone la retención de cada capa."""
        create_bucket_if_not_exists(BUCKET_NAME)
        enable_versioning(BUCKET_NAME)
        set_bucket_lifecycle_policy(BUCKET_NAME, {config.PREFIX_ENRICHED: config.ENRICHED_TTL_DAYS})

    def escribir_por_mes(reportes: pd.DataFrame) -> int:
        """Escribe los reportes en la partición de su propio mes y devuelve cuántos fueron."""
        escritas = 0
        for mes, grupo in split_by_month(reportes).items():
            upload_from_dataframe(grupo, BUCKET_NAME, raw_crimes(mes))
            logger.info("Capa cruda: %d reportes en month=%s", len(grupo), mes)
            escritas += len(grupo)
        return escritas

    @task.python
    def land_raw(**context):
        """Deja en la capa cruda los reportes del período y las comisarías, sin tocarlos."""
        inicio, fin = download_window(
            context.get("data_interval_start"),
            context.get("data_interval_end"),
            now=datetime.datetime.now(datetime.UTC),
        )
        crimes_key = raw_crimes(inicio.strftime("%Y-%m"))
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
        faltan_comisarias = not check_file_exists(BUCKET_NAME, raw_stations())
        # La carga inicial se decide mirando la ventana, no el archivo del mes. Preguntar solo
        # por el mes corriente dejaba a una instalación nueva entrenando con diez días de datos:
        # cualquier corrida que escribiera ese archivo y se cortara antes del histórico hacía que
        # todas las siguientes tomaran el atajo e informaran `success`.
        falta_el_historico = needs_initial_load(
            list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()),
            fin,
            config.ROLLING_WINDOW_DAYS,
        )
        if not faltan_reportes and not faltan_comisarias and not falta_el_historico:
            # El atajo también escribe el linaje: son `MERGE`, así que repetirlos no cambia el
            # grafo, y si una corrida anterior lo escribió con Neo4j caído, esta lo repara. Sin
            # esto el hueco sería permanente, porque esa partición ya nunca se vuelve a calcular.
            linaje = record(
                raw_statements(
                    partitions_in_window(
                        list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()),
                        fin,
                        config.ROLLING_WINDOW_DAYS,
                    )
                )
            )
            return {
                "status": "success",
                "crimes_file": crimes_key,
                "rows": None,
                "lineage": linaje,
                **ventana,
            }

        filas = None
        with tempfile.TemporaryDirectory() as temporal:
            if faltan_comisarias:
                comisarias = os.path.join(temporal, "police_stations.csv")
                download_police_stations(output_file=comisarias)
                upload_to_minio(comisarias, BUCKET_NAME, raw_stations())

            if faltan_reportes or falta_el_historico:
                filas = 0

            if faltan_reportes:
                reportes = os.path.join(temporal, "crimes.csv")
                # Que el período venga vacío es normal: el portal publica con unos días de
                # retraso, así que el mes corriente puede no tener nada todavía. Eso no puede
                # abortar la carga inicial, que es lo que de verdad llena la ventana.
                del_periodo = download_crimes_incremental(inicio, fin, output_file=reportes)
                if len(del_periodo):
                    filas += escribir_por_mes(del_periodo)

            if falta_el_historico:
                # Hay que traer los meses anteriores de la ventana. Cada uno va a SU partición y
                # no a la del mes corriente, porque la ventana se determina por qué particiones
                # se leen y una que abarcara doce meses rompería el recorte.
                historico = os.path.join(temporal, "historico.csv")
                desde = fin - datetime.timedelta(days=config.ROLLING_WINDOW_DAYS)
                anteriores = download_crimes_incremental(desde, inicio, output_file=historico)
                logger.info("Carga inicial: %d reportes anteriores al período", len(anteriores))
                if len(anteriores):
                    filas += escribir_por_mes(anteriores)

            # Que no aterrice nada nuevo es normal: el portal publica con atraso, así que el
            # mes corriente puede estar vacío. Eso no es "no hay datos" mientras la ventana
            # tenga particiones, y cortar ahí dejaría sin construir las capas derivadas aunque
            # la ventana se haya corrido un mes.
            if filas == 0 and not partitions_in_window(
                list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()),
                fin,
                config.ROLLING_WINDOW_DAYS,
            ):
                return {"status": "no_data", "rows": 0, **ventana}

        particiones = partitions_in_window(
            list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()), fin, config.ROLLING_WINDOW_DAYS
        )
        linaje = record(raw_statements(particiones))
        return {
            "status": "success",
            "crimes_file": crimes_key,
            "rows": filas,
            "lineage": linaje,
            **ventana,
        }

    @task.python
    def build_enriched(raw, **context):
        """Junta las particiones de la ventana, enriquece y limpia."""
        if raw.get("status") == "no_data":
            return {"status": "no_data"}

        sufijo = raw["partition_date"]
        destino = enriched_crimes(sufijo)
        if check_file_exists(BUCKET_NAME, destino):
            linaje = record(
                enriched_statements(
                    destino,
                    partitions_in_window(
                        list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()),
                        datetime.datetime.fromisoformat(raw["window_end"]),
                        config.ROLLING_WINDOW_DAYS,
                    ),
                )
            )
            return {
                "status": "success",
                "enriched_file": destino,
                "partition_date": sufijo,
                "lineage": linaje,
            }

        particiones = partitions_in_window(
            list_objects(BUCKET_NAME, prefix=raw_crimes_prefix()),
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
        comisarias = download_to_dataframe(BUCKET_NAME, raw_stations())

        log_raw_data_metrics(crimenes, run_name=f"raw_data_{sufijo}")
        enriquecido = preprocess_for_split(enrich_crime_data(crimenes, comisarias))
        upload_from_dataframe(enriquecido, BUCKET_NAME, destino)

        linaje = record(enriched_statements(destino, particiones))
        return {
            "status": "success",
            "enriched_file": destino,
            "partition_date": sufijo,
            "raw_rows": len(crimenes),
            "rows": len(enriquecido),
            "lineage": linaje,
        }

    @task.python
    def build_curated(enriched):
        """Corta, saca outliers, codifica y escala, y deja las features del contrato."""
        if enriched.get("status") == "no_data":
            return {"status": "no_data"}

        sufijo = enriched["partition_date"]
        train_key, test_key, params_key = (clave(sufijo) for clave in CURATED_ARTIFACTS)
        # Los tres artefactos, no solo los datasets: una partición sin sus parámetros no se
        # puede servir, así que darla por completa dejaría al entrenamiento sin con qué armar el
        # modelo. Es el caso de las particiones escritas antes de que los parámetros existieran.
        if all(check_file_exists(BUCKET_NAME, clave(sufijo)) for clave in CURATED_ARTIFACTS):
            linaje = record(curated_statements(train_key, enriched["enriched_file"]))
            return {
                "status": "success",
                "train_file": train_key,
                "test_file": test_key,
                "params_file": params_key,
                "lineage": linaje,
            }

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

        train, test, frecuencias = encode_data_fn(train, test)
        train, test, escala = scale_data_fn(train, test)

        # No hay etapa de balanceo: el desbalance lo maneja el entrenamiento con
        # `scale_pos_weight`, que es lo que XGBoost ofrece para eso. El dataset curado queda con
        # las filas reales y su proporción real de arrestos, que es también la que ve el modelo
        # en producción. Medido sobre la ventana entera: pesar la clase da mejor AUC y mejor MCC
        # que SMOTE más submuestreo, y además es determinista.

        # Las columnas pasan a los nombres del modelo y el contrato de `arrest_model` se queda
        # con las features que el modelo necesita: no hay etapa de selección porque el contrato
        # ES la selección. Si falta alguna, la tarea falla diciendo cuál en vez de dejar en el
        # lake un dataset que el modelo no puede consumir.
        elegidas_train = assert_no_missing(
            take_contract(rename_to_model(train), CURATED_FEATURES, config.TARGET_COLUMN),
            "curated/train",
        )
        elegidas_test = assert_no_missing(
            take_contract(rename_to_model(test), CURATED_FEATURES, config.TARGET_COLUMN),
            "curated/test",
        )

        # Los parámetros del preprocesamiento se guardan al lado del dataset: el modelo que
        # se entrene con él tiene que servirse con estos, no con otros ajustados aparte.
        comisarias = download_to_dataframe(BUCKET_NAME, raw_stations())
        upload_bytes(
            dump_params(build_params(frecuencias, escala, comisarias)), BUCKET_NAME, params_key
        )

        upload_from_dataframe(elegidas_train, BUCKET_NAME, train_key)
        upload_from_dataframe(elegidas_test, BUCKET_NAME, test_key)

        linaje = record(curated_statements(train_key, enriched["enriched_file"]))
        return {
            "status": "success",
            "train_file": train_key,
            "test_file": test_key,
            "params_file": params_key,
            "lineage": linaje,
            "split_rows": filas_corte,
            "rows": (len(elegidas_train), len(elegidas_test)),
            "features": len([c for c in elegidas_train.columns if c != config.TARGET_COLUMN]),
        }

    @task.python
    def log_summary(raw, enriched, curated):
        """Registra el resumen de la corrida con los conteos que trae cada capa.

        Los conteos vienen por XCom y no de volver a bajar los datasets: cada capa sabe cuántas
        filas dejó en cada paso interno, así que el resumen no necesita leer nada del bucket.
        """
        # Si alguna capa no pudo escribir su linaje, el hueco queda registrado como métrica en
        # vez de quedar en silencio: un grafo incompleto es tan malo para auditar como uno falso.
        escrito = all(capa.get("lineage", True) for capa in (raw, enriched, curated))
        if not escrito:
            logger.warning("Alguna capa no pudo escribir su linaje en el grafo")

        conteos = summary_counts(raw, enriched, curated)
        if conteos is None:
            logger.info("Las capas no recalcularon nada: no hay corrida que resumir")
            return {"status": "skipped", "lineage": escrito}

        log_pipeline_summary(
            **conteos,
            lineage_written=float(escrito),
            run_name=f"pipeline_summary_{raw['partition_date']}",
        )
        return {"status": "success", "lineage": escrito}

    @task.python(outlets=[CURATED_LAYER])
    def publish_curated(curated):
        """Publica la capa curada, que es lo que dispara el entrenamiento.

        Es una tarea aparte y no un `outlets` sobre `build_curated` porque el aviso tiene que
        poder no salir, y una tarea que se saltea no emite el evento. No sale cuando no hubo
        dato nuevo, ni cuando la partición ya estaba: entrenar ahí daría una versión más sobre
        exactamente los mismos datos. El criterio lo decide `wrote_new_partition`, el mismo
        que mira el resumen.
        """
        if not wrote_new_partition(curated):
            raise AirflowSkipException("sin partición curada nueva: no hay nada que entrenar")
        logger.info("Capa curada publicada: %s", curated["train_file"])
        return curated["train_file"]

    crudo = land_raw()
    limpio = build_enriched(crudo)
    final = build_curated(limpio)
    setup_s3() >> crudo >> limpio >> final >> log_summary(crudo, limpio, final)
    publish_curated(final)


dag = process_etl_taskflow()
