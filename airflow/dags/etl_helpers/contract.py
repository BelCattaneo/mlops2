"""El contrato de features del dataset que consume el modelo.

La selección por información mutua depende de los datos: el conjunto de features que elige en
una corrida no está garantizado para la siguiente. Pero la plataforma sirve un modelo entrenado
sobre un espacio de features fijo, así que si el dataset cambia de columnas sin que nadie se
entere, lo que el modelo recibe en producción deja de corresponder a lo que vio entrenando. Ese
desfase tiene nombre: training/serving skew.

Este chequeo lo convierte en una falla ruidosa de la tarea en vez de un modelo que se degrada
en silencio. Es la misma idea que la validación de esquema entre etapas de TFX.

Vive acá y no en el módulo del DAG porque así se puede probar sin Airflow instalado.
"""

from collections.abc import Sequence

import pandas as pd


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
