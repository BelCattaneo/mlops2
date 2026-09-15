# Mini-TP 2 — Los metadatos del modelo por GraphQL

Los metadatos del mismo modelo de arrestos de Chicago que el TP1 sirve por REST, expuestos por GraphQL: un esquema tipado con Strawberry, y un campo que lee el linaje del modelo desde Neo4j.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md) · [Mini-TP 3 (gRPC)](../tp3_grpc/README.md)

## Cómo correrlo

Todos los comandos se corren desde la raíz del repo.

| comando | qué hace |
|---|---|
| `make graphql-run` | levanta la API en el puerto 8010, con GraphiQL en `/graphql` |
| `make graphql-up` · `make graphql-down` | levanta y detiene la API en Docker, en el mismo puerto |
| `make graphql-logs` | muestra los logs del contenedor |
| `make graphql-client` | corre el cliente de prueba contra la API |
| `make graphql-compare` | compara la misma lectura por REST y por GraphQL |
| `make neo4j-up` · `make neo4j-down` | levanta y detiene Neo4j en Docker |
| `make graphql-seed` | siembra el linaje del modelo en Neo4j |

Para probarlo desde el navegador, con `make graphql-run` corriendo, abrir <http://127.0.0.1:8010/graphql> y pegar:

```graphql
{
  model(name: "chicago-arrest-xgboost") {
    name
    version
    metrics { mcc auc }
  }
}
```

## En Docker

La API tiene su propia imagen, como las del TP1 y el TP3. Neo4j no va adentro: corre en su contenedor, y los dos comparten una red de Docker en la que la API lo encuentra por nombre.

```bash
make neo4j-up && make graphql-seed
make graphql-up       # construye la imagen, levanta el contenedor y espera a que responda
make graphql-client
```

Si Neo4j no está levantado, el contenedor arranca igual y solo `lineage` viene en `null`.

## El esquema

Un solo endpoint y un esquema que declara qué campos existen y de qué tipo son. El cliente arma su recorte: pide los campos que necesita y recibe exactamente eso.

```graphql
type Query {
  model(name: String!): Model
}

type Model {
  name: String!
  version: Int!
  framework: String!
  inputs: [String!]!
  features: [String!]!
  trainedAt: DateTime!
  metrics: Metrics!
  lineage: [Artifact!]
}

type Metrics { accuracy: Float! precision: Float! recall: Float! f1: Float! auc: Float! mcc: Float! }
type Artifact { name: String! kind: String! }
```

Un nombre que no es el del modelo cargado devuelve `null`, sin error.

Las métricas salen de `model/model.pkl`, el mismo bundle que sirven REST y gRPC. La consigna acepta que vengan de un registro local o simuladas; estas son las reales del modelo entregado.

El bundle no se carga al importar el módulo: entra por el contexto de cada query. Eso permite ejecutar el esquema en los tests sin levantar un servidor.

## El linaje

`lineage` es el único campo que sale de Neo4j, y solo se consulta si la query lo pide.

El linaje es la trazabilidad del modelo: de qué archivos crudos salió y por qué transformaciones pasó. Se guarda como grafo porque la pregunta que interesa —qué hay aguas arriba de este modelo— tiene largo variable, y en un grafo eso es un recorrido de una línea en vez de una cadena de JOINs.

```
Crimes_Chicago_2024.csv ─┐
Police_Stations_20251005.csv ─┴→ 1_Creacion_dataset → ..._processed.csv
  → 3_Outliers_Encoding → ..._outliers_encoded(.csv, _test.csv)
  → 4_Escalado → ..._standardized(.csv, _test.csv)
  → 5_Balanceo → ..._standardized_combined.csv
  → 6_Feature_Selection → ..._final.csv, ..._final_test.csv
  → entrenamiento → model/model.pkl
```

Son 16 artefactos aguas arriba del modelo: 10 datasets y 6 transformaciones. La cadena está verificada contra los archivos del TP-final y contra lo que lee el script de entrenamiento, que además del par final toma el dataset procesado y el de comisarías para calcular los parámetros de codificación.

El balanceo dejó tres variantes y existe una rama con PCA; el modelo entregado usa `combined`, así que solo esa cadena se siembra.

El sembrado es idempotente: usa `MERGE` y no borra la base.

Si Neo4j no está corriendo, `lineage` viene en `null` con el error acotado a ese campo, y el resto de la respuesta llega completa. La API arranca igual sin Neo4j. El error que ve el cliente es un mensaje genérico: el detalle de la conexión queda en el log del servicio.

## La comparación con REST

La vista a armar es chica: el nombre del modelo y una sola métrica, el MCC.

| protocolo | llamadas | bytes recibidos |
|---|---|---|
| REST | 1 | 557 |
| GraphQL | 1 | 89 |

Las dos vistas traen lo mismo. La diferencia es que `GET /v1/metadata` devuelve el paquete entero —versión, framework, los 6 campos de entrada, las 7 features, las 6 métricas y la fecha— cuando solo se querían dos campos.

Aparte de la tabla: el linaje no lo expone ningún endpoint REST, así que sumarlo a la vista obligaría a crear uno. En GraphQL es un campo más en la misma query, resuelto contra otra fuente de datos.

## Reflexión

GraphQL trajo solo los campos pedidos: 89 bytes contra 557 de REST, con una llamada cada uno. El desarrollo está en la sección 6 del notebook.

## El notebook

[`mini_tp2_actividad.ipynb`](mini_tp2_actividad.ipynb) es el starter de la cátedra completado, y se entrega ejecutado con sus salidas. Levanta las dos APIs en hilos del mismo proceso, consulta GraphQL desde un cliente Python, corre la comparación y muestra el linaje.

Los `.py` de esta carpeta son la fuente y están cubiertos por tests; el notebook los importa y los muestra.

```bash
make neo4j-up && make graphql-seed
uv run jupyter nbconvert --to notebook --execute --inplace tp2_graphql/mini_tp2_actividad.ipynb
```

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `schema.py` | los tipos y la query; el bundle entra por el contexto |
| `app.py` | FastAPI con el router de Strawberry en `/graphql` |
| `client.py` | cliente de prueba; devuelve 0/1 según los casos esperados |
| `compare.py` | la comparación con REST, en llamadas y bytes |
| `lineage.py` | el grafo de linaje: sembrado idempotente y la consulta en Cypher |
| `Dockerfile` | la imagen de la API: dependencias base más el grupo `graphql`, sin Neo4j |

El driver de Neo4j es perezoso y no conecta hasta la primera consulta, que es lo que permite que el servicio levante con la base caída. Para sembrar se usa otra función, que sí espera a que Neo4j acepte conexiones, porque el contenedor tarda en arrancar.
