"""Las particiones crudas que entran en la ventana de entrenamiento.

La ventana no se aplica filtrando filas sino eligiendo qué particiones se leen: la capa cruda
está partida por mes, así que leer los últimos doce meses es quedarse con esas claves. Filtrar
por fila además sería redundante, y haría que una corrida y la siguiente no fueran comparables
porque el corte se movería con el reloj.

Vive acá y no en el módulo del DAG porque así se puede probar sin Airflow instalado.
"""

import datetime
import re

import pandas as pd

PARTICION = re.compile(r"month=(\d{4})-(\d{2})")


def partitions_in_window(keys: list[str], end: datetime.datetime, days: int) -> list[str]:
    """Las claves cuya partición mensual cae en los `days` días previos a `end`, ordenadas.

    Se compara por mes, no por día: una partición entra si su mes es posterior o igual al mes
    en el que arranca la ventana. Las claves sin partición mensual se ignoran.
    """
    desde = end - datetime.timedelta(days=days)
    minimo = (desde.year, desde.month)
    elegidas = []
    for clave in keys:
        encontrado = PARTICION.search(clave)
        if encontrado and (int(encontrado.group(1)), int(encontrado.group(2))) >= minimo:
            elegidas.append(clave)
    return sorted(elegidas)


def download_window(
    interval_start: datetime.datetime | None,
    interval_end: datetime.datetime | None,
    now: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    """La ventana de la corrida: su intervalo de datos, o el mes corriente si no tiene.

    En Airflow 3 un trigger manual sin fecha lógica deja el intervalo en `None`, y el botón
    "Trigger DAG" de la interfaz dispara así: sin reemplazo, la tarea de descarga se cae con
    `AttributeError` al armar la partición, o sea que el DAG solo se podría correr programado,
    que es justo lo que un corrector no va a hacer.

    Y con fecha lógica lo deja como un punto, inicio igual a fin. Tomado literal eso da un
    período vacío: la descarga trae cero filas y la corrida reporta éxito sin escribir nada.
    Los dos casos caen al reemplazo.
    """
    completo = interval_start is not None and interval_end is not None
    if completo and interval_start < interval_end:
        return interval_start, interval_end
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now


def partition_date(ds: str | None, window_end: datetime.datetime) -> str:
    """El sufijo de las claves derivadas: la fecha lógica, o el fin de la ventana si no hay.

    Sin fecha lógica Airflow no provee `ds`, así que el sufijo sale de la ventana ya resuelta.
    Resolverlo una sola vez y hacerlo viajar por XCom es lo que evita que dos capas de la misma
    corrida escriban en particiones distintas.
    """
    return ds or window_end.date().isoformat()


def newest_partition(objects: list[tuple[str, float]]) -> str | None:
    """La partición escrita más recientemente, de una lista de (clave, marca de tiempo).

    No es la de fecha mayor. La partición lleva la fecha lógica de la corrida, que puede ir
    hacia atrás si se reprocesa un período viejo, así que ordenar por nombre elige el dataset
    equivocado. Lo que define cuál es la última es cuándo se escribió.
    """
    candidatas = [
        (marca, encontrada.group(0).removeprefix("date="))
        for clave, marca in objects
        if (encontrada := re.search(r"date=\d{4}-\d{2}-\d{2}", clave))
    ]
    return max(candidatas)[1] if candidatas else None


def split_by_month(reports: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Reparte los reportes en grupos por el mes de su propia fecha.

    La carga inicial baja un año de una vez, y escribirlo todo en la partición del mes corriente
    haría que la partición mienta sobre qué contiene: la ventana se determina por qué
    particiones se leen, así que una que abarca doce meses rompe el recorte.

    Falla si alguna fila no tiene fecha, porque la capa cruda es lo que llegó: una fila que
    desaparece acá no se recupera de ningún lado.
    """
    fechas = pd.to_datetime(reports["date"], errors="coerce")
    sin_fecha = int(fechas.isna().sum())
    if sin_fecha:
        raise ValueError(f"{sin_fecha} reportes sin fecha: no se pueden particionar")
    meses = fechas.dt.strftime("%Y-%m")
    return {mes: reports[meses == mes].copy() for mes in sorted(meses.unique())}
