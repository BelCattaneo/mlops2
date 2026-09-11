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
├── Makefile         # atajos: install, test, lint, run, build, up, down, logs, health
├── data/            # datasets del TP-final (procesado, train, test) y comisarías
├── model/           # model.pkl: modelo entrenado + parámetros de codificación
├── arrest_model/    # paquete compartido: carga del modelo
├── tp1_rest/        # Mini-TP 1: API REST (app.py, Dockerfile)
├── tp2_graphql/     # Mini-TP 2: GraphQL
├── tp3_grpc/        # Mini-TP 3: gRPC
└── tests/
```

## Modelo (`model/model.pkl`)

Un único archivo `joblib` con el `XGBClassifier()` entrenado sobre los datasets finales del TP-final y los parámetros necesarios para codificar los datos crudos (frecuencias de train, media y desvío de las coordenadas y ubicación de las comisarías). Se genera aparte, fuera del alcance de los mini-TPs; las APIs solo lo cargan.

## TP1 — REST

> **En progreso.** Hecho: `/health` en local y en Docker. Falta: `/v1/predict`, validaciones, lote, metadata y cliente.

API FastAPI que carga `model/model.pkl` una sola vez al arrancar.

| comando | qué hace |
|---|---|
| `make run` | levanta la API local con uvicorn en el puerto 8000 (docs en `/docs`) |
| `make up` | construye la imagen, levanta el contenedor y espera a que responda `/health` |
| `make health` | consulta `GET /health` |
| `make client` | corre el cliente de prueba (`tp1_rest/client.py`) contra la API levantada con `make run` o `make up` |
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

## TP2 — GraphQL

_Pendiente._

## TP3 — gRPC

_Pendiente._
