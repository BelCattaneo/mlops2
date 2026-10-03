# Atajos del repo. `make help` lista los comandos.
# Los globales van sin prefijo; los de cada TP llevan el suyo: rest-, graphql-, grpc-, stream-,
# fed- y lake-.
REST_IMAGE := arrest-rest
REST_CONTAINER := arrest-rest
REST_PORT := 8000
GRAPHQL_IMAGE := arrest-graphql
GRAPHQL_CONTAINER := arrest-graphql
GRAPHQL_PORT := 8010
GRPC_IMAGE := arrest-grpc
GRPC_CONTAINER := arrest-grpc
GRPC_PORT := 50051
NEO4J_CONTAINER := neo4j-tp
REDPANDA_CONTAINER := redpanda-tp
# La red que comparten Neo4j y la API GraphQL: adentro de ella se encuentran por nombre.
DOCKER_NETWORK := arrest-net

.PHONY: help install test lint docker-network
.PHONY: rest-run rest-build rest-up rest-down rest-logs rest-health rest-client
.PHONY: graphql-run graphql-build graphql-up graphql-down graphql-logs graphql-client
.PHONY: graphql-compare graphql-seed neo4j-up neo4j-down
.PHONY: grpc-stubs grpc-run grpc-build grpc-up grpc-down grpc-logs grpc-client grpc-bench
.PHONY: stream-run stream-compare stream-kafka redpanda-up redpanda-down fed-run lake-run

help: ## Muestra los comandos disponibles
	@grep -E '^[a-z][a-z0-9-]*:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-16s %s\n", $$1, $$2}'

install: ## Instala las dependencias con uv
	uv sync

test: ## Corre los tests
	uv run pytest

lint: ## Revisa estilo y formato con ruff
	uv run ruff check arrest_model tp1_rest tp2_graphql tp3_grpc tp4_streaming tp5_federated tp6_datalake tests
	uv run ruff format --check arrest_model tp1_rest tp2_graphql tp3_grpc tp4_streaming tp5_federated tp6_datalake tests

# Sin `##` a propósito: es un paso interno de neo4j-up y graphql-up, no un comando para correr solo.
docker-network:
	@docker network inspect $(DOCKER_NETWORK) > /dev/null 2>&1 || docker network create $(DOCKER_NETWORK) > /dev/null

rest-run: ## TP1 · levanta la API local con uvicorn (recarga al guardar)
	uv run uvicorn tp1_rest.app:app --reload --port $(REST_PORT)

rest-build: ## TP1 · construye la imagen Docker
	docker build -f tp1_rest/Dockerfile -t $(REST_IMAGE) .

