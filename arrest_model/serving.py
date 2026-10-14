"""El modelo servible: el estimador y su preprocesamiento en un solo artefacto.

Separar el modelo de los parámetros con los que se entrenó es la forma más fácil de servir
predicciones equivocadas sin que nada falle. Está medido: el estimador alimentado con datos
codificados con otros parámetros predice arresto en el 99% de las filas en vez del 15%, con
accuracy 0,16 y AUC 0,53, sin un solo error.

Y el mecanismo explica por qué el colapso es total y no gradual. Tres de las siete features son
codificación por frecuencia, que le asigna a cada categoría un número que depende de la ventana
de datos con la que se ajustó. Los umbrales que aprende un árbol caen entre los valores de dos
categorías vecinas, así que mover las frecuencias un 0,2% —lo que cambian en un mes— hace que
categorías enteras cruzen el umbral de golpe. No hay parámetros "parecidos": son los del modelo
o cualquier cosa.

Por eso el artefacto contiene las tres partes: el estimador, los parámetros con los que se
codifica y el umbral con el que se decide. Recibe los seis campos crudos del contrato —los
mismos que recibe la API REST— y devuelve la probabilidad y la decisión: el consumidor no
codifica ni elige corte, así que no hay forma de que codifique distinto de como se entrenó ni
de que decida distinto de como se midió.

Valida con el mismo contrato que las APIs, así que también se sostiene expuesto solo.
"""

from typing import Any

import mlflow.pyfunc
import pandas as pd
from xgboost import XGBClassifier

from arrest_model.config import DEFAULT_THRESHOLD
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
        # El umbral sale de los parámetros y no del registro: así el artefacto decide igual
        # cargado desde donde sea. Los que se escribieron antes no lo traen y decide el 0,5.
        self.threshold = float(self.params.pop("threshold", DEFAULT_THRESHOLD))

    def predict(
        self, context: Any, model_input: pd.DataFrame, params: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """Valida los campos crudos, los codifica y devuelve probabilidad y decisión.

        Devuelve las dos columnas y no solo la probabilidad porque el umbral es parte del
        modelo: quien carga el artefacto tiene que poder decidir igual que la API sin tener que
        averiguar en el registro con qué corte se midió.
        """
        reportes = [
            CrimeReport.model_validate(fila) for fila in model_input.to_dict(orient="records")
        ]
        features = encode_payload(reportes, self.params)
        probabilidades = self.model.predict_proba(features[list(MODEL_FEATURES)])[:, 1]
        return pd.DataFrame(
            {
                "probability": probabilidades,
                "arrest": (probabilidades > self.threshold).astype(int),
            }
        )
