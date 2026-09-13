"""Mini-TP 2: esquema GraphQL con los metadatos del modelo."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from arrest_model.features import MODEL_FEATURES
from arrest_model.schemas import EXAMPLE_REPORT
from tp2_graphql.app import create_app
from tp2_graphql.client import run_client
from tp2_graphql.schema import schema

MODELO = "chicago-arrest-xgboost"


def consultar(query: str, bundle: dict[str, Any]) -> Any:
    """Corre la query contra el esquema, sin levantar servidor."""
    return schema.execute_sync(query, context_value={"bundle": bundle})


def test_query_returns_the_model_metadata(bundle: dict[str, Any]) -> None:
    result = consultar(f'{{ model(name: "{MODELO}") {{ name version framework }} }}', bundle)
    assert result.errors is None
    assert result.data["model"] == {
        "name": MODELO,
        "version": 1,
        "framework": "xgboost 3.4.1",
    }


def test_query_returns_only_the_requested_fields(bundle: dict[str, Any]) -> None:
    # La gracia de GraphQL: se pide una métrica y no llega el resto del payload.
    result = consultar(f'{{ model(name: "{MODELO}") {{ metrics {{ mcc }} }} }}', bundle)
    assert result.errors is None
    assert result.data == {"model": {"metrics": {"mcc": pytest.approx(0.5811, abs=1e-4)}}}


class DriverQueFalla:
    """Un driver de Neo4j que revienta al usarse, para probar qué pasa si la base no responde."""

    def session(self) -> Any:
        raise RuntimeError("Neo4j no responde")


def test_lineage_is_null_when_neo4j_fails(bundle: dict[str, Any]) -> None:
    # El linaje se cae, pero el resto de la respuesta tiene que llegar igual.
    result = schema.execute_sync(
        f'{{ model(name: "{MODELO}") {{ name lineage {{ name kind }} }} }}',
        context_value={"bundle": bundle, "driver": DriverQueFalla()},
    )
    assert result.errors is not None
    assert result.data["model"]["name"] == MODELO
    assert result.data["model"]["lineage"] is None


def test_lineage_is_not_queried_when_not_asked(bundle: dict[str, Any]) -> None:
    # Con un driver que revienta, pedir solo las métricas no puede fallar: GraphQL resuelve
    # únicamente los campos pedidos, y ese es el punto de la comparación con REST.
    result = schema.execute_sync(
        f'{{ model(name: "{MODELO}") {{ metrics {{ mcc }} }} }}',
        context_value={"bundle": bundle, "driver": DriverQueFalla()},
    )
    assert result.errors is None
    assert result.data["model"]["metrics"]["mcc"] == pytest.approx(0.5811, abs=1e-4)


def test_unknown_model_is_null(bundle: dict[str, Any]) -> None:
    result = consultar('{ model(name: "otro-modelo") { name } }', bundle)
    assert result.errors is None
    assert result.data == {"model": None}


def test_the_app_answers_a_query_over_http(bundle: dict[str, Any]) -> None:
    with TestClient(create_app(lambda: bundle)) as client:
        response = client.post(
            "/graphql", json={"query": f'{{ model(name: "{MODELO}") {{ name version }} }}'}
        )
    assert response.status_code == 200
    assert response.json()["data"]["model"] == {"name": MODELO, "version": 1}


def test_the_app_serves_graphiql(bundle: dict[str, Any]) -> None:
    # La consigna pide probarlo desde GraphiQL, así que la interfaz tiene que estar servida.
    with TestClient(create_app(lambda: bundle)) as client:
        response = client.get("/graphql", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "graphiql" in response.text.lower()


def test_client_runs_every_case_without_failures(
    bundle: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    # El cliente recibe la sesión, así que el flujo entero se prueba sin levantar un servidor.
    with TestClient(create_app(lambda: bundle)) as client:
        assert run_client("/graphql", session=client, timeout=None) == 0
    assert "[FALLA]" not in capsys.readouterr().out


def test_inputs_and_features_describe_the_real_model(bundle: dict[str, Any]) -> None:
    # Lo que declara el esquema tiene que ser lo que de verdad consume el modelo.
    result = consultar(f'{{ model(name: "{MODELO}") {{ inputs features }} }}', bundle)
    assert result.errors is None
    assert result.data["model"]["inputs"] == list(EXAMPLE_REPORT)
    assert result.data["model"]["features"] == MODEL_FEATURES
