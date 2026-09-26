# Mini-TP 4 — El modelo puntuando un flujo

El mismo modelo de arrestos de Chicago que los TPs anteriores sirven por REST, GraphQL y gRPC, ahora puntuando un flujo continuo de eventos: cada reporte se puntúa apenas llega, con métricas por ventana y una alerta cuando los datos de entrada se corren de lo que el modelo vio al entrenar.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md) · [Mini-TP 2 (GraphQL)](../tp2_graphql/README.md) · [Mini-TP 3 (gRPC)](../tp3_grpc/README.md)

## Cómo correrlo

Todos los comandos se corren desde la raíz del repo.

| comando | qué hace |
|---|---|
| `make stream-run` | puntúa un flujo de 400 reportes, con el corrimiento de zona a la mitad |
| `make stream-compare` | compara puntuar el flujo de a uno contra puntuarlo en lote |
| `make redpanda-up` · `make redpanda-down` | levanta y detiene el broker en Docker |
| `make stream-kafka` | corre el mismo flujo contra el broker |

## El flujo

Los eventos son reportes sintéticos: se generan alrededor de la zona donde el modelo vio la mayoría de los crímenes y pasan por el mismo `CrimeReport` que valida la API REST, así que el flujo ejercita el camino real de datos. La semilla fija el flujo entero, de modo que una corrida se puede repetir.

A partir de cierto evento los reportes se corren 13 km al norte. Ese es el cambio de distribución que la consigna pide provocar para tener algo que detectar.

## El consumidor

Cada evento se valida, se codifica con `arrest_model` y se puntúa apenas llega. La ventana es deslizante: guarda lo que llegó en el último segundo y descarta lo viejo, así las métricas describen cómo viene el flujo ahora y no desde que arrancó.

```
ventana @  100 eventos |  82 en ventana | throughput 82.4 ev/s | p95 7.18 ms | drift 0.21 | probabilidad media 0.491
ventana @  200 eventos |  85 en ventana | throughput 85.1 ev/s | p95 6.39 ms | drift 0.24 | probabilidad media 0.365
ventana @  300 eventos |  83 en ventana | throughput 83.4 ev/s | p95 7.69 ms | drift 1.37 | probabilidad media 0.382  ← ALERTA de drift
ventana @  400 eventos |  83 en ventana | throughput 83.4 ev/s | p95 6.67 ms | drift 1.36 | probabilidad media 0.509
```

## Las métricas de la ventana

| métrica | qué mide |
|---|---|
| throughput | eventos por segundo; si baja, el consumidor se está quedando atrás del flujo |
| p95 | la latencia que el 95% de los eventos no supera; el promedio escondería los casos lentos |
| drift | cuánto se corrieron las entradas respecto del entrenamiento, en desvíos |
| probabilidad media | qué está prediciendo el modelo en esa ventana |

El drift sale de las tres features estandarizadas. El `.pkl` guarda la media y el desvío con los que se entrenó y la codificación les aplica el z-score, así que en entrenamiento valen 0 y 1: cuánto se aleja de 0 la media de la ventana es cuánto se corrió la entrada. El indicador toma la mayor de las tres en valor absoluto, para que no haya que elegir de antemano cuál se va a mover.

La alerta salta cuando el indicador cruza medio desvío, y no se repite mientras el drift dure: avisar en cada ventana sería ruido.

Se mide el drift de las entradas y no el de las predicciones porque la salida puede no moverse aunque los datos cambien. En la corrida de arriba las entradas pasaron de 0.21 a 1.37 desvíos mientras la probabilidad media siguió alrededor de 0.4: el modelo contesta con normalidad sobre datos de una zona que casi no vio.

Lo que este indicador no cubre: las features categóricas, que se codifican por frecuencia y no están estandarizadas. Un cambio en la mezcla de tipos de delito no lo detectaría.

## La comparación con batch

Los mismos 1000 eventos, puntuados de a uno y puntuados de una sola vez. Los dos caminos hacen el mismo trabajo, validar y codificar y predecir, y se miden del mismo lado, sin la cola ni el ritmo de llegada.

| camino | total (ms) | por evento (ms) |
|---|---|---|
| online | 1234.4 | 1.234 |
| batch | 4.4 | 0.004 |

Las predicciones de los dos caminos coinciden exactamente, y hay un test que lo verifica: si difirieran, el camino online estaría ordenando mal las features, perdiendo eventos o codificando distinto.

## El mismo flujo contra Kafka

El consumidor no sabe de dónde vienen los eventos, así que corre igual contra un broker real. Con `make redpanda-up` levantado, `make stream-kafka` publica en el topic y consume desde ahí, con el mismo resultado que en memoria.

La cola en memoria es lo que usan los tests y el notebook, porque corre en cualquier máquina y da siempre lo mismo. El broker es el camino de producción y la capa de streaming del TP integrador.

## El notebook

[`mini_tp4_actividad.ipynb`](mini_tp4_actividad.ipynb) es el starter de la cátedra completado, y se entrega ejecutado con sus salidas. Los `.py` de esta carpeta son la fuente y están cubiertos por tests; el notebook los importa y los muestra.

```bash
uv run jupyter nbconvert --to notebook --execute --inplace tp4_streaming/mini_tp4_actividad.ipynb
```

Sin broker levantado, la celda de Kafka lo informa y el notebook sigue.

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `events.py` | genera los reportes del flujo, con semilla y corrimiento de zona |
| `sources.py` | las dos fuentes, la cola en memoria y el topic de Kafka, con la misma interfaz |
| `metrics.py` | throughput, p95 y drift, calculados sobre datos que entran por parámetro |
| `consumer.py` | la inferencia online, la ventana deslizante y la alerta |
| `compare.py` | el mismo conjunto puntuado de a uno contra en lote |
| `run.py` | el comando que arma la fuente, corre el flujo e imprime cada ventana |

Los tests que necesitan el broker llevan el marcador `kafka` y se saltean solos en una máquina sin Docker.
