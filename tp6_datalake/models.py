"""Mini-TP 6: el modelo publicado en el lake y servido desde ahí.

Hasta acá, los tres servicios del repo copian `model/model.pkl` adentro de su imagen. Eso ata
el modelo al contenedor: publicar uno nuevo obliga a reconstruir y redesplegar las tres
imágenes, y nada garantiza que las tres estén sirviendo la misma versión.

Con el modelo en el lake, la imagen deja de contenerlo y pasa a saber dónde buscarlo. Publicar
una versión nueva es subir un objeto, y el servicio la toma al arrancar.

La versión va en el prefijo, `models/v1/`, así conviven varias y volver atrás es apuntar a la
anterior en vez de reconstruir nada.
"""

import io
from pathlib import Path
from typing import Any

import joblib
from botocore.exceptions import ClientError

from arrest_model.model import MODEL_PATH
from tp6_datalake.lake import BUCKET, get_bytes, put_bytes

VERSION = "v1"


def model_key(version: str = VERSION) -> str:
    """Dónde vive esa versión del modelo dentro del lake."""
    return f"models/{version}/model.pkl"


def publish_model(
    s3: Any, bucket: str = BUCKET, version: str = VERSION, path: Path = MODEL_PATH
) -> str:
    """Sube el bundle entrenado a la zona de modelos, bajo su versión."""
    return put_bytes(s3, model_key(version), path.read_bytes(), bucket)


def load_model(s3: Any, bucket: str = BUCKET, version: str = VERSION) -> dict[str, Any]:
    """Trae el bundle desde el lake y lo reconstruye en memoria, sin tocar el disco."""
    try:
        crudo = get_bytes(s3, model_key(version), bucket)
    except ClientError as error:
        raise FileNotFoundError(
            f"No hay modelo {version} en s3://{bucket}/{model_key(version)}"
        ) from error
    return joblib.load(io.BytesIO(crudo))
