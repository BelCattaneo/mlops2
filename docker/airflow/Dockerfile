FROM apache/airflow:3.0.2
COPY requirements.txt /requirements.txt

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         git \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /requirements.txt

RUN pip install --upgrade pip

# Los providers de Google y Snowflake vienen en la imagen base y declaran `pandas>=2.1.2,<2.2`
# como dependencia OBLIGATORIA. Ese techo cascadea —pandas 2.1 pide `numpy<2`, y scipy y
# geopandas actuales piden `numpy>=2`— y deja el stack numérico del contenedor desalineado del
# repo, lo que cambia el resultado del balanceo del dataset de entrenamiento.
#
# No los usa nadie: el DAG habla con MinIO por boto3 y con Socrata por HTTP, ningún paquete los
# pide salvo detrás de un `extra`, y la base no tiene conexiones de esos tipos. Si alguna vez
# hicieran falta, se vuelven a instalar y se revisa el techo.
RUN pip uninstall -y apache-airflow-providers-google apache-airflow-providers-snowflake
RUN pip install --no-cache-dir apache-airflow[virtualenv]==3.0.2 -r /requirements.txt
