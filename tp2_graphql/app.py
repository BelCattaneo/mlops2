"""Mini-TP 2: API GraphQL con los metadatos del modelo de arrestos de Chicago.

Monta el esquema en `/graphql`, con GraphiQL para probarlo desde el navegador.

El modelo se carga una sola vez, al crear la app, y viaja a los resolvers por el contexto de
cada query. Si no se puede cargar, el servicio no arranca: a diferencia de la API REST, acá no
hay un endpoint de salud que tenga sentido seguir sirviendo sin modelo.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from arrest_model.model import load_bundle
from tp2_graphql.lineage import connect
from tp2_graphql.schema import schema


def create_app(loader: Callable[[], dict[str, Any]] = load_bundle) -> FastAPI:
    """Crea la app; `loader` devuelve el bundle del modelo (los tests inyectan otro)."""
    bundle = loader()
    # El driver no conecta acá: es perezoso, así que la app levanta aunque Neo4j esté caído.
    driver = connect()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Cierra el driver al apagar; si no, su pool de conexiones queda abierto del lado de
        Neo4j hasta que la base las dé por muertas."""
        yield
        driver.close()

    def get_context() -> dict[str, Any]:
        """Contexto de cada query: el bundle ya cargado y el driver para el linaje."""
        return {"bundle": bundle, "driver": driver}

    app = FastAPI(title="Mini-TP 2 · Metadatos por GraphQL", lifespan=lifespan)
    app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql")
    return app


app = create_app()
