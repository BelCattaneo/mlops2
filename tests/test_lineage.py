"""Mini-TP 2: el linaje del modelo, sembrado en Neo4j.

Estos tests necesitan un Neo4j corriendo (`make neo4j-up`). Si no hay nada escuchando en el
puerto bolt, se saltean solos: el resto de la suite tiene que poder correr sin Docker.
"""

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from tp2_graphql.lineage import MODEL_NAME, lineage_of, open_driver, seed


def _neo4j_escuchando() -> bool:
    """Dice si hay algo aceptando conexiones en el puerto bolt."""
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", 7687)) == 0


pytestmark = [
    pytest.mark.neo4j,
    pytest.mark.skipif(not _neo4j_escuchando(), reason="no hay Neo4j escuchando en 7687"),
]


@pytest.fixture(scope="module")
def driver() -> Iterator[Any]:
    """Un driver de Neo4j para todo el módulo, con el grafo ya sembrado."""
    conexion = open_driver()
    seed(conexion)
    yield conexion
    conexion.close()


def test_seed_is_idempotent(driver: Any) -> None:
    # Sembrar dos veces no puede duplicar nodos ni aristas: usa MERGE, no CREATE.
    antes = lineage_of(driver, MODEL_NAME)
    seed(driver)
    assert lineage_of(driver, MODEL_NAME) == antes


def test_lineage_reaches_the_raw_datasets(driver: Any) -> None:
    nombres = {artefacto["name"] for artefacto in lineage_of(driver, MODEL_NAME)}
    assert "Crimes_Chicago_2024.csv" in nombres
    assert "Police_Stations_20251005.csv" in nombres


def test_lineage_includes_the_transforms(driver: Any) -> None:
    tipos = {artefacto["kind"] for artefacto in lineage_of(driver, MODEL_NAME)}
    assert tipos == {"Dataset", "Transform"}


def test_lineage_of_an_unknown_model_is_empty(driver: Any) -> None:
    assert lineage_of(driver, "otro-modelo") == []
