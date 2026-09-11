# Atajos del Mini-TP 1. `make help` lista los comandos.
IMAGE := arrest-rest
CONTAINER := arrest-rest
PORT := 8000

.PHONY: help install test lint run build up down logs health client

help: ## Muestra los comandos disponibles
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-8s %s\n", $$1, $$2}'

install: ## Instala las dependencias con uv
	uv sync

test: ## Corre los tests
	uv run pytest

lint: ## Revisa estilo y formato con ruff
	uv run ruff check arrest_model tp1_rest tests
	uv run ruff format --check arrest_model tp1_rest tests

run: ## Levanta la API local con uvicorn (recarga al guardar)
	uv run uvicorn tp1_rest.app:app --reload --port $(PORT)

build: ## Construye la imagen Docker
	docker build -f tp1_rest/Dockerfile -t $(IMAGE) .

up: build ## Levanta el contenedor y espera a que responda /health
	@docker rm -f $(CONTAINER) > /dev/null 2>&1 || true
	docker run -d --rm -p $(PORT):8000 --name $(CONTAINER) $(IMAGE)
	@curl -s --retry 45 --retry-all-errors --retry-delay 2 --max-time 5 http://127.0.0.1:$(PORT)/health && echo

down: ## Detiene el contenedor
	docker stop $(CONTAINER)

logs: ## Muestra los logs del contenedor
	docker logs -f $(CONTAINER)

health: ## Consulta GET /health
	@curl -s http://127.0.0.1:$(PORT)/health && echo

client: ## Prueba la API con el cliente (con make run o make up corriendo)
	uv run python tp1_rest/client.py --url http://127.0.0.1:$(PORT)
