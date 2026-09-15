"""Configuración compartida por los tres servicios, sus clientes y los tests.

Es un módulo aparte y sin dependencias para que un cliente liviano pueda leerla sin cargar pandas
ni xgboost, que es lo que arrastra importar `arrest_model.model`.
"""

# El nombre con el que `model/model.pkl` identifica al modelo. Viaja en cada predicción de REST y
# gRPC, es el argumento de la query de GraphQL y el nodo final del linaje en Neo4j.
MODEL_NAME = "chicago-arrest-xgboost"
