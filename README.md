# Mini-TPs · Operaciones de Aprendizaje Automático II (CEIA-FIUBA)

Modelo propio de Aprendizaje de Máquina: **predicción de arrestos en crímenes reportados en Chicago (2024)** con XGBoost ([TP-final](https://github.com/CEIA-22Co2025-Grupo4/TP-final)), servido por REST, GraphQL y gRPC.

| Mini-TP | Tema | Carpeta | Estado |
|---|---|---|---|
| 1 | API REST con FastAPI | [`tp1_rest/`](tp1_rest/) | Pendiente |
| 2 | Metadatos por GraphQL + linaje en Neo4j | [`tp2_graphql/`](tp2_graphql/) | Pendiente |
| 3 | Scoring por gRPC | [`tp3_grpc/`](tp3_grpc/) | Pendiente |

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/) y Docker (para Neo4j y la imagen del TP1).

```bash
uv sync
```

## Estructura

```
├── data/            # datasets del TP-final (procesado, train, test) y comisarías
├── model/           # entrenamiento y artefactos del modelo
├── arrest_model/    # paquete compartido: contrato y carga del modelo
├── tp1_rest/        # Mini-TP 1: REST
├── tp2_graphql/     # Mini-TP 2: GraphQL
├── tp3_grpc/        # Mini-TP 3: gRPC
└── tests/
```

## TP1 — REST

_Pendiente._

## TP2 — GraphQL

_Pendiente._

## TP3 — gRPC

_Pendiente._
