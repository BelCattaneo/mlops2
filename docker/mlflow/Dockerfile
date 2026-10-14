FROM python:3.12-slim

COPY requirements.txt /requirements.txt

# `wget` es para el healthcheck del compose, que es lo único que la imagen necesita de apt. Las
# listas se borran en la misma capa: dejarlas ahí son 21 MB que viajan en cada pull.
RUN apt-get update \
  && apt-get install -y --no-install-recommends wget \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# `--no-cache-dir` en las dos instalaciones: la caché de pip son 237 MB medidos que quedaban
# adentro de la imagen sin que nadie los vuelva a usar.
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir mlflow[extras]==3.16.1 \
  && pip install --no-cache-dir -r /requirements.txt

EXPOSE 5000