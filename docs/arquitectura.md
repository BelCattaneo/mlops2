# Arquitectura del TP integrador

Plataforma de predicción en tiempo real de "ML Models & Something More Inc." que sirve el modelo XGBoost de arrestos en Chicago (2024). Nivel en contenedores.

Parte de la infraestructura del TP final de MLOps I y le aplica encima los conceptos de la materia. Lo que sigue es qué cambió y por qué.

Equipo: trabajo individual. Bel Cattaneo cubre diseño, implementación y documentación.

Se levanta con `make stack-up`; el detalle está en [cómo levantarla](plataforma.md).

![Arquitectura de la plataforma por capas](arquitectura.png)

Los diagramas se generan desde `arquitectura.mmd` y `arquitectura-mlops1.mmd` con `make diagramas`.

## De dónde se parte

La infraestructura viene del TP final de MLOps I, y vale la pena ver las dos arquitecturas juntas porque la diferencia no está en la cantidad de servicios.

![Arquitectura del TP final de MLOps I](arquitectura-mlops1.png)

| | MLOps I | MLOps II |
|---|---|---|
| ejecutor de Airflow | Celery, con worker y ValKey de broker | LocalExecutor: las tareas corren en el proceso del scheduler |
| el pipeline | un DAG de 11 tareas, una por etapa | un DAG de 5 tareas, una por capa |
| lo que deja en el lake | el dataset entero entre paso y paso, en 9 prefijos numerados de `0-raw-data/` a `ml-ready-data/`: 13 objetos y 348,95 MB de CSV por corrida | tres capas con nombres de dominio y retención propia: 3 objetos y 10,42 MB de Parquet por corrida |
| la ventana móvil | `merge_data` releía el último archivo mergeado y le concatenaba el mes nuevo | la determinan qué particiones mensuales caen en los últimos 365 días |
| el entrenamiento | un servicio `trainer` aparte | un DAG propio, acoplado al ETL solo por la capa curada |
| de dónde sale el modelo que se sirve | del artefacto que dejó el entrenamiento | del Model Registry, por el alias `champion` |
| los parámetros de preprocesamiento | quedaban del lado del pipeline | viajan dentro del artefacto del modelo |
| el umbral de decisión | un `0.5` escrito en el código | lo elige el entrenamiento sobre validación y viaja con el modelo |
| protocolos de servicio | una API REST | REST para los clientes, gRPC para la inferencia interna y GraphQL para los metadatos y el linaje |
| el resumen de la corrida | bajaba 7 datasets de S3 para contar filas | los conteos viajan por XCom |

La diferencia de fondo es que en MLOps I el pipeline era una cadena de archivos, donde cada etapa dependía de que la anterior hubiera dejado el suyo en el lugar justo. Ahora es un contrato: el ETL publica una capa curada que cumple el contrato de features de `arrest_model`, y el entrenamiento la consume sin saber quién la escribió.

## Decisiones de arquitectura

### Un solo protocolo de servicio, y es REST

> Decidido el 2026-10-12 y todavía sin ejecutar: el compose y el diagrama de arriba siguen
> mostrando los tres servicios. Esta nota se va cuando se saquen.

La plataforma sirve el modelo por REST. No porque REST sea mejor en abstracto —medimos que gRPC es más rápido— sino porque a la carga de este problema esa ventaja no compra nada.

**El volumen.** El portal publica 633 reportes por día. Eso es 26,4 por hora, 0,44 por minuto, uno cada 136 segundos: 0,007 predicciones por segundo. Con la mediana medida de una llamada REST dockerizada —4,94 ms con keep-alive— el servicio estaría ocupado el 0,0036% del tiempo.

**Lo que gRPC ahorraría.** Dockerizado y reusando el canal, gRPC responde en 2,81 ms contra los 4,94 de REST: 2,13 ms por llamada, 1,76x. A 633 llamadas por día eso son **1,35 segundos por día**, 8 minutos por año. El costo de obtenerlos es un servicio más en el compose, una imagen más que mantener, un `.proto` que versionar y un puerto más que asegurar.

**Y la forma de la carga no es de a uno.** Los reportes llegan en lote, con 12 días de atraso del portal, así que lo que la plataforma hace es puntuar conjuntos y no eventos sueltos. Ahí la comparación se da vuelta: el lote de 100 por REST tarda 6,92 ms y el mismo lote por `PredictStream` de gRPC, 13,46 ms. **REST le gana a gRPC por 1,95x en las seis corridas medidas.**

