"""El grafo de linaje que el pipeline escribe mientras corre.

Los nodos son **instancias**, no etapas: esta partición cruda, esta curada, esta versión del
modelo. Un grafo de etapas sería una segunda copia del diagrama de arquitectura, guardada en una
base de datos y desincronizándose; con instancias hay cientos de nodos y las consultas sirven.

Lo que contesta y MLflow no es la pregunta inversa. MLflow registra de qué partición curada salió
cada versión, así que "¿de dónde salió este modelo?" ya tiene respuesta. Pero "este mes del
portal vino mal, ¿qué versiones hay que revisar?" es un recorrido hacia adelante de profundidad
desconocida, y eso es exactamente lo que un grafo hace bien.

Todo se escribe con `MERGE`: el ETL es idempotente por partición y repetir una corrida tiene que
dejar el grafo igual, no con dos nodos por el mismo archivo.

Y se escribe best-effort. Si Neo4j no responde, las tareas siguen: el linaje es trazabilidad, no
una dependencia del pipeline de datos. Lo que no puede pasar es que el hueco quede en silencio,
así que quien escribe informa si pudo y el resumen de la corrida lo registra.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "testpass"))

Sentencia = tuple[str, dict[str, Any]]


def raw_statements(keys: list[str]) -> list[Sentencia]:
    """Un nodo por partición cruda aterrizada."""
    return [("MERGE (:RawPartition {key: $key})", {"key": clave}) for clave in keys]


def enriched_statements(key: str, raw_keys: list[str]) -> list[Sentencia]:
    """La partición intermedia y las aristas desde cada mes crudo que la produjo."""
    sentencias: list[Sentencia] = [
        ("MERGE (:EnrichedPartition {key: $key})", {"key": key}),
    ]
    sentencias += [
        (
            """
            MERGE (o:RawPartition {key: $origen})
            MERGE (d:EnrichedPartition {key: $destino})
            MERGE (o)-[:DERIVES]->(d)
            """,
            {"origen": origen, "destino": key},
        )
        for origen in raw_keys
    ]
    return sentencias


def curated_statements(key: str, enriched_key: str) -> list[Sentencia]:
    """La partición curada y la arista desde la intermedia de la que salió."""
    return [
        (
            """
            MERGE (o:EnrichedPartition {key: $origen})
            MERGE (d:CuratedPartition {key: $destino})
            MERGE (o)-[:DERIVES]->(d)
            """,
            {"origen": enriched_key, "destino": key},
        )
    ]


def model_statements(name: str, version: int, curated_key: str) -> list[Sentencia]:
    """La versión registrada y la arista desde la partición curada con la que se entrenó."""
    return [
        (
            """
            MERGE (o:CuratedPartition {key: $origen})
            MERGE (d:ModelVersion {name: $name, version: $version})
            MERGE (o)-[:DERIVES]->(d)
            """,
            {"origen": curated_key, "name": name, "version": version},
        )
    ]


def upstream_cypher() -> str:
    """Todo lo que está aguas arriba de una versión, a cualquier cantidad de saltos."""
    return """
    MATCH (a)-[:DERIVES*1..]->(m:ModelVersion {name: $name, version: $version})
    RETURN DISTINCT a.key AS key, head(labels(a)) AS kind
    ORDER BY kind, key
    """


def downstream_cypher() -> str:
    """Qué versiones del modelo salieron, a cualquier cantidad de saltos, de una partición.

    Es la pregunta que MLflow no contesta: si un mes del portal vino mal, cuáles hay que revisar.
    """
    return """
    MATCH (o {key: $key})-[:DERIVES*1..]->(m:ModelVersion)
    RETURN DISTINCT m.name AS name, m.version AS version
    ORDER BY version
    """


def record(statements: list[Sentencia], uri: str = URI, auth: tuple[str, str] = AUTH) -> bool:
    """Escribe las sentencias y dice si pudo. Nunca levanta: el linaje no frena el pipeline."""
    try:
        from neo4j import GraphDatabase

        with (
            GraphDatabase.driver(
                uri, auth=auth, connection_timeout=5, connection_acquisition_timeout=5
            ) as driver,
            driver.session() as session,
        ):
            for cypher, parametros in statements:
                session.run(cypher, **parametros)
    except Exception:
        logger.warning("No se pudo escribir el linaje en %s; la corrida sigue", uri, exc_info=True)
        return False
    return True
