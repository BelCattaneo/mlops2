"""Mini-TP 2: esquema GraphQL con los metadatos del modelo."""

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from arrest_model.features import MODEL_FEATURES
from arrest_model.schemas import EXAMPLE_REPORT
from tp1_rest.app import create_app as create_rest_app
from tp2_graphql.app import create_app
from tp2_graphql.client import run_client
from tp2_graphql.compare import GraphQLFailed, compare
from tp2_graphql.compare import main as compare_main
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


def test_lineage_is_null_when_neo4j_fails(
    bundle: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # El linaje se cae, pero el resto de la respuesta tiene que llegar igual. Va por la app
    # porque el resolver es asíncrono y `execute_sync` no puede ejecutarlo.
    monkeypatch.setattr("tp2_graphql.app.connect", lambda: DriverQueFalla())
    with TestClient(create_app(lambda: bundle)) as client:
        cuerpo = client.post(
            "/graphql",
            json={"query": f'{{ model(name: "{MODELO}") {{ name lineage {{ name kind }} }} }}'},
        ).json()
    assert cuerpo["errors"]
    assert cuerpo["data"]["model"]["name"] == MODELO
    assert cuerpo["data"]["model"]["lineage"] is None


def test_lineage_does_not_run_on_the_event_loop(
    bundle: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # El resolver hace I/O de red contra Neo4j. Si corre en el hilo del event loop, una consulta
    # lenta deja sin atender al resto del servicio, incluidas las requests que no tocan Neo4j.
    visto: dict[str, bool] = {}

    def espia(driver: Any, name: str) -> list[dict[str, Any]]:
        try:
            asyncio.get_running_loop()
            visto["en_el_loop"] = True
        except RuntimeError:
            visto["en_el_loop"] = False
        return []

    monkeypatch.setattr("tp2_graphql.schema.lineage_of", espia)
    with TestClient(create_app(lambda: bundle)) as client:
        respuesta = client.post(
            "/graphql", json={"query": f'{{ model(name: "{MODELO}") {{ lineage {{ name }} }} }}'}
        )
    assert respuesta.status_code == 200
    assert visto["en_el_loop"] is False


def test_lineage_is_not_queried_when_not_asked(bundle: dict[str, Any]) -> None:
    # Con un driver que revienta, pedir solo las métricas no puede fallar: GraphQL resuelve
    # únicamente los campos pedidos, y ese es el punto de la comparación con REST.
    result = schema.execute_sync(
        f'{{ model(name: "{MODELO}") {{ metrics {{ mcc }} }} }}',
        context_value={"bundle": bundle, "driver": DriverQueFalla()},
    )
    assert result.errors is None
    assert result.data["model"]["metrics"]["mcc"] == pytest.approx(0.5811, abs=1e-4)


def test_an_extra_metric_does_not_break_the_query(bundle: dict[str, Any]) -> None:
    # Un reentrenamiento puede sumar una métrica al bundle. Eso no puede anular el modelo
    # entero ni, mucho menos, devolverle al cliente el mensaje interno de Python.
    metricas = {**bundle["metadata"]["metrics"], "brier": 0.1}
    raro = {**bundle, "metadata": {**bundle["metadata"], "metrics": metricas}}
    result = consultar(f'{{ model(name: "{MODELO}") {{ name metrics {{ mcc }} }} }}', raro)
    assert result.errors is None
    assert result.data["model"]["name"] == MODELO
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


def test_both_protocols_build_the_same_view(bundle: dict[str, Any]) -> None:
    with (
        TestClient(create_rest_app(lambda: bundle)) as rest,
        TestClient(create_app(lambda: bundle)) as graphql,
    ):
        numeros = compare("", "/graphql", rest_session=rest, graphql_session=graphql, timeout=None)
    assert numeros["vista"]["rest"] == numeros["vista"]["graphql"]
    assert numeros["vista"]["graphql"]["name"] == MODELO


def test_graphql_moves_fewer_bytes_for_the_same_view(bundle: dict[str, Any]) -> None:
    # REST manda el payload entero cuando se querían dos campos; eso es el over-fetching.
    with (
        TestClient(create_rest_app(lambda: bundle)) as rest,
        TestClient(create_app(lambda: bundle)) as graphql,
    ):
        numeros = compare("", "/graphql", rest_session=rest, graphql_session=graphql, timeout=None)
    assert numeros["graphql"]["bytes"] < numeros["rest"]["bytes"]


class RespuestaConErrores:
    """Una consulta GraphQL que falló: status 200, `errors` en el cuerpo y `data` en null."""

    content = b'{"errors": [{"message": "algo se rompio"}], "data": null}'

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return json.loads(self.content)


class SesionConErrores:
    """Una sesión cuyas consultas siempre vuelven con errores."""

    def post(self, *args: Any, **kwargs: Any) -> RespuestaConErrores:
        return RespuestaConErrores()


def test_compare_reports_a_graphql_error_instead_of_crashing(bundle: dict[str, Any]) -> None:
    # El error de GraphQL viaja con status 200, así que `raise_for_status` no lo ve y `data`
    # llega en null. Sin un chequeo explícito esto reventaba con un TypeError.
    with TestClient(create_rest_app(lambda: bundle)) as rest:
        with pytest.raises(GraphQLFailed):
            compare(
                "", "/graphql", rest_session=rest, graphql_session=SesionConErrores(), timeout=None
            )


def test_the_command_line_explains_the_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Lo que ve quien lo corre desde la terminal: un mensaje, no un traceback.
    def explota(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise GraphQLFailed("algo se rompio")

    monkeypatch.setattr("tp2_graphql.compare.compare", explota)
    monkeypatch.setattr("sys.argv", ["compare"])
    assert compare_main() == 1
    assert "algo se rompio" in capsys.readouterr().out


def test_inputs_and_features_describe_the_real_model(bundle: dict[str, Any]) -> None:
    # Lo que declara el esquema tiene que ser lo que de verdad consume el modelo.
    result = consultar(f'{{ model(name: "{MODELO}") {{ inputs features }} }}', bundle)
    assert result.errors is None
    assert result.data["model"]["inputs"] == list(EXAMPLE_REPORT)
    assert result.data["model"]["features"] == MODEL_FEATURES
