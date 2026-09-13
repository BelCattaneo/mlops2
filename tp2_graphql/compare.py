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

MODELO = "chicago-arrest-xgboost"
VISTA = "nombre del modelo y su MCC"
QUERY = f'{{ model(name: "{MODELO}") {{ name metrics {{ mcc }} }} }}'


def compare(
    rest_url: str,
    graphql_url: str,
    rest_session: Any = requests,
    graphql_session: Any = requests,
    timeout: float | None = 10,
) -> dict[str, Any]:
    """Arma la misma vista por los dos protocolos y devuelve qué costó cada uno.

    Las sesiones entran por parámetro para poder medir contra las dos apps sin levantarlas.
    """
    opciones = {"timeout": timeout} if timeout is not None else {}

    rest = rest_session.get(f"{rest_url}/v1/metadata", **opciones)
    rest.raise_for_status()
    metadata = rest.json()

    graphql = graphql_session.post(graphql_url, json={"query": QUERY}, **opciones)
    graphql.raise_for_status()
    modelo = graphql.json()["data"]["model"]

    return {
        "vista": {
            "rest": {"name": metadata["name"], "mcc": metadata["metrics"]["mcc"]},
            "graphql": {"name": modelo["name"], "mcc": modelo["metrics"]["mcc"]},
        },
        "rest": {"llamadas": 1, "bytes": len(rest.content)},
        "graphql": {"llamadas": 1, "bytes": len(graphql.content)},
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
    except requests.RequestException as exc:
        print(f"No se pudo comparar ({type(exc).__name__}): {exc}")
        print("Tienen que estar las dos APIs arriba: `make rest-run` y `make graphql-run`.")
        return 1
    print(format_results(numeros))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