Las mediciones están en [`tp3_grpc/latencias.md`](../tp3_grpc/latencias.md), con cuatro cohortes medidas tres veces cada una.

### GraphQL tampoco entra

Su ventaja medida es traer solo los campos pedidos: 89 bytes contra 557 de REST para la misma consulta de metadatos. Es real, y es irrelevante acá: son metadatos que se consultan de vez en cuando, y 468 bytes no pagan un contenedor, una imagen y un puerto más.

Lo único que GraphQL aportaba y nadie más tenía era el linaje del modelo, que es gobernanza y hay que conservar. Se conserva en Neo4j, que la plataforma mantiene por su cuenta: el pipeline escribe el grafo mientras corre y se consulta en su propia interfaz, que para seguir aristas hacia atrás es mejor herramienta que un endpoint que devuelve una lista plana. El consumidor del linaje es una persona auditando, no una aplicación en un bucle.

### Por qué esto no contradice los mini-TPs

Los mini-TPs comparan REST, GraphQL y gRPC sobre el mismo modelo: ese es su objetivo y ahí la comparación tiene sentido. La plataforma no compara, sirve. Tiene un tipo de consumidor, así que tiene un protocolo.

Sobredimensionar la arquitectura tiene un costo que no se ve en un diagrama: cada servicio de más es una imagen que reconstruir, una superficie que asegurar y una versión que mantener alineada con el paquete compartido.

## Capas

| capa | componentes | qué hace |
|---|---|---|
| Ingesta y orquestación | Airflow | el DAG de ETL baja los reportes de Socrata y los procesa |
| Data lake | MinIO | guarda los datasets en tres capas —`raw`, `enriched` y `curated` de `s3://data`— y los artefactos de modelos (`s3://mlflow`) |
| Entrenamiento y ciclo de vida | Airflow, MLflow, PostgreSQL | el DAG `train_arrest_model` entrena sobre la capa curada y registra el modelo con el alias `champion` |
| Servicio | REST, gRPC, GraphQL con Neo4j | predicciones y metadatos del modelo `champion`, que trae su propia codificación adentro y recibe los campos crudos |

## Qué concepto de la materia aplica cada decisión

| sesión | el concepto | cómo lo aplica la plataforma |
|---|---|---|
| S1 · Del modelo al servicio | predicción online en contenedores, contrato validado, versionado de API y de modelo, qué monitorear | el payload se valida antes de llegar al modelo; la versión servida sale del registro y viaja en cada respuesta; `/health` distingue "el proceso está arriba" de "hay modelo cargado" |
| S2 · Grafos de linaje | el linaje dato → feature → modelo como grafo, para trazabilidad y auditoría | Neo4j en el perfil `lineage`, consultable desde el servicio de metadatos junto con la versión y las métricas del modelo |
| S3 · gRPC | contrato tipado y binario para la inferencia interna de baja latencia | el servicio gRPC del compose, con el modelo cargado una sola vez al arrancar |
| S4 · Streaming | inferencia online sobre un flujo, features por ventana, monitoreo continuo | no se incorporó a la plataforma: el pipeline es mensual y la inferencia, a pedido |
| S5 · Aprendizaje federado | mover el cómputo al dato, agregar solo parámetros | no se incorporó: los datos del portal de Chicago son públicos y están centralizados, así que no hay dilema del dato que resolver |
| S6 · Nube y data lake | zonas del lake, *schema-on-read*, Parquet en lo curado, un solo origen de verdad | las tres capas de `s3://data` con retención propia y el bucket versionado; el lake es lo único que acopla el ETL con el entrenamiento |
| S7 · Seguridad y gobernanza | autenticación, cifrado, auditoría | pendiente, el material de la sesión no está publicado. Lo que ya hay: secretos solo en `.env`, el bucket versionado con retención por capa, y el grafo de linaje |

## Hoja de ruta

| hito | fecha | qué se presenta |
|---|---|---|
| Hito #1 · arquitectura | 17/09 | este documento |
| Hito #2 · checkpoint | 01/10 | la infraestructura de MLOps I levantada con los tres servicios y la capa de streaming |
| Defensa | 15/10 | la plataforma completa y la presentación |
| Repositorio final | 22/10 | el repo y las slides |

## Créditos

La infraestructura parte del [TP final de MLOps I](https://github.com/CEIA-22Co2025-Grupo4/MLOPS) del grupo CEIA-22Co2025-Grupo4, basado en [amq2-service-ml](https://github.com/facundolucianna/amq2-service-ml) de la cátedra.
