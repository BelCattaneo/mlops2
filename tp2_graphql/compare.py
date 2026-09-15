"""Compara la misma lectura servida por REST y por GraphQL.

La vista que se arma es chica a propósito: el nombre del modelo y una sola métrica, el MCC.

Por REST hay que pedir `/v1/metadata`, que devuelve el paquete entero —versión, framework, los
6 campos de entrada, las 7 features, las 6 métricas y la fecha— cuando solo se querían dos
campos. Eso es over-fetching, y se mide en bytes.

Por GraphQL se pide exactamente esos dos campos y no llega nada más.

Queda afuera de la medición, pero es parte de la comparación: el linaje del modelo no lo expone
ningún endpoint REST, así que para sumarlo a la vista habría que agregar uno. En GraphQL es un
campo más en la misma query.

Uso: `uv run python -m tp2_graphql.compare [--rest-url ...] [--graphql-url ...]`
"""

import argparse
from typing import Any

import requests

from arrest_model.config import MODEL_NAME
from tp2_graphql.client import post_graphql

VISTA = "nombre del modelo y su MCC"
QUERY = f'{{ model(name: "{MODEL_NAME}") {{ name metrics {{ mcc }} }} }}'


class GraphQLFailed(RuntimeError):
    """La consulta volvió con errores, que es como GraphQL avisa que falló: en el cuerpo y con
    status 200. Es una excepción propia para que la línea de comandos la trate como cualquier
    otra falla de la llamada y muestre un mensaje en vez de un traceback."""


class CountingSession:
    """Envuelve una sesión HTTP y cuenta las requests que salen por ella."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Hace el GET con la sesión envuelta y lo cuenta."""
        self.calls += 1
        return self.session.get(*args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        """Hace el POST con la sesión envuelta y lo cuenta."""
        self.calls += 1
        return self.session.post(*args, **kwargs)


def model_from_response(body: dict[str, Any]) -> dict[str, Any]:
    """Saca el modelo del cuerpo de la respuesta, o falla diciendo qué contestó la API.

    Un error de GraphQL viaja con status 200, así que no lo ve `raise_for_status`: hay que
    mirar el cuerpo, donde además `data` puede llegar en null.
    """
    if body.get("errors"):
        raise GraphQLFailed("; ".join(error.get("message", "") for error in body["errors"]))
    modelo = (body.get("data") or {}).get("model")
    if modelo is None:
        raise GraphQLFailed(f"la API no devolvió ningún modelo llamado {MODEL_NAME}")
    return modelo


def compare(
    rest_url: str,
    graphql_url: str,
    rest_session: Any = requests,
    graphql_session: Any = requests,
    timeout: float | None = 10,
) -> dict[str, Any]:
    """Arma la misma vista por los dos protocolos y devuelve qué costó cada uno.

    Las sesiones entran por parámetro para poder medir contra las dos apps sin levantarlas. Las
    llamadas se cuentan sobre la sesión: si la vista pasara a necesitar otra request, la tabla lo
    reflejaría sin tocar este diccionario.
    """
    opciones = {"timeout": timeout} if timeout is not None else {}
    rest_calls, graphql_calls = CountingSession(rest_session), CountingSession(graphql_session)

    rest = rest_calls.get(f"{rest_url}/v1/metadata", **opciones)
    rest.raise_for_status()
    metadata = rest.json()

    graphql = post_graphql(graphql_calls, graphql_url, QUERY, timeout)
    modelo = model_from_response(graphql.json())

    return {
        "vista": {
            "rest": {"name": metadata["name"], "mcc": metadata["metrics"]["mcc"]},
            "graphql": {"name": modelo["name"], "mcc": modelo["metrics"]["mcc"]},
        },
        "rest": {"llamadas": rest_calls.calls, "bytes": len(rest.content)},
        "graphql": {"llamadas": graphql_calls.calls, "bytes": len(graphql.content)},
    }


def format_results(numeros: dict[str, Any]) -> str:
    """Arma la tabla en markdown, lista para pegar en el README o el notebook."""
    rest, graphql = numeros["rest"], numeros["graphql"]
    lineas = [
        f"Vista: {VISTA}.",
        "",
        "| protocolo | llamadas | bytes recibidos |",
        "|---|---|---|",
        f"| REST | {rest['llamadas']} | {rest['bytes']} |",
        f"| GraphQL | {graphql['llamadas']} | {graphql['bytes']} |",
        "",
        f"Las dos vistas coinciden: {numeros['vista']['rest'] == numeros['vista']['graphql']}.",
        "El linaje del modelo no lo expone ningún endpoint REST; en GraphQL es un campo más.",
    ]
    return "\n".join(lineas)


def main() -> int:
    """Punto de entrada: corre la comparación e imprime la tabla."""
    parser = argparse.ArgumentParser(description="La misma lectura por REST y por GraphQL")
    parser.add_argument("--rest-url", default="http://127.0.0.1:8000")
    parser.add_argument("--graphql-url", default="http://127.0.0.1:8010/graphql")
    args = parser.parse_args()
    try:
        numeros = compare(args.rest_url, args.graphql_url)
    except (requests.RequestException, GraphQLFailed) as exc:
        print(f"No se pudo comparar ({type(exc).__name__}): {exc}")
        print("Tienen que estar las dos APIs arriba: `make rest-run` y `make graphql-run`.")
        return 1
    print(format_results(numeros))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
