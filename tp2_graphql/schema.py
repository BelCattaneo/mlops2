"""Mini-TP 2: esquema GraphQL con los metadatos del modelo de arrestos de Chicago.

Los datos salen del mismo `model/model.pkl` que sirven REST y gRPC: acá no se reimplementa
nada del modelo, solo se traduce su metadata al esquema.

El bundle no se carga al importar el módulo, entra por el contexto de la query. Así el esquema
se puede ejecutar en los tests sin levantar un servidor, y la app lo inyecta al arrancar.
"""

import asyncio
from dataclasses import fields
from datetime import datetime
from typing import Any

import strawberry

from tp2_graphql.lineage import lineage_of


@strawberry.type
class Metrics:
    """Métricas del modelo sobre el conjunto de test del TP-final."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    auc: float
    mcc: float


# Las métricas que declara el esquema. Sale de la clase para que agregar un campo alcance.
METRIC_NAMES = tuple(campo.name for campo in fields(Metrics))


@strawberry.type
class Artifact:
    """Un artefacto aguas arriba del modelo: un dataset o una transformación."""

    name: str
    kind: str


@strawberry.type
class Model:
    """El modelo que están sirviendo las APIs del repo."""

    name: str
    version: int
    framework: str
    inputs: list[str]
    features: list[str]
    trained_at: datetime
    metrics: Metrics

    @strawberry.field
    async def lineage(self, info: strawberry.Info) -> list[Artifact] | None:
        """De dónde salió el modelo: sus datasets y transformaciones, leídos de Neo4j.

        Solo se consulta si la query pide este campo; ese es justamente el punto de GraphQL.
        Es nullable a propósito: si Neo4j no responde, el error queda acá y el resto de la
        respuesta llega igual.

        Va en un hilo aparte porque el driver de Neo4j es sincrónico: resolverlo en el hilo del
        event loop dejaría sin atender al resto del servicio mientras la base tarda, incluidas
        las requests que ni siquiera piden el linaje.
        """
        artefactos = await asyncio.to_thread(lineage_of, info.context["driver"], self.name)
        return [Artifact(name=a["name"], kind=a["kind"]) for a in artefactos]


def model_from_metadata(metadata: dict[str, Any]) -> Model:
    """Arma el tipo del esquema a partir de la metadata que viaja en el bundle.

    De las métricas toma solo las que declara el esquema. Un reentrenamiento que agregue una
    métrica nueva no puede anular la respuesta entera ni devolverle al cliente un mensaje
    interno de Python, que es lo que pasaba al expandir el diccionario completo.
    """
    return Model(
        name=metadata["name"],
        version=metadata["version"],
        framework=metadata["framework"],
        inputs=list(metadata["inputs"]),
        features=list(metadata["features"]),
        trained_at=datetime.fromisoformat(metadata["trained_at"]),
        metrics=Metrics(**{nombre: metadata["metrics"][nombre] for nombre in METRIC_NAMES}),
    )


@strawberry.type
class Query:
    """Punto de entrada del esquema."""

    @strawberry.field
    def model(self, name: str, info: strawberry.Info) -> Model | None:
        """Devuelve el modelo con ese nombre, o null si no es el que está cargado."""
        metadata = info.context["bundle"]["metadata"]
        return model_from_metadata(metadata) if metadata["name"] == name else None


schema = strawberry.Schema(query=Query)
