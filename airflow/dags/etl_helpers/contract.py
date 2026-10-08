"""El contrato de features del dataset que consume el modelo.

La selección por información mutua depende de los datos: el conjunto de features que elige en
una corrida no está garantizado para la siguiente. Pero la plataforma sirve un modelo entrenado
sobre un espacio de features fijo, así que si el dataset cambia de columnas sin que nadie se
entere, lo que el modelo recibe en producción deja de corresponder a lo que vio entrenando. Ese
desfase tiene nombre: training/serving skew.

Este chequeo lo convierte en una falla ruidosa de la tarea en vez de un modelo que se degrada
en silencio. Es la misma idea que la validación de esquema entre etapas de TFX.

Las features esperadas no se declaran acá: salen de `arrest_model`, que es la codificación
que comparten los cuatro protocolos. Así la plataforma tiene una sola definición del espacio
de features, y el dataset que produce el DAG se le puede dar de comer al modelo sin traducir.

Vive acá y no en el módulo del DAG porque así se puede probar sin Airflow instalado.
"""

from collections.abc import Sequence

import pandas as pd

from arrest_model.features import MODEL_FEATURES

# El contrato no se escribe a mano: son las features del paquete que usan los cuatro protocolos
# para servir. Si el modelo cambia su espacio de features, el contrato del ETL cambia con él.
CURATED_FEATURES = tuple(MODEL_FEATURES)

# El puente entre los nombres del ETL y los del modelo. No es mecánico —`day_of_week_sin` contra
# `Day_sin`, `x_coordinate_standardized` contra `X Coordinate_standardized`— así que va explícito,
# y un test verifica que los valores sean exactamente MODEL_FEATURES, en orden.
CURATED_RENAMES = {
    "iucr_freq": "IUCR_freq",
    "primary_type_freq": "Primary_Type_freq",
    "location_description_freq": "Location_Description_freq",
    "day_of_week_sin": "Day_sin",
    "x_coordinate_standardized": "X Coordinate_standardized",
    "y_coordinate_standardized": "Y Coordinate_standardized",
    "distance_crime_to_police_station_standardized": (
        "Distance Crime To Police Station_standardized"
    ),
}


def rename_to_model(df: pd.DataFrame) -> pd.DataFrame:
    """Pasa las columnas del ETL a los nombres con los que se entrenó el modelo.

    Lo que el mapeo no conoce queda con su nombre, para que el contrato lo vea y falle diciendo
    que sobra en vez de dejarlo pasar.
    """
    return df.rename(columns=CURATED_RENAMES)


def enforce_feature_contract(df: pd.DataFrame, features: Sequence[str], label: str) -> pd.DataFrame:
    """Verifica que el dataset tenga exactamente las features declaradas, y las ordena.

    Devuelve el dataframe con las columnas en el orden del contrato y la etiqueta al final, que
    es el orden con el que se entrenó el modelo. Si sobra o falta alguna, falla diciendo cuál.
    """
    esperadas = [*features, label]
    faltan = [columna for columna in esperadas if columna not in df.columns]
    sobran = [columna for columna in df.columns if columna not in esperadas]
    if faltan or sobran:
        detalle = []
        if faltan:
            detalle.append(f"faltan {', '.join(faltan)}")
        if sobran:
            detalle.append(f"sobran {', '.join(sobran)}")
        raise ValueError(
            f"el dataset curado no cumple el contrato de features: {'; '.join(detalle)}"
        )
    return df[esperadas]


def assert_no_missing(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Falla si el dataset tiene nulos o infinitos, diciendo en qué columnas.

    El pipeline medía el porcentaje de nulos y lo dibujaba en un gráfico que subía a MLflow.
    Medirlo no sirve si nadie mira: un nulo que llega al entrenamiento lo rompe o lo degrada en
    silencio. Acá es una falla de la tarea.
    """
    nulos = {columna: int(cantidad) for columna, cantidad in df.isna().sum().items() if cantidad}
    numericas = df.select_dtypes(include="number")
    infinitos = {
        columna: int(cantidad)
        for columna, cantidad in numericas.isin([float("inf"), float("-inf")]).sum().items()
        if cantidad
    }
    if nulos or infinitos:
        detalle = []
        if nulos:
            detalle.append("nulos en " + ", ".join(f"{c} ({n})" for c, n in nulos.items()))
        if infinitos:
            detalle.append("infinitos en " + ", ".join(f"{c} ({n})" for c, n in infinitos.items()))
        raise ValueError(f"el dataset {name} no está limpio: {'; '.join(detalle)}")
    return df
