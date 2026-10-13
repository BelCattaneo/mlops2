# Levantar la plataforma

La plataforma del TP integrador corre en Docker: Airflow, MLflow, PostgreSQL y MinIO con un solo comando, y la API de predicción detrás de su propio perfil. Esta página es cómo arrancarla, cómo correr el pipeline y dónde mirar lo que produjo.

← [Arquitectura del integrador](arquitectura.md) · [README del repo](../README.md)

## Requisitos

Docker con al menos 4 GB de memoria asignados. Medido con el pipeline en reposo: 3,75 GiB con todo arriba, los ocho servicios de la plataforma más la API del perfil `serving`.

Y un `.env`, que no se versiona porque ahí van los secretos:

```bash
cp .env.example .env
```

Alcanza con eso tal cual. El único valor que conviene completar es `SOCRATA_APP_TOKEN`, que se saca gratis en [el portal de Chicago](https://data.cityofchicago.org/profile/edit/developer_settings): sin token la descarga igual funciona, pero el portal agrupa el límite de uso por dirección IP y puede cortar.

## Arrancar

```bash
make stack-up
```

Construye las imágenes la primera vez, levanta los servicios y espera a que respondan. Al terminar imprime dónde quedó cada cosa:

| servicio | dónde | credenciales | para qué |
|---|---|---|---|
| Airflow | <http://127.0.0.1:8081> | `airflow` / `airflow` | dispara y monitorea el pipeline |
| MLflow | <http://127.0.0.1:5001> | — | las métricas de cada corrida del pipeline |
| MinIO | <http://127.0.0.1:9001> | `minio` / `minio123` | el data lake: `data` y `mlflow` |
| PostgreSQL | `127.0.0.1:5433` | `airflow` / `airflow` | metadata de Airflow y de MLflow |

Los puertos salen del `.env` y los de arriba son los valores por defecto. Están elegidos para no chocar con lo que suele estar ocupado: 8081 en vez de 8080 para Airflow, y 5433 en vez de 5432 para PostgreSQL.

## Correr el pipeline

```bash
make stack-dag
```

Despausa el DAG `etl_with_taskflow` y lo dispara. El avance se mira en la interfaz de Airflow, en la vista de grafo.

Medido en una instalación nueva: la primera corrida tarda 8,9 minutos, casi todos de descarga, porque no hay nada en el lake y baja la ventana completa de 365 días —13 particiones mensuales, 81 MB, unos 226.000 reportes—. Las siguientes tardan 7 segundos, porque reusan la capa cruda y solo recalculan las capas derivadas.

Despausar el DAG hace que el scheduler cree además su propia corrida del período corriente, así que en una instalación nueva puede haber dos: la programada y la que dispara el comando. El DAG admite una sola corrida a la vez, así que la segunda espera en cola y cuando le toca encuentra la ventana ya completa. Eso es a propósito: dos corridas simultáneas se pisarían en el lake.

El pipeline también corre solo, una vez por mes, desde que el DAG queda despausado.

## Entrenar el modelo

```bash
make stack-train
```

Dispara el DAG `train_arrest_model`, que es aparte del ETL a propósito: reentrenar no tiene que obligar a reprocesar los datos, y procesar datos nuevos no tiene que disparar un entrenamiento. Lo que los une es la capa curada del lake.

Entrena sobre la partición curada escrita más recientemente —la última escrita, no la de fecha mayor— y mide las seis métricas contra el test de esa misma partición.

Lo que registra en MLflow no es el estimador suelto sino el modelo servible: recibe los seis campos crudos del contrato, codifica adentro con los parámetros de esa partición, y devuelve la probabilidad. El consumidor no codifica nada, así que no puede codificar distinto de como se entrenó. Queda con su firma de entrada declarada y valida con el mismo contrato que las APIs, así que también se sostiene expuesto solo con `mlflow models serve`.

La versión registrada toma el alias `champion`, que es lo que las APIs van a pedir: promover una versión es una operación de registro y no un redespliegue.

Cada corrida mide además cuánto se movieron los datos respecto de los que vio el champion que está servido, comparando los parámetros de preprocesamiento de las dos particiones. `drift_max_sigma` es el corrimiento de la media de la feature que más se movió, en desvíos del champion: las features estandarizadas valen 0 y 1 en entrenamiento por construcción, así que ese número dice a cuántos desvíos de lo que el modelo vio están llegando los datos nuevos.

Para calibrarlo: dos particiones consecutivas dan 0,000000, y la partición de antes de que el ETL midiera la distancia en el mismo CRS que el modelo contra la de después da **1,7773**, señalando la única feature que se movió. Un valor alto no es un error de la corrida: es la señal de que el modelo servido está viendo otra cosa que la que entrenó.

Las métricas de la última corrida se ven en <http://127.0.0.1:5001>, en el experimento `chicago-arrest`. Las del ETL van aparte, en `chicago-arrest-etl`: son métricas de datos, no de modelos, y no se comparan entre sí.

Si no hay ningún dataset curado, la tarea falla diciendo que hay que correr el ETL antes. Y si la partición que encuentra es de una versión vieja del ETL, falla diciendo qué columna le falta, en vez de entrenar con un dataset que el modelo no puede consumir.

## Servir el modelo

```bash
make stack-serve
```

Levanta la API de la plataforma, que sirve lo que registró el entrenamiento. Reusa el código del mini-TP 1, que es una entrega aparte: la misma imagen corrida suelta sirve el `model/model.pkl` versionado en el repo, y acá sirve el champion porque el entorno se lo indica. Va en su propio perfil del compose a propósito: sin una versión con el alias `champion` no hay nada que servir, así que se levanta después de `make stack-train` y no junto con la plataforma.

| | dónde | para qué |
|---|---|---|
| REST | <http://127.0.0.1:8002/docs> | `POST /v1/predict`, `/v1/predict/batch`, `/v1/metadata` y `/health` |

Es el único protocolo de servicio, y por qué está medido en [la arquitectura](arquitectura.md#decisiones-de-arquitectura): a 633 reportes por día la ventaja de gRPC son 1,35 segundos por día, y para la forma real de la carga —lotes, no eventos sueltos— REST le gana 6,92 ms contra 13,46.

No es el 8000 del mini-TP a propósito: el contenedor de la plataforma tiene tag, nombre y puerto propios (`mlops2-rest`), así que la plataforma y el mini-TP suelto pueden estar arriba a la vez y ningún `make rest-build` le pisa la imagen al otro. Adentro de la red del compose escucha en su puerto de siempre, que es el que nombra el diagrama de arquitectura.

A diferencia de los DAGs, que se montan desde el repo y toman los cambios al instante, la imagen de la API hornea el paquete `arrest_model` adentro. Por eso `make stack-serve` construye antes de levantar: saltearse ese paso deja el servicio sirviendo el código de la imagen anterior, con el modelo nuevo.

Lo que recibe por entorno es `MODEL_URI=models:/chicago-arrest-xgboost@champion`: un alias, no un número de versión. Promover otra versión es mover el alias en MLflow, sin tocar el compose ni reconstruir la imagen.

El servicio le pregunta al registro cada `MODEL_TTL_SECONDS` —60 en el compose— si hay otra versión, así que **promover no exige reiniciar nada**: se mueve el alias y en el próximo chequeo el servicio empieza a servir la versión nueva. La consulta no baja artefactos, solo resuelve el alias, y la descarga ocurre únicamente cuando el número de versión cambió.

```bash
# mover el alias desde cualquier cliente de MLflow
mlflow.MlflowClient().set_registered_model_alias("chicago-arrest-xgboost", "champion", "9")
```

Verificado contra la plataforma corriendo: con el servicio sirviendo la v11 se movió el alias a la v9; al instante seguía respondiendo v11 —todavía dentro del intervalo— y después del chequeo pasó a v9, sin que nadie tocara el contenedor.

Si el registro no contesta, el servicio sigue sirviendo el modelo que ya tenía cargado: una degradación del registro no puede convertirse en una caída del servicio. Y si arranca sin champion queda en 503 y lo vuelve a intentar, así que entrenar después lo levanta solo.

Que la versión servida es la del registro y no la del `.pkl` se ve en la respuesta: `GET /health` y cada predicción informan `model_version`, y `/v1/metadata` agrega el umbral con el que decide.

## El linaje de cada versión

El pipeline escribe un grafo mientras corre, en Neo4j, con un nodo por **instancia**: cada partición cruda, cada intermedia, cada curada y cada versión del modelo, encadenadas por `DERIVES`. No son las etapas del pipeline —eso ya está en el diagrama de arquitectura— sino lo que cada corrida produjo.

Se consulta en <http://127.0.0.1:7475>, con el usuario y la clave de `.env`. Las dos preguntas que contesta:

```cypher
// de qué salió una versión, a cualquier profundidad
MATCH (a)-[:DERIVES*1..]->(m:ModelVersion {name: "chicago-arrest-xgboost", version: 13})
RETURN DISTINCT a.key, head(labels(a))

// y la inversa: este mes del portal vino mal, ¿qué versiones hay que revisar?
MATCH (o {key: "raw/crimes/month=2026-03/crimes.csv"})-[:DERIVES*1..]->(m:ModelVersion)
RETURN DISTINCT m.name, m.version
```

La primera también la contesta MLflow, que registra de qué partición curada salió cada versión. La segunda no: es un recorrido hacia adelante de profundidad desconocida, y es lo que justifica una base de grafos en vez de una tabla.

Escribirlo es best-effort. Si Neo4j no responde, las tareas siguen —el linaje es trazabilidad, no una dependencia del pipeline de datos— y el resumen de la corrida registra `lineage_written` en 0, así que el hueco queda visible en MLflow en lugar de quedar en silencio. Verificado apagando Neo4j: la corrida termina en `success` y la métrica queda en 0. Y el grafo se repara solo, porque las tareas escriben su linaje también cuando toman el atajo de idempotencia: la partición que quedó afuera entra en la corrida siguiente sin recalcular nada.

## Qué deja en el lake

Tres capas en el bucket `data`, que se ven en la consola de MinIO:

| capa | clave | formato | retención |
|---|---|---|---|
| cruda | `raw/crimes/month=YYYY-MM/crimes.csv` y `raw/police_stations/police_stations.csv` | CSV, tal como llegó del portal | se conserva |
| intermedia | `enriched/crimes/date=YYYY-MM-DD/crimes.parquet` | Parquet | expira a los 30 días |
| curada | `curated/train/date=YYYY-MM-DD/train.parquet`, su `test`, y `curated/params/date=YYYY-MM-DD/params.json` | Parquet y JSON | se conserva |

La capa curada es el par de entrenamiento y prueba con las 7 features del modelo más la etiqueta, y los parámetros con los que se codificó: las frecuencias de cada categoría, la media y el desvío de cada numérica, y las comisarías proyectadas. Esos parámetros son la otra mitad del modelo —con otros, el mismo estimador predice cualquier cosa— así que el entrenamiento los mete adentro del artefacto. La capa está completa cuando están los tres: si falta alguno, la corrida siguiente la recalcula.

El detalle de qué hace cada capa está en [la arquitectura](arquitectura.md).

El bucket está versionado, así que un borrado no borra: deja una marca de borrado y el objeto se recupera por su `VersionId`.

En MLflow quedan cinco corridas por cada pasada del pipeline, una por etapa, con las métricas de cuántas filas entraron y salieron, el balance de clases y las features elegidas con su score.

## Los comandos

| comando | qué hace |
|---|---|
| `make stack-up` | levanta la plataforma y espera a que responda |
| `make stack-dag` | despausa y dispara el ETL |
| `make stack-train` | entrena con el último curado y registra el champion |
| `make stack-serve` | levanta la API sirviendo el champion |
| `make stack-ps` | muestra el estado de los servicios |
| `make stack-logs` | sigue los logs de todos |
| `make stack-down` | detiene la plataforma y conserva los volúmenes |

`make stack-down` no borra datos: el lake y las bases viven en volúmenes de Docker y sobreviven. Para empezar de cero, `docker compose --profile all down -v`.

## Si algo no arranca

Las APIs no levantan o `/health` da 503: es que todavía no hay nada con el alias `champion`. `make stack-train` lo registra. El log de cada una dice qué no pudo cargar.

El modelo salió entrenado con muy pocas filas: la ventana cruda quedó incompleta. `make stack-ps` no lo dice, pero contar las particiones sí: tienen que ser unas trece, una por mes. En la consola de MinIO, bajo `raw/crimes/`. Si hay una sola, la próxima corrida del ETL baja el histórico que falta: la decisión de la carga inicial mira la ventana entera y no el archivo del mes corriente.

El DAG no aparece en Airflow, o aparece con error: `docker compose --profile all exec -T airflow-scheduler airflow dags list-import-errors` dice qué no pudo importar.

Una tarea falló: el log completo está en la interfaz de Airflow, y también en `airflow/logs/dag_id=etl_with_taskflow/`, que está montado desde el repo.

La descarga de Socrata corta por límite de uso: poné el token en `.env` y recreá los contenedores de Airflow, que es lo que los hace releer el archivo.

```bash
docker compose --profile all up -d --force-recreate \
    airflow-scheduler airflow-apiserver airflow-dag-processor airflow-triggerer
```
