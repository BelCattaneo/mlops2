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

La codificación está en `arrest_model/features.py`: **una función por feature**, registradas en `ENCODERS`, que además fija el orden con el que se entrenó el modelo.

| campo crudo | feature | transformación |
|---|---|---|
| `iucr` | `IUCR_freq` | frecuencia en train; 0 si no apareció |
| `primary_type` | `Primary_Type_freq` | frecuencia en train |
| `location_description` | `Location_Description_freq` | frecuencia en train; vacío → `UNKNOWN` |
| `date` | `Day_sin` | día de la semana (domingo=1) → `sin(2π·d/7)` |
| `latitude`, `longitude` | `X/Y Coordinate_standardized` | proyección a EPSG:3435 → z-score |
| `latitude`, `longitude` | `Distance Crime To Police Station_standardized` | comisaría más cercana (EPSG:26971) → `log1p` → z-score |

Se testea contra 50 filas reales de `final_test.csv` (`tests/data/encoding_cases.csv`): mismas features y misma clase predicha que en el TP-final.

## TP1 — REST

> **En progreso.** Hecho: `/health` y `/v1/predict` con validación del payload, en local y en Docker. Falta: lote, metadata y manejo de errores.

API FastAPI que carga `model/model.pkl` una sola vez al arrancar.

| comando | qué hace |
|---|---|
| `make run` | levanta la API local con uvicorn en el puerto 8000 (docs en `/docs`) |
| `make up` | construye la imagen, levanta el contenedor y espera a que responda `/health` |
| `make health` | consulta `GET /health` |
| `make client` | corre el cliente de prueba (`tp1_rest/client.py`): `/health`, un payload válido (200) y cinco inválidos (422) |
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
| `POST /v1/predict` | recibe los 6 campos crudos y devuelve `{"arrest", "probability", "model_name", "model_version"}`; 422 si el payload no cumple el contrato; 503 si no hay modelo |

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

### Qué valida el contrato

El payload se valida **antes** de llegar al modelo; si no cumple, la API responde 422 con el detalle del campo.

| campo | regla |
|---|---|
| `iucr` | texto de 4 caracteres: 3 dígitos y un dígito o letra (`^[0-9]{3}[0-9A-Z]$`). Un código válido que el modelo no vio se acepta y se codifica con frecuencia 0 |
| `primary_type` | uno de los 31 tipos que aparecen en el train del TP-final |
| `location_description` | opcional; vacío se codifica como `UNKNOWN` |
| `date` | fecha ISO 8601. Sin zona horaria se asume hora de Chicago; con zona se convierte |
| `latitude` · `longitude` | dentro de los límites de Chicago: [41.60, 42.05] y [-87.95, -87.50] |
| cualquier otro campo | se rechaza: el contrato no acepta campos extra |

Los textos se normalizan antes de validar: `" battery "` se acepta como `"BATTERY"`.

## TP2 — GraphQL

_Pendiente._

## TP3 — gRPC

_Pendiente._
