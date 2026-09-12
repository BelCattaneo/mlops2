# Atajos del repo. `make help` lista los comandos.
# Los globales van sin prefijo; los de cada servicio se prefijan (rest-, y más adelante grpc-).
REST_IMAGE := arrest-rest
REST_CONTAINER := arrest-rest
REST_PORT := 8000

.PHONY: help install test lint
.PHONY: rest-run rest-build rest-up rest-down rest-logs rest-health rest-client

help: ## Muestra los comandos disponibles
	@grep -E '^[a-z][a-z-]*:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-13s %s\n", $$1, $$2}'

install: ## Instala las dependencias con uv
	uv sync

test: ## Corre los tests
	uv run pytest

lint: ## Revisa estilo y formato con ruff
	uv run ruff check arrest_model tp1_rest tp3_grpc tests
	uv run ruff format --check arrest_model tp1_rest tp3_grpc tests

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

.PHONY: grpc-stubs

grpc-stubs: ## TP3 · regenera los stubs de gRPC desde scoring.proto
	uv run python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. tp3_grpc/scoring.proto
