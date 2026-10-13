"""El grafo de linaje que el pipeline escribe mientras corre."""

from lineage_graph import (
    curated_statements,
    enriched_statements,
    model_statements,
    raw_statements,
    upstream_cypher,
)

MES = "raw/crimes/month=2026-03/crimes.csv"
INTERMEDIA = "enriched/crimes/date=2026-10-08/crimes.parquet"
CURADA = "curated/train/date=2026-10-08/train.parquet"


def claves_de(sentencias: list[tuple[str, dict]]) -> list[dict]:
    """Los parámetros de cada sentencia, que es lo que describe el grafo."""
    return [parametros for _, parametros in sentencias]


def test_every_statement_merges_so_repeating_a_run_does_not_duplicate() -> None:
    # El ETL es idempotente por partición: si una corrida se repite, el grafo tiene que quedar
    # igual y no con dos nodos por el mismo archivo.
    todas = (
        raw_statements([MES])
        + enriched_statements(INTERMEDIA, [MES])
        + curated_statements(CURADA, INTERMEDIA)
        + model_statements("chicago-arrest-xgboost", 9, CURADA)
    )

    assert all("MERGE" in cypher for cypher, _ in todas)
    assert not any("CREATE " in cypher for cypher, _ in todas)


def test_the_raw_partition_is_identified_by_its_key() -> None:
    assert claves_de(raw_statements([MES])) == [{"key": MES}]


def test_the_enriched_partition_points_back_to_every_month_it_read() -> None:
    # Es la arista que después permite preguntar al revés: de este mes, ¿qué salió?
    otro = "raw/crimes/month=2026-04/crimes.csv"

    sentencias = enriched_statements(INTERMEDIA, [MES, otro])

    origenes = [p["origen"] for p in claves_de(sentencias) if "origen" in p]
    assert sorted(origenes) == sorted([MES, otro])


def test_the_model_version_hangs_from_the_partition_it_trained_on() -> None:
    sentencias = model_statements("chicago-arrest-xgboost", 9, CURADA)

    parametros = claves_de(sentencias)[-1]
    assert parametros["version"] == 9
    assert parametros["origen"] == CURADA


def test_the_upstream_query_walks_an_unknown_number_of_hops() -> None:
    # Es lo que justifica el grafo: la cadena tiene cuatro saltos hoy y podría tener otros
    # mañana, y la consulta no cambia.
    assert "*1.." in upstream_cypher()
