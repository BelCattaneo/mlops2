# Mini-TPs · Operaciones de Aprendizaje Automático II (CEIA-FIUBA)

Modelo propio de Aprendizaje de Máquina: predicción de arrestos en crímenes reportados en Chicago (2024) con XGBoost ([TP-final](https://github.com/CEIA-22Co2025-Grupo4/TP-final)), servido por tres protocolos distintos.

Los tres mini-TPs comparten el paquete `arrest_model/` y el mismo `model/model.pkl`: lo que cambia es el protocolo, no el modelo ni la codificación. Cada uno tiene su propia presentación:

| Mini-TP | Tema | Detalle | Estado |
|---|---|---|---|
| 1 | API REST con FastAPI | [`tp1_rest/README.md`](tp1_rest/README.md) | Listo |
| 2 | Metadatos por GraphQL + linaje en Neo4j | [`tp2_graphql/README.md`](tp2_graphql/README.md) | Listo, falta la reflexión |
| 3 | Scoring por gRPC | [`tp3_grpc/README.md`](tp3_grpc/README.md) | Listo |

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/), Docker y `make`.

```bash
make install   # uv sync
make test      # pytest
make lint      # ruff check + ruff format --check
make help      # lista completa de comandos
```

Para levantar y probar cada servicio, ver el README del mini-TP correspondiente.

## Estructura

```
├── Makefile         # atajos globales (install, test, lint) y por servicio (rest-*, grpc-*)
├── model/           # model.pkl: modelo entrenado + parámetros de codificación
├── arrest_model/    # paquete compartido: contrato del payload, codificación y predicción
├── tp1_rest/        # Mini-TP 1: API REST (app.py, client.py, Dockerfile, README.md)
├── tp2_graphql/     # Mini-TP 2: GraphQL (schema.py, app.py, client.py, compare.py, lineage.py, README.md)
├── tp3_grpc/        # Mini-TP 3: gRPC (scoring.proto, server.py, client.py, benchmark.py, README.md)
└── tests/           # tests + data/encoding_cases.csv (filas de referencia del TP-final)
```

## El paquete compartido `arrest_model/`

| módulo | qué tiene |
|---|---|
| `schemas.py` | el contrato: `CrimeReport` (los 6 campos crudos) y las respuestas de las APIs |
| `features.py` | la codificación: una función por feature, registradas en `ENCODERS` |
| `model.py` | `load_bundle()` para leer el `.pkl` y `predict()` para predecir un lote |

Ningún servicio reimplementa la codificación ni el formato de la respuesta: todos usan este paquete.

## Modelo (`model/model.pkl`)

Un único archivo `joblib` con el `XGBClassifier()` entrenado sobre los datasets finales del TP-final y los parámetros necesarios para codificar los datos crudos (frecuencias de train, media y desvío de las coordenadas y ubicación de las comisarías). Las APIs solo lo cargan: nada en este repo necesita los datasets originales.

El modelo se genera aparte, fuera del alcance de los mini-TPs, con un script que entrena, verifica la codificación contra las 50.744 filas de test del TP-final y controla las métricas antes de guardar:

```bash
uv run --project . python ../prep/train_model.py \
    --data-dir ~/Documents/CEIA/TP-final/datasets
```

### La codificación

Está en `arrest_model/features.py`, con una función por feature registrada en `ENCODERS`, que además fija el orden con el que se entrenó el modelo.

| campo crudo | feature | transformación |
|---|---|---|
| `iucr` | `IUCR_freq` | frecuencia en train; 0 si no apareció |
| `primary_type` | `Primary_Type_freq` | frecuencia en train |
| `location_description` | `Location_Description_freq` | frecuencia en train; vacío → `UNKNOWN` |
| `date` | `Day_sin` | día de la semana (domingo=1) → `sin(2π·d/7)` |
| `latitude`, `longitude` | `X/Y Coordinate_standardized` | proyección a EPSG:3435 → z-score |
| `latitude`, `longitude` | `Distance Crime To Police Station_standardized` | comisaría más cercana (EPSG:26971) → `log1p` → z-score |

## Tests

```bash
make test
```

Además de los tests de cada servicio, la codificación se verifica contra 50 filas reales de `final_test.csv` (`tests/data/encoding_cases.csv`): tienen que dar las mismas features y la misma clase predicha que en el TP-final.
