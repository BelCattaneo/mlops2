"""Mini-TP 2: API GraphQL con los metadatos del modelo de arrestos de Chicago.

Monta el esquema en `/graphql`, con GraphiQL para probarlo desde el navegador.

El modelo se carga una sola vez, al crear la app, y viaja a los resolvers por el contexto de
cada query. Si no se puede cargar, el servicio no arranca: a diferencia de la API REST, acá no
hay un endpoint de salud que tenga sentido seguir sirviendo sin modelo.
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from arrest_model.model import load_bundle
from tp2_graphql.schema import schema


def create_app(loader: Callable[[], dict[str, Any]] = load_bundle) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo (los tests inyectan otro)."""
    bundle = loader()

    def get_context() -> dict[str, Any]:
        """Contexto de cada query: el bundle ya cargado, sin volver a leer el archivo."""
        return {"bundle": bundle}

    app = FastAPI(title="Mini-TP 2 · Metadatos por GraphQL")
    app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql")
    return app


app = create_app()
