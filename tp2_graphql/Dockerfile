# Mini-TP 2. Build desde la raíz del repo: docker build -f tp2_graphql/Dockerfile -t arrest-graphql .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONPATH=/app

# Solo dependencias base + grupo graphql, con las versiones exactas de uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group graphql --no-install-project

COPY arrest_model ./arrest_model
COPY tp2_graphql ./tp2_graphql
COPY model/model.pkl ./model/model.pkl

# Neo4j no va en esta imagen: corre en su propio contenedor y la dirección llega por NEO4J_URI.
EXPOSE 8010
CMD ["/app/.venv/bin/uvicorn", "tp2_graphql.app:app", "--host", "0.0.0.0", "--port", "8010"]
