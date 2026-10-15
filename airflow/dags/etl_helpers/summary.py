"""El resumen de una corrida del ETL, armado con lo que reporta cada capa.

Los conteos viajan en el XCom de su capa en vez de volver a bajar los datasets para contarlos:
la capa que leyó las filas es la que sabe cuántas eran. Cuando una capa vuelve temprano porque
lo que produce ya estaba, su XCom no trae conteos, y entonces no hay corrida que resumir.

Vive acá y no en el módulo del DAG porque así se puede probar sin Airflow instalado.
"""

from typing import Any

CONTEOS = (
    "raw_count",
    "enriched_count",
    "train_count",
    "test_count",
    "final_train_count",
    "final_test_count",
    "feature_count",
)


def wrote_new_partition(curated: dict[str, Any]) -> bool:
    """Si la corrida escribió una partición curada nueva. Falso si volvió temprano.

    Es la misma señal que mira el resumen: la capa que escribió algo reporta sus conteos y la
    que volvió temprano no los trae. De esto depende que la corrida publique la capa, que es lo
    que dispara el entrenamiento: sin partición nueva no hay nada que entrenar.
    """
    return "rows" in curated


def summary_counts(
    raw: dict[str, Any], enriched: dict[str, Any], curated: dict[str, Any]
) -> dict[str, int] | None:
    """Los conteos de la corrida, o None si no hubo nada que procesar.

    El conteo de la capa cruda lo pone la descarga si bajó algo, y si volvió temprano lo pone
    la capa intermedia, que es la que leyó las particiones.
    """
    try:
        train_final, test_final = curated["rows"]
        corte_train, corte_test = curated["split_rows"]
        conteos = {
            "raw_count": raw.get("rows") or enriched["raw_rows"],
            "enriched_count": enriched["rows"],
            "train_count": corte_train,
            "test_count": corte_test,
            "final_train_count": train_final,
            "final_test_count": test_final,
            "feature_count": curated["features"],
        }
    except KeyError:
        return None
    return conteos if all(conteos[clave] is not None for clave in CONTEOS) else None
