# Mini-TPs · Operaciones de Aprendizaje Automático II (CEIA-FIUBA)

Modelo propio de Aprendizaje de Máquina: **predicción de arrestos en crímenes reportados en Chicago (2024)** con XGBoost ([TP-final](https://github.com/CEIA-22Co2025-Grupo4/TP-final)), servido por REST, GraphQL y gRPC.

| Mini-TP | Tema | Carpeta | Estado |
|---|---|---|---|
| 1 | API REST con FastAPI | [`tp1_rest/`](tp1_rest/) | En progreso |
| 2 | Metadatos por GraphQL + linaje en Neo4j | [`tp2_graphql/`](tp2_graphql/) | Pendiente |
| 3 | Scoring por gRPC | [`tp3_grpc/`](tp3_grpc/) | Pendiente |

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/), Docker y `make`.

```bash
make install   # uv sync
make help      # lista de comandos
```

## Estructura

```
├── Makefile         # atajos: install, test, lint, run, build, up, down, logs, health, client
├── data/            # datasets del TP-final (procesado, train, test) y comisarías
├── model/           # model.pkl: modelo entrenado + parámetros de codificación
├── arrest_model/    # paquete compartido: contrato del payload, codificación y predicción
├── tp1_rest/        # Mini-TP 1: API REST (app.py, client.py, Dockerfile)
├── tp2_graphql/     # Mini-TP 2: GraphQL
├── tp3_grpc/        # Mini-TP 3: gRPC
└── tests/           # tests + data/encoding_cases.csv (filas de referencia del TP-final)
```

## Modelo (`model/model.pkl`)

Un único archivo `joblib` con el `XGBClassifier()` entrenado sobre los datasets finales del TP-final y los parámetros necesarios para codificar los datos crudos (frecuencias de train, media y desvío de las coordenadas y ubicación de las comisarías). Se genera aparte, fuera del alcance de los mini-TPs; las APIs solo lo cargan.

La codificación de los 6 campos crudos en las 7 features del modelo está en `arrest_model/features.py` y replica el preprocesamiento del TP-final. Se testea contra 50 filas reales de `final_test.csv` (`tests/data/encoding_cases.csv`): mismas features y misma clase predicha.

## TP1 — REST

> **En progreso.** Hecho: `/health` y `/v1/predict` (payload crudo → codificación → predicción), en local y en Docker. Falta: validaciones de entrada, lote, metadata y manejo de errores.

API FastAPI que carga `model/model.pkl` una sola vez al arrancar.

| comando | qué hace |
|---|---|
| `make run` | levanta la API local con uvicorn en el puerto 8000 (docs en `/docs`) |
| `make up` | construye la imagen, levanta el contenedor y espera a que responda `/health` |
| `make health` | consulta `GET /health` |
| `make client` | corre el cliente de prueba (`tp1_rest/client.py`): `/health`, un payload válido (200) y uno sin fecha (422), contra la API levantada con `make run` o `make up` |
| `make logs` | muestra los logs del contenedor |
| `make down` | detiene el contenedor |
| `make test` · `make lint` | tests y ruff |

Sin `make`:

```bash
uv run uvicorn tp1_rest.app:app --port 8000
docker build -f tp1_rest/Dockerfile -t arrest-rest .
docker run --rm -p 8000:8000 arrest-rest
uv run python tp1_rest/client.py
```

| endpoint | respuesta |
|---|---|
| `GET /health` | 200 `{"status": "ok", "model_name": "chicago-arrest-xgboost", "model_version": 1}`; 503 `{"status": "unavailable", "detail": "..."}` si no se pudo cargar `model/model.pkl` |
| `POST /v1/predict` | recibe los 6 campos crudos y devuelve `{"arrest", "probability", "model_name", "model_version"}`; 422 si falta un campo; 503 si no hay modelo |

Ejemplo con la primera fila de `Crimes_Chicago_2024.csv`:

```bash
curl -X POST http://127.0.0.1:8000/v1/predict -H "Content-Type: application/json" -d '{
  "iucr": "1310", "primary_type": "CRIMINAL DAMAGE", "location_description": "APARTMENT",
  "date": "2024-12-31T23:58:00", "latitude": 41.771470188, "longitude": -87.59074212
}'
```

```json
{"arrest": 0, "probability": 0.06843266636133194, "model_name": "chicago-arrest-xgboost", "model_version": 1}
```

## TP2 — GraphQL

_Pendiente._

## TP3 — gRPC

_Pendiente._
