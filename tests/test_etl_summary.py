"""El resumen de la corrida, armado con los conteos que trae cada capa."""

from etl_helpers.summary import CONTEOS, summary_counts

CRUDO = {"status": "success", "rows": 227976}
LIMPIO = {"status": "success", "raw_rows": 227976, "rows": 226951}
FINAL = {
    "status": "success",
    "split_rows": (181560, 45391),
    "rows": (181560, 44795),
    "features": 7,
}


def test_builds_the_counts_of_every_stage() -> None:
    conteos = summary_counts(CRUDO, LIMPIO, FINAL)

    assert conteos == {
        "raw_count": 227976,
        "enriched_count": 226951,
        "train_count": 181560,
        "test_count": 45391,
        "final_train_count": 181560,
        "final_test_count": 44795,
        "feature_count": 7,
    }


def test_takes_the_raw_count_from_the_enriched_layer_when_the_download_was_skipped() -> None:
    # La descarga vuelve temprano cuando la partición ya está, y entonces no sabe cuántas filas
    # tiene: el conteo lo pone la capa que las leyó.
    crudo_salteado = {"status": "success", "rows": None}

    assert summary_counts(crudo_salteado, LIMPIO, FINAL)["raw_count"] == 227976


def test_there_is_nothing_to_summarize_when_a_layer_was_skipped() -> None:
    # Si la capa final no recalculó nada, su XCom no trae conteos y no hay corrida que resumir.
    final_salteado = {"status": "success", "train_file": "x", "test_file": "y"}

    assert summary_counts(CRUDO, LIMPIO, final_salteado) is None


def test_there_is_nothing_to_summarize_without_data() -> None:
    assert summary_counts(CRUDO, LIMPIO, {"status": "no_data"}) is None
    assert summary_counts(CRUDO, {"status": "no_data"}, {"status": "no_data"}) is None


def test_the_counts_are_exactly_what_the_mlflow_logger_accepts() -> None:
    """Las claves que arma el resumen tienen que ser los parámetros que el logger recibe.

    El DAG llama `log_pipeline_summary(**conteos)`, así que una clave de más o de menos es un
    TypeError en la tarea. Medido: al sacar la etapa de balanceo quedó `balanced_count` como
    parámetro obligatorio del logger y ninguna prueba lo vio, porque este módulo se probaba
    solo. Y en las corridas tibias no se notaba: cuando una capa toma el atajo de idempotencia
    el resumen devuelve `None` y la tarea sale antes de llamar al logger. Falló en la primera
    corrida que hizo trabajo de verdad, que fue la de una instalación nueva.
    """
    import inspect

    from etl_helpers.monitoring.loggers import log_pipeline_summary

    parametros = inspect.signature(log_pipeline_summary).parameters
    obligatorios = {
        nombre
        for nombre, p in parametros.items()
        if p.default is inspect.Parameter.empty and nombre != "run_name"
    }

    assert obligatorios == set(CONTEOS)
    assert set(summary_counts(CRUDO, LIMPIO, FINAL)) == set(CONTEOS)
