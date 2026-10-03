"""Mini-TP 6: traer los datos crudos al lake.

La zona `raw` guarda lo que llegó tal cual, sin limpiar. Esa es la diferencia con un warehouse:
si mañana cambia el preprocesamiento, se puede reprocesar desde el crudo en vez de volver a
pedirle los datos a la fuente, que puede no tenerlos más.

Son dos fuentes con cadencias muy distintas. Los reportes de crímenes se actualizan a diario y
se particionan por día. Las comisarías son 23 filas que no cambian desde 2016, así que se
reemplazan enteras y sin partición.

Si el portal no responde —sin red, sin token o con el límite de uso agotado— se usa una copia
versionada en el repo. Es a propósito: un pipeline que solo funciona con internet no se puede
corregir en la máquina de otro.
"""

import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arrest_model.log import service_logger
from tp6_datalake.lake import BUCKET, put_bytes

logger = service_logger("tp6_datalake")

DOMAIN = "https://data.cityofchicago.org/resource"
CRIMES = "ijzp-q8t2"
STATIONS = "z8bn-74gv"
ROWS = 2000

SNAPSHOT_CRIMES = Path(__file__).resolve().parent / "data" / "crimes_sample.csv.gz"
SNAPSHOT_STATIONS = Path(__file__).resolve().parent / "data" / "police_stations.csv"


def fetch_csv(dataset: str, rows: int = ROWS, timeout: float = 30, **params: str) -> bytes:
    """Pide un dataset del portal en CSV.

    El token va si está definido: sin él la consulta igual funciona, pero el portal agrupa el
    límite de uso por dirección IP y corta antes.
    """
    # Los valores van codificados: un "$order=date DESC" sin escapar rompe la URL por el espacio.
    partes = {"$limit": str(rows), **{f"${clave}": valor for clave, valor in params.items()}}
    consulta = urllib.parse.urlencode(partes)
    pedido = urllib.request.Request(f"{DOMAIN}/{dataset}.csv?{consulta}")
    token = os.getenv("SOCRATA_APP_TOKEN")
    if token:
        pedido.add_header("X-App-Token", token)
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:  # noqa: S310
        return respuesta.read()


def land_raw(
    s3: Any,
    bucket: str = BUCKET,
    day: str = "",
    download: Callable[..., bytes] = fetch_csv,
) -> dict[str, str]:
    """Deja en `raw` los reportes del día y las comisarías; devuelve qué subió y de dónde salió."""
    try:
        reportes = download(CRIMES, order="date DESC")
        comisarias = download(STATIONS)
        origen = "socrata"
    except Exception:
        # Se avisa con la traza: un respaldo silencioso esconde que la fuente dejó de responder.
        logger.exception("No se pudo bajar de Socrata; se usa la copia versionada del repo")
        reportes = SNAPSHOT_CRIMES.read_bytes()
        comisarias = SNAPSHOT_STATIONS.read_bytes()
        origen = "respaldo"
    return {
        "crimes": put_bytes(s3, f"raw/crimes/dia={day}/crimes.csv", reportes, bucket),
        "stations": put_bytes(s3, "raw/police_stations/police_stations.csv", comisarias, bucket),
        "origen": origen,
    }
