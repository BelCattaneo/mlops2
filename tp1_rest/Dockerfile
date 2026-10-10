# Mini-TP 1. Build desde la raíz del repo: docker build -f tp1_rest/Dockerfile -t arrest-rest .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONPATH=/app

# Dependencias base + el grupo propio + `serving`, con las versiones exactas de uv.lock.
# `serving` es lo que hace falta para traer el champion del registro cuando corre dentro de
# la plataforma; sin `MODEL_URI` en el entorno, la imagen sirve el .pkl de abajo igual que antes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group rest --group serving --no-install-project

COPY arrest_model ./arrest_model
COPY tp1_rest ./tp1_rest
COPY model/model.pkl ./model/model.pkl

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "tp1_rest.app:app", "--host", "0.0.0.0", "--port", "8000"]
