FROM python:3.12-slim

COPY requirements.txt /requirements.txt

# `wget` es para el healthcheck del compose, que es lo único que la imagen necesita de apt. Las
# listas se borran en la misma capa: dejarlas ahí son 21 MB que viajan en cada pull.
RUN apt-get update \
  && apt-get install -y --no-install-recommends wget \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Sin `[extras]`: medido adentro de la imagen, traía 142 MB de `azure`, 55 MB de `azureml` y
# 119 MB de `kubernetes` para una plataforma que guarda en MinIO y no despliega en Kubernetes.
# El servidor necesita el paquete completo —no `mlflow-skinny`— porque sirve la interfaz.
#
# `--no-cache-dir` en las dos instalaciones: la caché de pip son 237 MB medidos que quedaban
# adentro de la imagen sin que nadie los vuelva a usar.
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir mlflow==3.16.1 \
  && pip install --no-cache-dir -r /requirements.txt

EXPOSE 5000