rest-up: rest-build ## TP1 · levanta el contenedor y espera a que responda /health
	@docker rm -f $(REST_CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm -p $(REST_PORT):8000 --name $(REST_CONTAINER) $(REST_IMAGE)
	@curl -s --retry 45 --retry-all-errors --retry-delay 2 --max-time 5 http://127.0.0.1:$(REST_PORT)/health && echo

rest-down: ## TP1 · detiene el contenedor
	docker stop $(REST_CONTAINER)

rest-logs: ## TP1 · muestra los logs del contenedor
	docker logs -f $(REST_CONTAINER)

rest-health: ## TP1 · consulta GET /health
	@curl -s http://127.0.0.1:$(REST_PORT)/health && echo

rest-client: ## TP1 · prueba la API con el cliente (con rest-run o rest-up corriendo)
	uv run python tp1_rest/client.py --url http://127.0.0.1:$(REST_PORT)

graphql-run: ## TP2 · levanta la API GraphQL local (GraphiQL en /graphql)
	uv run uvicorn tp2_graphql.app:app --port $(GRAPHQL_PORT)

graphql-build: ## TP2 · construye la imagen Docker
	docker build -f tp2_graphql/Dockerfile -t $(GRAPHQL_IMAGE) .

graphql-up: graphql-build docker-network ## TP2 · levanta el contenedor en la red de Neo4j y espera a que responda
	@docker rm -f $(GRAPHQL_CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm -p $(GRAPHQL_PORT):8010 --name $(GRAPHQL_CONTAINER) --network $(DOCKER_NETWORK) \
		-e NEO4J_URI=bolt://$(NEO4J_CONTAINER):7687 $(GRAPHQL_IMAGE)
	@curl -s -o /dev/null --retry 45 --retry-all-errors --retry-delay 2 --max-time 5 -H 'Accept: text/html' \
		http://127.0.0.1:$(GRAPHQL_PORT)/graphql && echo "GraphQL listo en http://127.0.0.1:$(GRAPHQL_PORT)/graphql"

graphql-down: ## TP2 · detiene el contenedor
	docker stop $(GRAPHQL_CONTAINER)

graphql-logs: ## TP2 · muestra los logs del contenedor
	docker logs -f $(GRAPHQL_CONTAINER)

graphql-client: ## TP2 · prueba la API GraphQL con el cliente (con graphql-run o graphql-up corriendo)
	uv run python -m tp2_graphql.client --url http://127.0.0.1:$(GRAPHQL_PORT)/graphql

graphql-compare: ## TP2 · compara la misma lectura por REST y por GraphQL (las dos APIs arriba)
	uv run python -m tp2_graphql.compare \
		--rest-url http://127.0.0.1:$(REST_PORT) \
		--graphql-url http://127.0.0.1:$(GRAPHQL_PORT)/graphql

graphql-seed: ## TP2 · siembra el linaje del modelo en Neo4j (espera a que acepte conexiones)
	uv run python -m tp2_graphql.lineage

neo4j-up: docker-network ## TP2 · levanta Neo4j en Docker (UI en 7474, driver bolt en 7687)
	@docker rm -f $(NEO4J_CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm --name $(NEO4J_CONTAINER) --network $(DOCKER_NETWORK) -p 7474:7474 -p 7687:7687 \
		-e NEO4J_AUTH=neo4j/testpass neo4j:latest

neo4j-down: ## TP2 · detiene Neo4j
	docker stop $(NEO4J_CONTAINER)

grpc-stubs: ## TP3 · regenera los stubs de gRPC desde scoring.proto
	uv run python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. tp3_grpc/scoring.proto

grpc-run: ## TP3 · levanta el servidor gRPC local en el puerto 50051
	uv run python -m tp3_grpc.server

grpc-build: ## TP3 · construye la imagen Docker
	docker build -f tp3_grpc/Dockerfile -t $(GRPC_IMAGE) .

grpc-up: grpc-build ## TP3 · levanta el contenedor y espera a que acepte conexiones
	@docker rm -f $(GRPC_CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm -p $(GRPC_PORT):50051 --name $(GRPC_CONTAINER) $(GRPC_IMAGE)
	@uv run python -c "import grpc; grpc.channel_ready_future(grpc.insecure_channel('127.0.0.1:$(GRPC_PORT)')).result(timeout=60); print('gRPC listo en 127.0.0.1:$(GRPC_PORT)')"

grpc-down: ## TP3 · detiene el contenedor
	docker stop $(GRPC_CONTAINER)

grpc-logs: ## TP3 · muestra los logs del contenedor
	docker logs -f $(GRPC_CONTAINER)

grpc-client: ## TP3 · prueba el servicio con el cliente (con grpc-run o grpc-up corriendo)
	uv run python -m tp3_grpc.client --target 127.0.0.1:$(GRPC_PORT)

grpc-bench: ## TP3 · compara latencia gRPC vs REST (los dos arriba y del mismo lado)
	uv run python -m tp3_grpc.benchmark --rest-url http://127.0.0.1:$(REST_PORT) \
		--grpc-target 127.0.0.1:$(GRPC_PORT)

stream-run: ## TP4 · puntúa un flujo de reportes evento por evento, con drift a la mitad
	uv run python -m tp4_streaming.run --drift-from 200

stream-compare: ## TP4 · compara puntuar el flujo de a uno contra puntuarlo en lote
	uv run python -m tp4_streaming.compare

stream-kafka: ## TP4 · corre el mismo flujo contra Redpanda (con redpanda-up levantado)
	uv run python -m tp4_streaming.run --drift-from 200 --source kafka

redpanda-up: ## TP4 · levanta Redpanda en Docker (API de Kafka en 9092)
	@docker rm -f $(REDPANDA_CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm --name $(REDPANDA_CONTAINER) -p 9092:9092 redpandadata/redpanda \
		redpanda start --overprovisioned --smp 1 --check=false
	@uv run python -c "import socket, time; [time.sleep(1) for _ in range(30) if socket.socket().connect_ex(('127.0.0.1', 9092))]; print('Redpanda listo en 127.0.0.1:9092')"

redpanda-down: ## TP4 · detiene Redpanda
	docker stop $(REDPANDA_CONTAINER)

fed-run: ## TP5 · compara el modelo federado contra el centralizado y mide el costo del ruido
	uv run python -m tp5_federated.run

lake-run: ## TP6 · sube datos y modelo al data lake y sirve el modelo desde ahí
	uv run python -m tp6_datalake.run
