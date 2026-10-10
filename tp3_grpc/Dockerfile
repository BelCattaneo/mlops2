# Mini-TP 3. Build desde la raíz del repo: docker build -f tp3_grpc/Dockerfile -t arrest-grpc .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONPATH=/app

# Dependencias base + el grupo propio + `serving`, con las versiones exactas de uv.lock.
# `serving` es lo que hace falta para traer el champion del registro cuando corre dentro de
# la plataforma; sin `MODEL_URI` en el entorno, la imagen sirve el .pkl de abajo igual que antes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group grpc --group serving --no-install-project

COPY arrest_model ./arrest_model
COPY tp3_grpc ./tp3_grpc
COPY model/model.pkl ./model/model.pkl

EXPOSE 50051
CMD ["/app/.venv/bin/python", "-m", "tp3_grpc.server"]
