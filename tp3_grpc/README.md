# Mini-TP 3 — Servir el modelo por gRPC

El mismo modelo de arrestos de Chicago que el TP1 sirve por REST, expuesto por gRPC: contrato tipado en un `.proto`, protobuf binario sobre HTTP/2, con un método unary y uno de server-streaming.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md)

> Pendiente: falta escribir la reflexión final (punto 5 de la consigna). Los datos ya están medidos, acá abajo y en el notebook.

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

Los dos protocolos hacen el mismo trabajo (validar, codificar, predecir) y se miden del mismo lado: comparar gRPC local contra REST en contenedor mediría el empaquetado, no el protocolo. REST se mide de dos formas a propósito, porque gRPC siempre reutiliza el canal: la comparación justa es contra keep-alive.

Se midió repetidas veces, porque con una sola medición no se puede separar un efecto real del ruido. Las mediciones dedicadas son las de las tablas de abajo: una con los dos servicios locales y dos con los dos en contenedor. Además, cada ejecución del notebook agrega una medición local más.

### Una llamada

Mediciones dedicadas, 300 repeticiones, ms por llamada:

| forma | local | contenedor (1) | contenedor (2) |
|---|---|---|---|
| REST sin sesión | 2.65 | 4.76 | 4.34 |
| REST keep-alive | 2.51 | 3.16 | 3.61 |
| gRPC unary | 1.92 | 1.91 | 2.15 |

### Un lote de 100 reportes

Milisegundos totales:

| forma | local | contenedor (1) | contenedor (2) |
|---|---|---|---|
| 100 × `POST /v1/predict` | 268.8 | 288.5 | 413.9 |
| 1 × `POST /v1/predict/batch` | 4.2 | 4.4 | 6.0 |
| 1 × `PredictStream` | 6.4 | 12.5 | 12.0 |

El notebook corre además su propia medición local cada vez que se ejecuta; sus números están en la salida de la celda del benchmark.

### Entrega del streaming y tamaño del mensaje

En un lote de 100, la primera predicción llega alrededor de los 3 ms y la última entre 7 y 9 ms según la corrida.

El mismo reporte pesa 60 bytes en protobuf contra 161 en JSON (2.7x), porque en protobuf viajan los números de campo y no sus nombres.

### Qué se repite

gRPC contra REST keep-alive: cinco mediciones locales dieron entre 1.31x y 1.55x, y las dos con los dos servicios en contenedor dieron 1.65x y 1.68x. Los rangos no se superponen, así que la ventaja de gRPC se agranda dentro de Docker, porque reutiliza una sola conexión HTTP/2 mientras REST paga la red de Docker en cada llamada. El margen entre un rango y el otro es chico, así que conviene no exagerar el efecto.

También se repite la dirección del lote: `POST /v1/predict/batch` le gana a `PredictStream` en todas las corridas.

### Qué no se puede concluir

La magnitud de esa ventaja del lote no se distingue del ruido: alrededor de 1.5x–2.5x en local contra 2.0x–2.8x en contenedor, o sea rangos superpuestos.

Y "gRPC es inmune al contenedor" es falso, aunque lo pareciera en la primera corrida. Con dos mediciones, gRPC se degrada del orden del 0–15% y REST keep-alive alrededor del 34%: se degrada bastante menos, no cero.

Los números varían entre corridas (una laptop con Docker Desktop, no un banco de pruebas): sirven para comparar rangos, no para la tercera cifra.

> Conclusiones pendientes. Lo de arriba son las observaciones; la interpretación y las tres respuestas de la consigna se completan en el notebook.

## El notebook

[`mini_tp3_actividad.ipynb`](mini_tp3_actividad.ipynb) es el starter de la cátedra completado, y se entrega ejecutado con sus salidas. Levanta el servidor gRPC en un hilo del mismo proceso (ahí se ve que el modelo se carga una sola vez), lo llama unary y por streaming, levanta además la API REST del TP1 en otro hilo y corre el benchmark.

Los `.py` de esta carpeta son la fuente y están cubiertos por tests; el notebook los importa y los muestra con `IPython.display.Code`, para que no haya dos copias del mismo código.

```bash
uv run jupyter nbconvert --to notebook --execute --inplace tp3_grpc/mini_tp3_actividad.ipynb
```

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `scoring.proto` | el contrato: mensajes y servicio |
| `scoring_pb2.py` · `scoring_pb2_grpc.py` | generados por protoc; versionados, no se editan |
| `server.py` | `report_from_proto`, el servicer con los dos métodos, y `serve()` que arranca sin bloquear |
| `client.py` | cliente de prueba end-to-end; devuelve 0/1 según los status esperados |
| `benchmark.py` | la comparación de latencia contra REST |
| `Dockerfile` | `python:3.12-slim` + uv, solo el grupo `grpc`, puerto 50051 |

`serve()` recibe el bundle como parámetro y acepta `port=0` para que el sistema elija un puerto libre: eso es lo que permite levantarlo en los tests y en el notebook sin chocar con nada.
