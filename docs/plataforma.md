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

## Qué deja en el lake

Tres capas en el bucket `data`, que se ven en la consola de MinIO:

| capa | clave | formato | retención |
|---|---|---|---|
| cruda | `raw/crimes/month=YYYY-MM/crimes.csv` y `raw/police_stations/police_stations.csv` | CSV, tal como llegó del portal | se conserva |
| intermedia | `enriched/crimes/date=YYYY-MM-DD/crimes.parquet` | Parquet | expira a los 30 días |
| curada | `curated/train/date=YYYY-MM-DD/train.parquet` y su `test` | Parquet | se conserva |

La capa curada es el par de entrenamiento y prueba con las 7 features del modelo más la etiqueta. El detalle de qué hace cada capa está en [la arquitectura](arquitectura.md).

El bucket está versionado, así que un borrado no borra: deja una marca de borrado y el objeto se recupera por su `VersionId`.

En MLflow quedan cinco corridas por cada pasada del pipeline, una por etapa, con las métricas de cuántas filas entraron y salieron, el balance de clases y las features elegidas con su score.

## Los comandos

| comando | qué hace |
|---|---|
| `make stack-up` | levanta la plataforma y espera a que responda |
| `make stack-dag` | despausa y dispara el ETL |
| `make stack-ps` | muestra el estado de los servicios |
| `make stack-logs` | sigue los logs de todos |
| `make stack-down` | detiene la plataforma y conserva los volúmenes |

`make stack-down` no borra datos: el lake y las bases viven en volúmenes de Docker y sobreviven. Para empezar de cero, `docker compose --profile all down -v`.

## Si algo no arranca

El DAG no aparece en Airflow, o aparece con error: `docker compose --profile all exec -T airflow-scheduler airflow dags list-import-errors` dice qué no pudo importar.

Una tarea falló: el log completo está en la interfaz de Airflow, y también en `airflow/logs/dag_id=etl_with_taskflow/`, que está montado desde el repo.

La descarga de Socrata corta por límite de uso: poné el token en `.env` y recreá los contenedores de Airflow, que es lo que los hace releer el archivo.

```bash
docker compose --profile all up -d --force-recreate \
    airflow-scheduler airflow-apiserver airflow-dag-processor airflow-triggerer
```
