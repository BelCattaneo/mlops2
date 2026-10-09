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
import tempfile
from pathlib import Path

import mlflow
import mlflow.pyfunc
import pandas as pd
from airflow.decorators import dag, task
from etl_config import BUCKET_NAME, DEFAULT_ARGS, TRAINING_EXPERIMENT, config
from etl_helpers.contract import CURATED_FEATURES, enforce_feature_contract
from etl_helpers.keys import curated_params, curated_prefix, curated_test, curated_train
from etl_helpers.minio import (
    download_bytes,
    download_to_dataframe,
    list_objects_with_times,
)
from etl_helpers.partitions import newest_partition, partition_date
from training_helpers import evaluate, fit_model

import arrest_model
from arrest_model.config import MODEL_NAME
from arrest_model.schemas import EXAMPLE_REPORT
from arrest_model.serving import ArrestModel

logger = logging.getLogger(__name__)

TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")


@dag(
    dag_id="train_arrest_model",
    description="Entrena el modelo de arrestos con el dataset curado y lo registra en MLflow",
    default_args=DEFAULT_ARGS,
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
            list_objects_with_times(BUCKET_NAME, prefix=curated_prefix("train"))
        )
        if particion is None:
            raise ValueError(
                f"no hay datasets curados en {curated_prefix('train')}: "
                "hay que correr el ETL antes de entrenar"
            )
        logger.info("Entrenando con la partición curada %s", particion)

        train = download_to_dataframe(BUCKET_NAME, curated_train(particion))
        test = download_to_dataframe(BUCKET_NAME, curated_test(particion))
        # Los parámetros con los que el ETL codificó ese dataset: van DENTRO del artefacto, no
        # al lado. Servir con otros es lo que hace predecir cualquier cosa sin que nada falle.
        params_crudos = download_bytes(BUCKET_NAME, curated_params(particion))
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
        mlflow.set_experiment(TRAINING_EXPERIMENT)
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
            # Se registra el modelo servible, no el estimador: recibe los seis campos
            # crudos del contrato y codifica adentro, así el consumidor no puede codificar
            # distinto de como se entrenó. `code_paths` mete el paquete compartido en el
            # artefacto, que es el que hace esa codificación.
            with tempfile.TemporaryDirectory() as temporal:
                estimador = os.path.join(temporal, "model.ubj")
                parametros = os.path.join(temporal, "params.json")
                modelo.save_model(estimador)
                Path(parametros).write_bytes(params_crudos)
                # La versión sale de lo que devuelve el registro, no de buscar la mayor: con
                # dos entrenamientos a la vez, buscar la mayor marcaría la del otro.
                registrado = mlflow.pyfunc.log_model(
                    name="model",
                    python_model=ArrestModel(),
                    artifacts={"model": estimador, "params": parametros},
                    code_paths=[str(Path(arrest_model.__file__).parent)],
                    registered_model_name=MODEL_NAME,
                    input_example=pd.DataFrame([EXAMPLE_REPORT]),
                )
            registrada = corrida.info.run_id
            version = registrado.registered_model_version

        cliente = mlflow.MlflowClient(TRACKING_URI)
        cliente.set_registered_model_alias(MODEL_NAME, "champion", version)
        logger.info("Versión %s registrada y marcada como champion", version)

        return {
            "status": "success",
            "run_id": registrada,
            "model_version": version,
            "curated_partition": particion,
            "metrics": metricas,
        }

    train_and_register()


dag = train_arrest_model()
