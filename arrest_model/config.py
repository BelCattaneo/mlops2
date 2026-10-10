"""Configuración compartida por los tres servicios, sus clientes y los tests.

Es un módulo aparte y sin dependencias para que un cliente liviano pueda leerla sin cargar pandas
ni xgboost, que es lo que arrastra importar `arrest_model.model`.
"""

# El nombre con el que `model/model.pkl` identifica al modelo. Viaja en cada predicción de REST y
# gRPC, es el argumento de la query de GraphQL y el nodo final del linaje en Neo4j.
MODEL_NAME = "chicago-arrest-xgboost"

# El corte con el que un modelo decide si hay arresto cuando no trae uno propio: es la regla de
# `XGBClassifier.predict` y la que documentan los cuatro protocolos. Un modelo entrenado por el
# pipeline sí trae el suyo, elegido sobre validación, porque el corte que mejor decide depende de
# cómo se reponderó el entrenamiento y no del problema.
DEFAULT_THRESHOLD = 0.5
