# Mini-TP 6 — El modelo en el Data Lake

El mismo modelo de arrestos de Chicago que sirven las APIs del repo, ahora guardado en un Data Lake y servido desde ahí en lugar de leerlo del disco o de hornearlo en la imagen.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md) · [Mini-TP 2 (GraphQL)](../tp2_graphql/README.md) · [Mini-TP 3 (gRPC)](../tp3_grpc/README.md) · [Mini-TP 4 (streaming)](../tp4_streaming/README.md) · [Mini-TP 5 (federado)](../tp5_federated/README.md)

## Cómo correrlo

Necesita MinIO levantado. El compose del repo lo trae, junto con MLflow para el paso opcional:

```bash
docker compose --profile all up -d
make lake-run
```

El comando crea las zonas, baja los datos, publica el modelo, lo vuelve a bajar para predecir y registra la corrida:

```
lake      · s3://arrest-lake con las zonas raw, curated, models
raw       · reportes y comisarías, origen socrata
curated   · s3://arrest-lake/curated/arrests/arrests.parquet
models    · s3://arrest-lake/models/v1/model.pkl
predicción desde el lake · arrest=0 probabilidad=0.0684 modelo=chicago-arrest-xgboost
mlflow    · corrida 51bb6ab9… con el artefacto en el lake
```

## Las zonas

En S3 no hay carpetas: las claves son planas y la barra es una convención. La zona es el prefijo de la clave, y por eso se puede listar una zona entera sin que exista ningún directorio.

| zona | qué guarda | formato |
|---|---|---|
| `raw` | lo que llegó de la fuente, sin tocar | CSV como viene |
| `curated` | las 7 features y la etiqueta, listas para entrenar | Parquet |
| `models` | el artefacto del modelo, bajo su versión | pickle de joblib |

Separarlas es lo que evita el pantano: quien entrena sabe cuál es el dato confiable sin adivinar. Y conservar el crudo permite reprocesar si mañana cambia la codificación, en vez de volver a pedirle los datos a una fuente que quizás ya no los tenga.

## La zona raw: dos fuentes con cadencias distintas

```
raw/crimes/dia=2026-10-03/crimes.csv      ← se agrega una partición por día
raw/police_stations/police_stations.csv   ← se reemplaza entero
```

Los reportes de crímenes se publican a diario, con siete días de retraso. Las comisarías son 23 filas que no cambian desde 2016. Particionar los reportes por día hace barato leer solo un día; particionar las comisarías sería ruido.

Si el portal no responde —sin red, sin token o con el límite de uso agotado— se usa una copia versionada en `data/`: 2.000 reportes y las 23 comisarías. Un pipeline que solo funciona con internet no se puede corregir en la máquina de otro. Cuando cae al respaldo lo informa en la salida y lo escribe en el log con la traza, porque un respaldo silencioso esconde que la fuente dejó de responder.

El token de Socrata no es obligatorio para leer, pero sin él el portal agrupa el límite de uso por dirección IP. Se saca gratis en [la configuración de desarrollador](https://data.cityofchicago.org/profile/edit/developer_settings) y se pone en el `.env`, que no se versiona.

## La zona curated: Parquet y no CSV

El mismo dataset ocupa 2656 KB en CSV y 765 KB en Parquet: 3.5 veces menos. Además conserva los tipos y permite leer una columna sin recorrer el resto. Hay un test que compara los dos tamaños, para que ese número no sea una creencia.

## Servir desde el lake

El modelo se publica bajo su versión y se carga desde el lake a memoria, sin pasar por disco:

```
models/v1/model.pkl
models/v2/model.pkl   ← conviven; volver atrás es apuntar a la otra
```

El test que sostiene todo esto: las predicciones del modelo bajado del lake coinciden exactamente con las del `.pkl` local, verificado sobre 200 reportes. Si difirieran, algo se habría corrompido en el viaje.

Pedir una versión que no existe devuelve un error que dice cuál falta, en vez del error opaco de `boto3`.

## MLflow con los artefactos en el lake

MLflow parte el problema en dos: la metadata de la corrida —parámetros, métricas, etiquetas— va a PostgreSQL, y los artefactos pesados van al lake, porque el servidor se levanta con `--default-artifact-root s3://mlflow/`.

El bucket queda ordenado por experimento y corrida:

```
mlflow/1/3496d0b96fc948949ce0e7d3d737ced5/artifacts/model.pkl
```

El cliente sube el artefacto él mismo, así que necesita el endpoint y las credenciales de MinIO; el módulo las fija al importarse. Se usa `mlflow-skinny`, que es el cliente sin el servidor: unos pocos MB en vez de los cientos del paquete completo.

## Reflexión

Con el modelo en el lake, publicar una versión nueva es subir un objeto en vez de reconstruir y redesplegar las tres imágenes que hoy lo llevan adentro. El desarrollo está en la sección de reflexión del notebook.

## El notebook

[`mini_tp6_actividad.ipynb`](mini_tp6_actividad.ipynb) es el starter de la cátedra completado, y se entrega ejecutado con sus salidas. Los `.py` de esta carpeta son la fuente y están cubiertos por tests; el notebook los importa y los muestra.

```bash
uv run jupyter nbconvert --to notebook --execute --inplace tp6_datalake/mini_tp6_actividad.ipynb
```

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `lake.py` | el cliente S3 contra MinIO: bucket, zonas, subir, bajar y listar |
| `ingest.py` | la descarga de Socrata con respaldo versionado, y el aterrizaje en `raw` |
| `curated.py` | el dataset procesado escrito en Parquet |
| `models.py` | publicar el modelo versionado y cargarlo desde el lake |
| `tracking.py` | la corrida en MLflow con los artefactos en el lake |
| `run.py` | el comando que recorre todo |

Los tests que necesitan MinIO llevan el marcador `minio` y los de MLflow el marcador `mlflow`; se saltean solos si esos servicios no están levantados.
