"""Las claves que la plataforma escribe en el lake, en un solo lugar.

El layout lo usan los dos DAGs: el ETL escribe y el entrenamiento lee. Armado con f-strings en
cada lugar donde hace falta, cambiarlo obliga a encontrar todas las copias, y la que se olvide
hace que una corrida escriba donde la siguiente no busca.

Además toda clave tiene que caer bajo una de las tres capas, porque la retención se define por
prefijo: una clave fuera de ellas no la alcanza ninguna regla y queda en el bucket para siempre.
"""

from collections.abc import Callable

from etl_config import config


def raw_crimes_prefix() -> str:
    """El prefijo de las particiones mensuales de reportes crudos."""
    return f"{config.PREFIX_RAW}crimes/"


def raw_crimes(month: str) -> str:
    """Los reportes crudos de un mes, como llegaron del portal."""
    return f"{raw_crimes_prefix()}month={month}/crimes.csv"


def raw_stations() -> str:
    """Las comisarías, que no cambian y no se particionan."""
    return f"{config.PREFIX_RAW}police_stations/police_stations.csv"


def enriched_crimes(partition: str) -> str:
    """El dataset limpio y enriquecido de una corrida."""
    return f"{config.PREFIX_ENRICHED}crimes/date={partition}/crimes.parquet"


def curated_prefix(artifact: str) -> str:
    """El prefijo de un artefacto de la capa curada, para listar sus particiones."""
    return f"{config.PREFIX_CURATED}{artifact}/"


def curated_train(partition: str) -> str:
    """El dataset de entrenamiento de una corrida."""
    return f"{curated_prefix('train')}date={partition}/train.parquet"


def curated_test(partition: str) -> str:
    """El dataset de prueba de una corrida."""
    return f"{curated_prefix('test')}date={partition}/test.parquet"


def curated_params(partition: str) -> str:
    """Los parámetros de preprocesamiento con los que se codificó esa corrida."""
    return f"{curated_prefix('params')}date={partition}/params.json"


# Los tres artefactos que la capa curada produce. La capa está completa cuando están los tres:
# un dataset sin sus parámetros no se puede servir, así que no alcanza con los dos datasets.
CURATED_ARTIFACTS: tuple[Callable[[str], str], ...] = (
    curated_train,
    curated_test,
    curated_params,
)
