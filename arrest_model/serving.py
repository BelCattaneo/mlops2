"""El modelo servible: el estimador y su preprocesamiento en un solo artefacto.

Separar el modelo de los parámetros con los que se entrenó es la forma más fácil de servir
predicciones equivocadas sin que nada falle. Está medido: el estimador del TP-final, alimentado
con datos codificados con otros parámetros, predice arresto en el 99% de las filas en vez del
15%, sin un solo error.

Por eso el artefacto contiene las dos mitades. Recibe los seis campos crudos del contrato —los
mismos que recibe la API REST— y devuelve la probabilidad: el consumidor no codifica nada, así
que no hay forma de que codifique distinto de como se entrenó.

Valida con el mismo contrato que las APIs, así que también se sostiene expuesto solo.
"""

from typing import Any

import mlflow.pyfunc
import pandas as pd
from xgboost import XGBClassifier

from arrest_model.features import MODEL_FEATURES, encode_payload
from arrest_model.params import load_params
from arrest_model.schemas import EXAMPLE_REPORT, CrimeReport

# Los seis campos crudos, que son la firma de entrada del modelo.
RAW_INPUTS = tuple(EXAMPLE_REPORT)


class ArrestModel(mlflow.pyfunc.PythonModel):
    """Envuelve el estimador y sus parámetros para que viajen y se sirvan juntos."""

    def load_context(self, context: Any) -> None:
        """Carga el estimador y los parámetros desde los artefactos del modelo.

        El estimador se lee con el formato propio de XGBoost y no desde un pickle. Un pickle ata
        al lector al entorno del escritor: el que escribía el contenedor de Airflow pedía `dill`,
        que no está en las imágenes de las APIs, así que el modelo no se podía cargar donde hay
        que servirlo. Y la documentación de XGBoost tampoco garantiza pickles entre versiones.
        """
        self.model = XGBClassifier()
        self.model.load_model(context.artifacts["model"])
        with open(context.artifacts["params"], "rb") as archivo:
            self.params = load_params(archivo.read())

    def predict(
        self, context: Any, model_input: pd.DataFrame, params: dict[str, Any] | None = None
    ) -> Any:
        """Valida los campos crudos, los codifica y devuelve la probabilidad de arresto."""
        reportes = [
            CrimeReport.model_validate(fila) for fila in model_input.to_dict(orient="records")
        ]
        features = encode_payload(reportes, self.params)
        return self.model.predict_proba(features[list(MODEL_FEATURES)])[:, 1]
