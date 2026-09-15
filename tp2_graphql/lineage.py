"""Mini-TP 2: el linaje del modelo, guardado como grafo en Neo4j.

El linaje es la trazabilidad del modelo: de qué archivos crudos salió, por qué transformaciones
pasó y qué datasets intermedios dejó en el camino. Se guarda como grafo porque la pregunta que
interesa —qué hay aguas arriba de este modelo— tiene largo variable, y eso en un grafo es un
recorrido y en SQL una cadena de JOINs que no se sabe de antemano cuántos son.

La cadena está verificada contra los archivos del TP-final y contra lo que lee el script de
entrenamiento, que toma cuatro datasets: los dos finales para entrenar y validar, y además el
procesado y el de comisarías para reconstruir el split y calcular los parámetros de codificación.

Se siembra con `make graphql-seed`, con Neo4j levantado (`make neo4j-up`).
"""

import os
import time
from typing import Any

from neo4j import Driver, GraphDatabase

from arrest_model.config import MODEL_NAME

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "testpass"))

PREFIX = "chicago_crimes_and_stations_2024"

# Cada nodo con su tipo. Los nombres de los datasets son los archivos reales del TP-final.
NODES: dict[str, str] = {
    "Crimes_Chicago_2024.csv": "Dataset",
    "Police_Stations_20251005.csv": "Dataset",
    f"{PREFIX}_processed.csv": "Dataset",
    f"{PREFIX}_processed_outliers_encoded.csv": "Dataset",
    f"{PREFIX}_processed_outliers_encoded_test.csv": "Dataset",
    f"{PREFIX}_processed_outliers_encoded_standardized.csv": "Dataset",
    f"{PREFIX}_processed_outliers_encoded_standardized_test.csv": "Dataset",
    f"{PREFIX}_processed_outliers_encoded_standardized_combined.csv": "Dataset",
    f"{PREFIX}_final.csv": "Dataset",
    f"{PREFIX}_final_test.csv": "Dataset",
    "1_Creacion_dataset": "Transform",
    "3_Outliers_Encoding": "Transform",
    "4_Escalado": "Transform",
    "5_Balanceo": "Transform",
    "6_Feature_Selection": "Transform",
    "entrenamiento": "Transform",
    MODEL_NAME: "Model",
}

# Aristas DERIVES, en la dirección en que fluyen los datos.
EDGES: list[tuple[str, str]] = [
    ("Crimes_Chicago_2024.csv", "1_Creacion_dataset"),
    ("Police_Stations_20251005.csv", "1_Creacion_dataset"),
    ("1_Creacion_dataset", f"{PREFIX}_processed.csv"),
    (f"{PREFIX}_processed.csv", "3_Outliers_Encoding"),
    ("3_Outliers_Encoding", f"{PREFIX}_processed_outliers_encoded.csv"),
    ("3_Outliers_Encoding", f"{PREFIX}_processed_outliers_encoded_test.csv"),
    (f"{PREFIX}_processed_outliers_encoded.csv", "4_Escalado"),
    (f"{PREFIX}_processed_outliers_encoded_test.csv", "4_Escalado"),
    ("4_Escalado", f"{PREFIX}_processed_outliers_encoded_standardized.csv"),
    ("4_Escalado", f"{PREFIX}_processed_outliers_encoded_standardized_test.csv"),
    (f"{PREFIX}_processed_outliers_encoded_standardized.csv", "5_Balanceo"),
    ("5_Balanceo", f"{PREFIX}_processed_outliers_encoded_standardized_combined.csv"),
    (f"{PREFIX}_processed_outliers_encoded_standardized_combined.csv", "6_Feature_Selection"),
    (f"{PREFIX}_processed_outliers_encoded_standardized_test.csv", "6_Feature_Selection"),
    ("6_Feature_Selection", f"{PREFIX}_final.csv"),
    ("6_Feature_Selection", f"{PREFIX}_final_test.csv"),
    # El entrenamiento lee los dos finales y, además, el procesado y el de comisarías.
    (f"{PREFIX}_final.csv", "entrenamiento"),
    (f"{PREFIX}_final_test.csv", "entrenamiento"),
    (f"{PREFIX}_processed.csv", "entrenamiento"),
    ("Police_Stations_20251005.csv", "entrenamiento"),
    ("entrenamiento", MODEL_NAME),
]

# El orden fija el resultado: Neo4j no garantiza uno, y sin esto comparar dos corridas sería
# intermitente.
LINEAGE_CYPHER = """
MATCH (a)-[:DERIVES*1..]->(m:Model {name: $name})
RETURN DISTINCT a.name AS name, head(labels(a)) AS kind
ORDER BY kind, name
"""


def connect(uri: str = URI, auth: tuple[str, str] = AUTH, timeout: float = 5) -> Driver:
    """Crea el driver sin verificar la conexión.

    El driver es perezoso: no se conecta hasta la primera consulta. Gracias a eso el servicio
    GraphQL arranca aunque Neo4j esté caído, y el problema aparece solo al pedir el linaje.

    Los timeouts van explícitos porque los que trae el driver son de decenas de segundos: una
    base que acepta la conexión pero no responde tendría al servicio esperando todo ese rato.
    """
    return GraphDatabase.driver(
        uri,
        auth=auth,
        connection_timeout=timeout,
        connection_acquisition_timeout=timeout,
        max_transaction_retry_time=timeout,
    )


def open_driver(uri: str = URI, auth: tuple[str, str] = AUTH, wait: float = 60) -> Driver:
    """Abre el driver y espera hasta `wait` segundos a que Neo4j acepte conexiones.

    El contenedor tarda en arrancar, así que sin la espera un `seed` lanzado justo después de
    levantarlo fallaría por una carrera y no por un problema real.
    """
    driver = GraphDatabase.driver(uri, auth=auth)
    limite = time.monotonic() + wait
    while True:
        try:
            driver.verify_connectivity()
            return driver
        except Exception:
            if time.monotonic() >= limite:
                driver.close()
                raise
            time.sleep(1)


def seed(driver: Driver) -> None:
    """Siembra la cadena de linaje. Es idempotente: correrlo de nuevo no duplica nada.

    Usa MERGE y no CREATE, y a propósito no borra la base: el ejemplo de la cátedra arranca su
    sembrado con un DETACH DELETE de todo, que se llevaría por delante cualquier otro grafo.
    """
    # La etiqueta no se puede parametrizar en Cypher; sale de NODES, que es constante del módulo.
    plantilla = (
        "MERGE (a:{origen} {{name: $a}}) MERGE (b:{destino} {{name: $b}}) MERGE (a)-[:DERIVES]->(b)"
    )
    with driver.session() as session:
        for origen, destino in EDGES:
            consulta = plantilla.format(origen=NODES[origen], destino=NODES[destino])
            session.run(consulta, a=origen, b=destino)


def lineage_of(driver: Driver, name: str) -> list[dict[str, Any]]:
    """Devuelve todo lo que está aguas arriba del modelo, sin importar a cuántos saltos."""
    with driver.session() as session:
        return [dict(registro) for registro in session.run(LINEAGE_CYPHER, name=name)]


def main() -> int:
    """Siembra el grafo: `uv run python -m tp2_graphql.lineage`."""
    driver = open_driver()
    try:
        seed(driver)
        artefactos = lineage_of(driver, MODEL_NAME)
        print(f"Linaje sembrado: {len(artefactos)} artefactos aguas arriba de {MODEL_NAME}.")
        for artefacto in artefactos:
            print(f"  {artefacto['kind']:10} {artefacto['name']}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
