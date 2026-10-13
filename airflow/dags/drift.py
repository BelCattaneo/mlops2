"""Cuánto se movieron los datos respecto de los que vio el champion.

Se mide comparando los parámetros de preprocesamiento de la partición nueva contra los del
modelo que está servido, sin volver a bajar un solo dato: esos parámetros SON un resumen de la
distribución —la media y el desvío de cada numérica, la frecuencia de cada categoría— y es lo
que el modelo realmente consume.

Las features estandarizadas valen 0 y 1 en entrenamiento por construcción, así que el
corrimiento de la media medido en desvíos del champion dice directamente a cuántos desvíos de
lo que el modelo vio están llegando los datos nuevos. Ese número ya tiene una referencia
medida en este proyecto: el bug del CRS, donde una feature llegaba a 1,69 desvíos, costaba
0,07 de MCC por el camino de servicio.

Se calcula por lote y no por request a propósito: a 633 reportes por día una ventana deslizante
de predicciones tarda más de dos minutos en juntar una muestra, y el pipeline es mensual.
"""

from typing import Any


def drift_metrics(champion: dict[str, Any] | None, nuevos: dict[str, Any]) -> dict[str, float]:
    """Las métricas de corrimiento entre los parámetros del champion y los de la partición nueva.

    Devuelve un diccionario vacío si todavía no hay champion: la primera corrida no tiene contra
    qué medirse, y eso no es un error.
    """
    if champion is None:
        return {}

    metricas: dict[str, float] = {}
    for clave, (media, desvio) in champion.get("scale", {}).items():
        if clave not in nuevos.get("scale", {}):
            continue
        media_nueva = nuevos["scale"][clave][0]
        # En desvíos del champion, que es la unidad en la que el modelo ve esa feature.
        metricas[f"drift_scale_{clave}"] = abs(media_nueva - media) / abs(desvio or 1.0)

    movimientos: list[float] = []
    nuevas_categorias = 0
    for columna, mapa in champion.get("freq", {}).items():
        mapa_nuevo = nuevos.get("freq", {}).get(columna, {})
        for categoria in set(mapa) | set(mapa_nuevo):
            movimientos.append(abs(mapa_nuevo.get(categoria, 0.0) - mapa.get(categoria, 0.0)))
        nuevas_categorias += len(set(mapa_nuevo) - set(mapa))

    metricas["drift_max_sigma"] = max(
        (v for k, v in metricas.items() if k.startswith("drift_scale_")), default=0.0
    )
    metricas["drift_freq_max"] = max(movimientos, default=0.0)
    metricas["drift_freq_new_categories"] = float(nuevas_categorias)
    return metricas
