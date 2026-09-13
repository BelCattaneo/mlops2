"""Mini-TP 2: esquema GraphQL con los metadatos del modelo de arrestos de Chicago.

Los datos salen del mismo `model/model.pkl` que sirven REST y gRPC: acá no se reimplementa
nada del modelo, solo se traduce su metadata al esquema.

El bundle no se carga al importar el módulo, entra por el contexto de la query. Así el esquema
se puede ejecutar en los tests sin levantar un servidor, y la app lo inyecta al arrancar.
"""

from datetime import datetime
from typing import Any

import strawberry


@strawberry.type
class Metrics:
    """Métricas del modelo sobre el conjunto de test del TP-final."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    auc: float
    mcc: float


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


def model_from_metadata(metadata: dict[str, Any]) -> Model:
    """Arma el tipo del esquema a partir de la metadata que viaja en el bundle."""
    return Model(
        name=metadata["name"],
        version=metadata["version"],
        framework=metadata["framework"],
        inputs=list(metadata["inputs"]),
        features=list(metadata["features"]),
        trained_at=datetime.fromisoformat(metadata["trained_at"]),
        metrics=Metrics(**metadata["metrics"]),
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
