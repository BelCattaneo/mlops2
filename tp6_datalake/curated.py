"""Mini-TP 6: la zona curada, con el dataset listo para entrenar.

En `raw` está lo que llegó, con sus 22 columnas y sus huecos. En `curated` va lo que el modelo
consume: las 7 features y la etiqueta, ya calculadas. Esa separación es lo que evita el pantano:
quien entrena sabe qué dato usar sin tener que adivinar cuál de todos es el bueno.

Va en Parquet y no en CSV porque guarda los tipos, se comprime por columna y permite leer una
columna sola sin recorrer el resto. Hoy el dataset lo produce el pipeline del TP-final; en la
plataforma lo va a escribir el DAG de Airflow.
"""

import io
from typing import Any

from tp5_federated.data import load_sample
from tp6_datalake.lake import BUCKET, put_bytes

KEY = "curated/arrests/arrests.parquet"


def land_curated(s3: Any, bucket: str = BUCKET, key: str = KEY) -> str:
    """Escribe el dataset procesado en la zona curada y devuelve su URI."""
    buffer = io.BytesIO()
    load_sample().to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
    return put_bytes(s3, key, buffer.getvalue(), bucket)
