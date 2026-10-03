"""Las particiones crudas que entran en la ventana de entrenamiento.

La ventana no se aplica filtrando filas sino eligiendo qué particiones se leen: la capa cruda
está partida por mes, así que leer los últimos doce meses es quedarse con esas claves. Filtrar
por fila además sería redundante, y haría que una corrida y la siguiente no fueran comparables
porque el corte se movería con el reloj.

Vive acá y no en el módulo del DAG porque así se puede probar sin Airflow instalado.
"""

import datetime
import re

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
