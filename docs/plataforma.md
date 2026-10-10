# Levantar la plataforma

Los cuatro servicios del TP integrador corren en Docker con un solo comando. Esta página es cómo arrancarlos, cómo correr el pipeline y dónde mirar lo que produjo.

← [Arquitectura del integrador](arquitectura.md) · [README del repo](../README.md)

## Requisitos

Docker con al menos 4 GB de memoria asignados: la plataforma usa 4,24 GB medidos con los cuatro servicios arriba y el pipeline en reposo.

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

La primera corrida tarda unos 9 minutos y medio, de los cuales 8 son la descarga: no hay nada en el lake, así que baja la ventana completa de 365 días, unos 228.000 reportes. Las corridas siguientes tardan un minuto, porque reusan la capa cruda.

El pipeline también corre solo, una vez por mes, desde que el DAG queda despausado.

## Entrenar el modelo

```bash
make stack-train
```

Dispara el DAG `train_arrest_model`, que es aparte del ETL a propósito: reentrenar no tiene que obligar a reprocesar los datos, y procesar datos nuevos no tiene que disparar un entrenamiento. Lo que los une es la capa curada del lake.

Entrena sobre la partición curada escrita más recientemente —la última escrita, no la de fecha mayor— y mide las seis métricas contra el test de esa misma partición.

Lo que registra en MLflow no es el estimador suelto sino el modelo servible: recibe los seis campos crudos del contrato, codifica adentro con los parámetros de esa partición, y devuelve la probabilidad. El consumidor no codifica nada, así que no puede codificar distinto de como se entrenó. Queda con su firma de entrada declarada y valida con el mismo contrato que las APIs, así que también se sostiene expuesto solo con `mlflow models serve`.

La versión registrada toma el alias `champion`, que es lo que las APIs van a pedir: promover una versión es una operación de registro y no un redespliegue.

Las métricas de la última corrida se ven en <http://127.0.0.1:5001>, en el experimento `chicago-arrest`. Las del ETL van aparte, en `chicago-arrest-etl`: son métricas de datos, no de modelos, y no se comparan entre sí.

Si no hay ningún dataset curado, la tarea falla diciendo que hay que correr el ETL antes. Y si la partición que encuentra es de una versión vieja del ETL, falla diciendo qué columna le falta, en vez de entrenar con un dataset que el modelo no puede consumir.

## Servir el modelo

```bash
make stack-serve
```

Levanta las tres APIs de los mini-TPs dentro de la plataforma, sirviendo lo que registró el entrenamiento en vez del `model/model.pkl` que tienen horneado. Van en su propio perfil del compose a propósito: sin una versión con el alias `champion` no hay nada que servir, así que se levantan después de `make stack-train` y no junto con la plataforma.

| servicio | dónde | para qué |
|---|---|---|
| REST | <http://127.0.0.1:8000/docs> | `POST /v1/predict`, `/v1/predict/batch`, `/v1/metadata` y `/health` |
| GraphQL | <http://127.0.0.1:8010/graphql> | los metadatos del modelo y el linaje, con GraphiQL para probarlo |
| gRPC | `127.0.0.1:50051` | `Predict` y `PredictStream` |

Lo que reciben por entorno es `MODEL_URI=models:/chicago-arrest-xgboost@champion`: un alias, no un número de versión. Promover otra versión es mover el alias en MLflow, sin tocar el compose ni reconstruir ninguna imagen.

El alias se resuelve una sola vez, al arrancar cada servicio, que es lo mismo que hacían con el `.pkl`. Así que después de promover una versión nueva hay que reiniciarlos para que la tomen:

```bash
docker compose --profile all --profile serving restart rest graphql grpc
```

Que la versión servida es la del registro y no la del `.pkl` se ve en la respuesta: `GET /health` y cada predicción informan `model_version`.

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
| `make stack-serve` | levanta las tres APIs sirviendo el champion |
| `make stack-ps` | muestra el estado de los servicios |
| `make stack-logs` | sigue los logs de todos |
| `make stack-down` | detiene la plataforma y conserva los volúmenes |

`make stack-down` no borra datos: el lake y las bases viven en volúmenes de Docker y sobreviven. Para empezar de cero, `docker compose --profile all down -v`.

## Si algo no arranca

Las APIs no levantan o `/health` da 503: es que todavía no hay nada con el alias `champion`. `make stack-train` lo registra. El log de cada una dice qué no pudo cargar.

El puerto 8000 ya está en uso al correr `make stack-serve`: es el mini-TP corriendo suelto con `make rest-up`, que publica el mismo puerto. `make rest-down` lo libera.

El DAG no aparece en Airflow, o aparece con error: `docker compose --profile all exec -T airflow-scheduler airflow dags list-import-errors` dice qué no pudo importar.

Una tarea falló: el log completo está en la interfaz de Airflow, y también en `airflow/logs/dag_id=etl_with_taskflow/`, que está montado desde el repo.

La descarga de Socrata corta por límite de uso: poné el token en `.env` y recreá los contenedores de Airflow, que es lo que los hace releer el archivo.

```bash
docker compose --profile all up -d --force-recreate \
    airflow-scheduler airflow-apiserver airflow-dag-processor airflow-triggerer
```
