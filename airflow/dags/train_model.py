"""Entrena el modelo con el dataset curado y lo registra en MLflow.

Separado del ETL a propósito: reentrenar no tiene que obligar a volver a procesar los datos, y
procesar datos nuevos no tiene que disparar un entrenamiento. El acople entre los dos es la capa
curada del lake, no una dependencia entre tareas.

El modelo queda registrado con el alias `champion`, que es lo que las APIs van a pedir: así
promover una versión es una operación de registro y no un redespliegue.
"""

import datetime
import logging
import os

import mlflow
from airflow.decorators import dag, task
from etl_config import config
from etl_helpers.contract import CURATED_FEATURES, enforce_feature_contract
from etl_helpers.minio import download_to_dataframe, list_objects_with_times
from etl_helpers.partitions import newest_partition, partition_date
from training_helpers import evaluate, fit_model

from arrest_model.config import MODEL_NAME

logger = logging.getLogger(__name__)

BUCKET_NAME = os.getenv("DATA_REPO_BUCKET_NAME", "data")
TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
EXPERIMENT = "chicago-arrest"

default_args = {
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=5),
    "dagrun_timeout": datetime.timedelta(minutes=60),
}


def latest_partition(keys: list[str]) -> str | None:
    """La partición más reciente de una lista de claves con `date=`, o None si no hay."""
    fechas = {
        parte.removeprefix("date=")
        for clave in keys
        for parte in clave.split("/")
        if "date=" in parte
    }
    return max(fechas) if fechas else None


@dag(
    dag_id="train_arrest_model",
    description="Entrena el modelo de arrestos con el dataset curado y lo registra en MLflow",
    default_args=default_args,
    schedule=None,
    start_date=datetime.datetime(2024, 1, 1),
    catchup=False,
    tags=["training", "Chicago", "MLflow"],
)
def train_arrest_model():
    @task.python
    def train_and_register(**context):
        """Entrena sobre la partición curada más reciente y registra la corrida en MLflow."""
        particion = newest_partition(
            list_objects_with_times(BUCKET_NAME, prefix=f"{config.PREFIX_CURATED}train/")
        )
        if particion is None:
            raise ValueError(
                f"no hay datasets curados en {config.PREFIX_CURATED}train/: "
                "hay que correr el ETL antes de entrenar"
            )
        logger.info("Entrenando con la partición curada %s", particion)

        train = download_to_dataframe(
            BUCKET_NAME, f"{config.PREFIX_CURATED}train/date={particion}/train.parquet"
        )
        test = download_to_dataframe(
            BUCKET_NAME, f"{config.PREFIX_CURATED}test/date={particion}/test.parquet"
        )
        # El contrato se verifica al cargar: una partición vieja, de antes de que el ETL
        # renombrara las columnas, falla diciendo qué le falta en vez de un KeyError pelado.
        train = enforce_feature_contract(train, CURATED_FEATURES, config.TARGET_COLUMN)
        test = enforce_feature_contract(test, CURATED_FEATURES, config.TARGET_COLUMN)
        features = list(CURATED_FEATURES)
        y_train = train[config.TARGET_COLUMN].astype(int)
        y_test = test[config.TARGET_COLUMN].astype(int)

        modelo = fit_model(train[features], y_train)
        metricas = evaluate(modelo, test[features], y_test)
        logger.info("Métricas sobre el test curado: %s", metricas)

        mlflow.set_tracking_uri(TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT)
        sufijo = partition_date(context.get("ds"), datetime.datetime.now(datetime.UTC))
        with mlflow.start_run(run_name=f"train_{sufijo}") as corrida:
            mlflow.log_params(
                {
                    "curated_partition": particion,
                    "train_rows": len(train),
                    "test_rows": len(test),
                    "features": len(features),
                }
            )
            mlflow.log_metrics(metricas)
            # El modelo se registra con los nombres de features puestos, así que servirlo con
            # columnas en otro orden falla en vez de devolver números equivocados.
            mlflow.xgboost.log_model(
                modelo,
                name="model",
                registered_model_name=MODEL_NAME,
                input_example=test[features].head(3),
            )
            registrada = corrida.info.run_id

        cliente = mlflow.MlflowClient(TRACKING_URI)
        version = max(
            cliente.search_model_versions(f"name='{MODEL_NAME}'"),
            key=lambda v: int(v.version),
        )
        cliente.set_registered_model_alias(MODEL_NAME, "champion", version.version)
        logger.info("Versión %s registrada y marcada como champion", version.version)

        return {
            "status": "success",
            "run_id": registrada,
            "model_version": version.version,
            "curated_partition": particion,
            "metrics": metricas,
        }

    train_and_register()


dag = train_arrest_model()
