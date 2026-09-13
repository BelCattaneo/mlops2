"""Cliente de prueba del Mini-TP 2: consulta la API GraphQL y muestra cada respuesta.

En GraphQL una consulta que falla igual responde 200, con una clave `errors` en el cuerpo. Por
eso cada caso se valida mirando la respuesta y no el status.

`run_client` recibe la sesión HTTP, así los tests lo ejercitan entero contra la app sin levantar
un servidor; por defecto usa `requests`, que es como lo corre la línea de comandos.
"""

import argparse
import json
from collections.abc import Callable
from typing import Any

import requests

MODELO = "chicago-arrest-xgboost"

# Cada caso: qué se pide y qué tiene que cumplir la respuesta.
CASOS: list[tuple[str, str, Callable[[Any], bool]]] = [
    (
        "los metadatos del modelo",
        f'{{ model(name: "{MODELO}") {{ name version framework }} }}',
        lambda data: data["model"]["name"] == MODELO and data["model"]["version"] == 1,
    ),
    (
        "una sola métrica, y nada más",
        f'{{ model(name: "{MODELO}") {{ metrics {{ mcc }} }} }}',
        lambda data: set(data["model"]["metrics"]) == {"mcc"},
    ),
    (
        "un modelo que no existe",
        '{ model(name: "otro-modelo") { name } }',
        lambda data: data["model"] is None,
    ),
]


def check(label: str, body: dict[str, Any], cumple: Callable[[Any], bool]) -> bool:
    """Muestra la respuesta y devuelve si cumple lo esperado."""
    try:
        ok = "errors" not in body and cumple(body.get("data"))
    except (KeyError, TypeError):
        ok = False
    print(f"[{'OK' if ok else 'FALLA'}] {label}")
    print(f"     {json.dumps(body, ensure_ascii=False)[:160]}")
    return ok


def run_client(url: str, session: Any = requests, timeout: float | None = 10) -> int:
    """Recorre los casos contra la API; devuelve 0 si todos cumplen.

    Con `timeout` en None el argumento no se manda: el TestClient de Starlette no lo acepta y
    avisa. Contra un servidor real hace falta, para que una request colgada no deje esperando
    al cliente para siempre.
    """
    opciones = {"timeout": timeout} if timeout is not None else {}
    try:
        resultados = [
            check(label, session.post(url, json={"query": query}, **opciones).json(), cumple)
            for label, query, cumple in CASOS
        ]
    except requests.RequestException as exc:
        print(f"Falló la llamada a {url} ({type(exc).__name__}).")
        print("¿Levantaste la API con `make graphql-run`?")
        return 1
    return 0 if all(resultados) else 1


def main() -> int:
    """Punto de entrada: `uv run python -m tp2_graphql.client [--url ...]`."""
    parser = argparse.ArgumentParser(description="Cliente de prueba de la API GraphQL")
    parser.add_argument("--url", default="http://127.0.0.1:8010/graphql")
    return run_client(parser.parse_args().url)


if __name__ == "__main__":
    raise SystemExit(main())
