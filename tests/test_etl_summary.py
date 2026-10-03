"""El resumen de la corrida, armado con los conteos que trae cada capa."""

from etl_helpers.summary import summary_counts

CRUDO = {"status": "success", "rows": 227976}
LIMPIO = {"status": "success", "raw_rows": 227976, "rows": 226951}
FINAL = {
    "status": "success",
    "split_rows": (181560, 45391),
    "balanced_rows": 170453,
    "rows": (170453, 44795),
    "features": 7,
}


def test_builds_the_counts_of_every_stage() -> None:
    conteos = summary_counts(CRUDO, LIMPIO, FINAL)

    assert conteos == {
        "raw_count": 227976,
        "enriched_count": 226951,
        "train_count": 181560,
        "test_count": 45391,
        "balanced_count": 170453,
        "final_train_count": 170453,
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
