# Mini-TP 3 — Servir el modelo por gRPC

El mismo modelo de arrestos de Chicago que el TP1 sirve por REST, expuesto por gRPC: contrato tipado en un `.proto`, protobuf binario sobre HTTP/2, con un método unary y uno de server-streaming.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md) · [Mini-TP 2 (GraphQL)](../tp2_graphql/README.md) · [Mini-TP 4 (streaming)](../tp4_streaming/README.md) · [Mini-TP 5 (federado)](../tp5_federated/README.md) · [Mini-TP 6 (data lake)](../tp6_datalake/README.md)

## Cómo correrlo

Todos los comandos se corren desde la raíz del repo.

| comando | qué hace |
|---|---|
| `make grpc-stubs` | regenera `scoring_pb2.py` y `scoring_pb2_grpc.py` desde el `.proto` |
| `make grpc-run` | levanta el servidor local en el puerto 50051 |
| `make grpc-up` | construye la imagen, levanta el contenedor y espera a que acepte conexiones |
| `make grpc-client` | corre el cliente de prueba contra el servicio |
| `make grpc-bench` | compara la latencia contra REST (los dos servicios arriba) |
| `make grpc-logs` · `make grpc-down` | logs y detener el contenedor |

Sin `make`:

```bash
uv run python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. tp3_grpc/scoring.proto
uv run python -m tp3_grpc.server                    # servidor local
uv run python -m tp3_grpc.client                    # cliente de prueba
docker build -f tp3_grpc/Dockerfile -t arrest-grpc . && docker run --rm -p 50051:50051 arrest-grpc
```

gRPC no se prueba con `curl`: el mensaje es binario y viaja sobre HTTP/2. Por eso la espera de arranque de `make grpc-up` no es un `curl` como en REST, sino una sonda de canal listo (`grpc.channel_ready_future`).

## El contrato

Todo sale de [`scoring.proto`](scoring.proto): `protoc` lo compila y genera los mensajes (`scoring_pb2.py`) y el stub del cliente más la clase base del servidor (`scoring_pb2_grpc.py`). Esos dos archivos se versionan y no se editan a mano; un test los regenera en un temporal y los compara, así que si alguien toca el `.proto` y no regenera, los tests fallan.

A diferencia del starter de la cátedra —que propone un `repeated double values` anónimo— el contrato declara los mismos 6 campos crudos que valida la API REST, cada uno con su tipo. La fecha viaja como `google.protobuf.Timestamp`, es decir un instante absoluto en UTC; el servidor lo convierte a hora de Chicago, que es como se entrenó la feature `Day_sin`.

| método | tipo | qué hace |
|---|---|---|
| `Predict(CrimeReport) → Prediction` | unary | un reporte, una predicción |
| `PredictStream(CrimeBatch) → stream Prediction` | server streaming | un lote, N predicciones en el mismo orden |

### Errores

| caso | status |
|---|---|
| campo faltante, IUCR inválido, `primary_type` desconocido, lat/lon fuera de Chicago | `INVALID_ARGUMENT`, con el campo que falló |
| lote vacío, o un item inválido dentro del lote | `INVALID_ARGUMENT`, con el índice del item |

El lote se valida entero antes de puntuar nada: si no, el cliente recibiría algunas predicciones y recién después el error.

### Qué no tiene, respecto de REST

gRPC implementa 2 de los 4 endpoints del TP1: no hay equivalente de `GET /health` ni de `GET /v1/metadata`, porque la consigna del TP3 no los pide. Si hicieran falta, los idiomáticos serían `grpc.health.v1` y un RPC `GetMetadata`.

## Qué se reutiliza

El servicio no reimplementa nada del modelo. La validación (`CrimeReport`), la codificación de las 7 features y la predicción viven en `arrest_model/`, compartidas con REST. Lo propio de este TP es solo el transporte: el `.proto`, traducir mensajes protobuf a ese núcleo, y devolver la respuesta.

## Medición de latencia

`benchmark.py` compara las dos APIs sirviendo el mismo modelo. Se corre con `make grpc-bench`, con los dos servicios levantados.

Se midieron cuatro cohortes: las dos APIs como proceso en la máquina (`rest-local`, `grpc-local`) y las dos en contenedor (`rest-dockerizado`, `grpc-dockerizado`). A cada una se le tomaron dos pruebas: una llamada suelta, repetida 300 veces, y un lote de 100 reportes. De REST se miden además dos formas de conectarse, abriendo la conexión en cada llamada y reutilizándola, porque gRPC siempre reutiliza el canal y la comparación pareja es contra esa segunda forma.

Cada cohorte se midió tres veces, porque con una sola medición no se distingue un efecto real del ruido. Los valores crudos quedaron en [`latencias.json`](latencias.json), y el detalle de la medición con su lectura está en [`latencias.md`](latencias.md). El [notebook](mini_tp3_actividad.ipynb) muestra la tabla de resultados y la reflexión.

## El notebook

[`mini_tp3_actividad.ipynb`](mini_tp3_actividad.ipynb) es el starter de la cátedra completado, y se entrega ejecutado con sus salidas. Levanta el servidor gRPC en un hilo del mismo proceso (ahí se ve que el modelo se carga una sola vez), lo llama unary y por streaming, y muestra la tabla de latencias medida con `benchmark.py`.

Los `.py` de esta carpeta son la fuente y están cubiertos por tests; el notebook los importa y los muestra con `IPython.display.Code`, para que no haya dos copias del mismo código.

```bash
uv run jupyter nbconvert --to notebook --execute --inplace tp3_grpc/mini_tp3_actividad.ipynb
```

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `scoring.proto` | el contrato: mensajes y servicio |
| `scoring_pb2.py` · `scoring_pb2_grpc.py` | generados por protoc; versionados, no se editan |
| `server.py` | `report_from_proto`, el servicer con los dos métodos, el interceptor de log y `serve()` |
| `client.py` | cliente de prueba end-to-end; devuelve 0/1 según los status esperados |
| `benchmark.py` | la comparación de latencia contra REST |
| `Dockerfile` | `python:3.12-slim` + uv, solo el grupo `grpc`, puerto 50051 |

`serve()` recibe el bundle como parámetro y acepta `port=0` para que el sistema elija un puerto libre: eso es lo que permite levantarlo en los tests y en el notebook sin chocar con nada.
