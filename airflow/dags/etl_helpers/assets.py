"""Lo que el ETL publica cuando deja una partición curada nueva.

Es el único acople entre el ETL y el entrenamiento: declarada como asset, la capa curada pasa a
ser el disparador de la corrida de entrenamiento, así que entrenar depende de que el dato esté
en el lake y no de un calendario que haya que mantener en fase con el del ETL.

Vive en el paquete de helpers, que es donde está el código que los DAGs comparten, y figura en
el `.airflowignore`: Airflow abre buscando DAGs todo archivo que nombre a "airflow" y a "dag",
y al abrir este le daría al `sys.path` su propia carpeta en vez de la de los DAGs, así que
importar `etl_config` fallaría y el error quedaría colgado en la interfaz.
"""

from airflow.sdk import Asset
from etl_config import BUCKET_NAME, config

CURATED_LAYER = Asset(
    uri=f"s3://{BUCKET_NAME}/{config.PREFIX_CURATED}",
    name="chicago-curated-layer",
)
