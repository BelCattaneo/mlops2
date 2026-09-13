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

### Cómo se midió

Para que la comparación mida el protocolo y no otra cosa, los dos lados tienen que hacer el mismo trabajo y medirse en el mismo lugar. Tres decisiones lo sostienen:

- Los dos servicios dejan una línea de log por request. REST la tiene desde el TP1; el servidor gRPC no la tenía, y se le agregó un interceptor justamente para emparejar. Sin eso REST pagaba un costo que gRPC no, y la diferencia medida lo habría incluido.
- Toda respuesta REST se valida con `raise_for_status()`. Sin eso, un servicio que contesta 503 se mide como si fueran predicciones: probado a propósito, daba REST cinco veces más rápido que gRPC, o sea la conclusión al revés.
- REST se mide de dos formas, sin sesión y con keep-alive, porque gRPC siempre reutiliza el canal. La comparación justa es contra keep-alive; la otra muestra cuánto cuesta abrir la conexión.

### Las cohortes

| cohorte | qué es |
|---|---|
| `rest-local` · `grpc-local` | los dos servicios como proceso en la máquina |
| `rest-dockerizado` · `grpc-dockerizado` | los dos servicios en contenedor al mismo tiempo |

Nunca se compara una cohorte local contra una dockerizada de otro protocolo: eso mediría el empaquetado, no el protocolo.

### Las corridas

Tres corridas por condición, 300 repeticiones por medición, todas seguidas en una misma sesión. Se corre más de una vez porque con una sola medición no se puede distinguir un efecto real del ruido.

Las mediciones de sesiones anteriores se descartaron. Los valores absolutos se mueven bastante con el estado de la máquina —entre tandas, toda la columna dockerizada se movió sin que cambiara el código— así que solo son comparables entre sí las corridas de una misma tanda.

### La tabla

Cada bloque es una cohorte; el nombre se escribe una sola vez y las filas siguientes son del mismo bloque.

| cohorte | prueba | variante | corridas (ms) | mediana |
|---|---|---|---|---|
| `rest-local` | una llamada | sin sesión | 2.78 · 2.82 · 2.76 | 2.78 |
|  | una llamada | keep-alive | 2.82 · 2.64 · 2.66 | 2.66 |
|  | lote de 100 | 100 llamadas sueltas | 275.61 · 252.94 · 255.83 | 255.83 |
|  | lote de 100 | 1 llamada al batch | 5.86 · 3.32 · 3.07 | 3.32 |
| `rest-dockerizado` | una llamada | sin sesión | 5.58 · 6.08 · 5.63 | 5.63 |
|  | una llamada | keep-alive | 4.94 · 5.34 · 4.83 | 4.94 |
|  | lote de 100 | 100 llamadas sueltas | 491.85 · 527.44 · 507.65 | 507.65 |
|  | lote de 100 | 1 llamada al batch | 6.92 · 7.60 · 6.08 | 6.92 |
| `grpc-local` | una llamada | canal reusado | 1.81 · 1.89 · 1.85 | 1.85 |
|  | lote de 100 | 1 PredictStream | 8.82 · 6.42 · 6.46 | 6.46 |
| `grpc-dockerizado` | una llamada | canal reusado | 2.81 · 2.81 · 2.75 | 2.81 |
|  | lote de 100 | 1 PredictStream | 12.41 · 13.46 · 16.78 | 13.46 |

Aparte de la tabla, dos datos medidos por separado: el mismo reporte pesa 60 bytes en protobuf contra 161 en JSON (2.7x), porque en protobuf viajan los números de campo y no sus nombres; y en un `PredictStream` de 100 la primera predicción llega alrededor de los 3 ms y la última entre 7 y 9 ms, o sea que el stream entrega de a poco en vez de todo al final.

### Qué se repite

Rangos separados, o sea efecto reproducible:

- gRPC contra REST keep-alive: 1.40x–1.56x local y 1.76x–1.90x dockerizado. La ventaja de gRPC se agranda dentro de Docker, porque reutiliza una sola conexión HTTP/2 mientras REST paga la red de Docker en cada llamada.
- Dockerizar cuesta caro y no por igual: la mediana empeora +102% en `rest-local` sin sesión, +86% con keep-alive y +52% en `grpc-local`. gRPC aguanta bastante mejor, pero está lejos de ser inmune.
- Agrupar es lo que más mueve la aguja: 100 llamadas sueltas contra una sola llamada al batch da entre 47x y 83x, en las dos condiciones.
- `POST /v1/predict/batch` le gana a `PredictStream` en las seis corridas.

### Qué no se puede concluir

Que la ventaja del batch sobre el stream dependa de dockerizar: da 1.51x–2.11x local contra 1.77x–2.76x dockerizado, o sea rangos superpuestos. La dirección se repite siempre; la magnitud no se distingue del ruido.

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
| `server.py` | `report_from_proto`, el servicer con los dos métodos, el interceptor de log y `serve()` |
| `client.py` | cliente de prueba end-to-end; devuelve 0/1 según los status esperados |
| `benchmark.py` | la comparación de latencia contra REST |
| `Dockerfile` | `python:3.12-slim` + uv, solo el grupo `grpc`, puerto 50051 |

`serve()` recibe el bundle como parámetro y acepta `port=0` para que el sistema elija un puerto libre: eso es lo que permite levantarlo en los tests y en el notebook sin chocar con nada.
