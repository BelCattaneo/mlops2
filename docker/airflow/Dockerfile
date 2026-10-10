# La variante `slim` de la imagen oficial: trae Airflow y cinco providers —`common-compat`,
# `common-io`, `common-sql`, `smtp` y `standard`— en vez de los treinta y pico que trae la normal.
# `standard` es el que necesitan los decoradores `@dag` y `@task`, que es todo lo que los DAGs
# importan de Airflow. Medido: la normal deja 338 MB de Google (`google` más `googleapiclient`),
# 80 MB de Azure y 71 MB de MySQL que nadie usa, y desinstalar los providers no los saca porque
# `pip uninstall` no toca las dependencias del paquete.
#
# De paso desaparece el problema que obligaba a desinstalar los providers de Google y Snowflake:
# declaraban `pandas>=2.1.2,<2.2` como dependencia obligatoria, y ese techo cascadeaba —pandas
# 2.1 pide `numpy<2`, y scipy y geopandas actuales piden `numpy>=2`— dejando el stack numérico
# del contenedor desalineado del repo, lo que cambia el resultado del balanceo del dataset.
FROM apache/airflow:slim-3.0.2
COPY requirements.txt /requirements.txt

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         git \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --upgrade pip

# Lo que la slim no trae y la plataforma sí necesita, pinneado a la versión de Airflow:
#   - `virtualenv`, para las tareas que corren en un intérprete aparte;
#   - el extra `postgres`, que trae los dos drivers de la base de metadata. Hacen falta los dos:
#     `psycopg2` para el engine sincrónico y `asyncpg` para el asincrónico, que es el que usa el
#     scheduler. Medido: con solo `psycopg2`, cualquier comando falla con
#     `ModuleNotFoundError: No module named 'asyncpg'` antes de llegar a la base;
#   - el provider `fab`, porque el compose configura `FabAuthManager` como auth manager.
RUN pip install --no-cache-dir \
      "apache-airflow[virtualenv,postgres]==3.0.2" \
      "apache-airflow-providers-fab==2.2.1" \
      -r /requirements.txt
