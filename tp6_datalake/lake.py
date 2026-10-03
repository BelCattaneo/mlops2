"""Mini-TP 6: el data lake, hablado por la API de S3.

El lake es MinIO corriendo en Docker, que habla el mismo protocolo que S3. Lo que vale de eso
es que el código no cambia si mañana el bucket vive en AWS: cambian el endpoint y las claves.

Las zonas no son carpetas. En S3 las claves son planas y la barra es una convención, así que
`raw/crimes/dia=2026-10-03/crimes.csv` es una clave entera y la zona es su prefijo. Por eso se
puede listar por zona sin que exista ningún directorio.
"""

import os
import socket
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
SECRET_KEY = os.getenv("MINIO_SECRET_ACCESS_KEY", "minio123")
BUCKET = os.getenv("LAKE_BUCKET", "arrest-lake")

# raw guarda lo que llegó tal cual; curated, lo que ya está listo para entrenar; models, los
# artefactos versionados. El riesgo de un lake sin zonas es que nadie sepa qué dato es confiable.
ZONES = ("raw", "curated", "models")


def lake_available(endpoint: str = ENDPOINT) -> bool:
    """Dice si hay alguien escuchando en el lake, para saltear lo que lo necesita."""
    host, _, port = endpoint.removeprefix("http://").removeprefix("https://").partition(":")
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port or 80))) == 0


def client(endpoint: str = ENDPOINT) -> Any:
    """Cliente S3 apuntando al lake.

    `path` en el direccionamiento es lo que hace que funcione contra MinIO: el estilo por
    defecto arma el nombre del bucket como subdominio, y en local eso no resuelve.
    """
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def ensure_bucket(s3: Any, bucket: str = BUCKET) -> None:
    """Crea el bucket y sus zonas si no están. Correrlo de nuevo no cambia nada."""
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
    for zone in ZONES:
        s3.put_object(Bucket=bucket, Key=f"{zone}/.keep", Body=b"")


def put_bytes(s3: Any, key: str, data: bytes, bucket: str = BUCKET) -> str:
    """Sube un objeto y devuelve su URI, que es como lo nombra el resto de la plataforma."""
    s3.put_object(Bucket=bucket, Key=key, Body=data)
    return f"s3://{bucket}/{key}"


def get_bytes(s3: Any, key: str, bucket: str = BUCKET) -> bytes:
    """Baja un objeto completo a memoria."""
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def list_keys(s3: Any, prefix: str = "", bucket: str = BUCKET) -> list[str]:
    """Lista las claves que empiezan con el prefijo, que es como se recorre una zona."""
    paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    return [obj["Key"] for pagina in paginas for obj in pagina.get("Contents", [])]
