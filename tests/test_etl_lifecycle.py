"""La política de ciclo de vida del bucket, capa por capa."""

from etl_helpers.minio.client import lifecycle_rules


def test_a_layer_with_a_ttl_gets_a_rule() -> None:
    configuracion = lifecycle_rules({"enriched/": 30})

    assert len(configuracion["Rules"]) == 1
    regla = configuracion["Rules"][0]
    assert regla["Filter"]["Prefix"] == "enriched/"
    assert regla["Expiration"]["Days"] == 30
    assert regla["Status"] == "Enabled"


def test_every_rule_expires_the_noncurrent_versions_too() -> None:
    # En un bucket versionado, Expiration no borra bytes: pone una marca de borrado y conserva
    # las versiones viejas. Sin NoncurrentVersionExpiration la limpieza no libera nada.
    configuracion = lifecycle_rules({"enriched/": 30, "scratch/": 7})

    for regla in configuracion["Rules"]:
        assert "NoncurrentVersionExpiration" in regla
        assert regla["NoncurrentVersionExpiration"]["NoncurrentDays"] >= 1


def test_the_layers_that_are_kept_get_no_rule() -> None:
    configuracion = lifecycle_rules({"enriched/": 30})

    prefijos = [regla["Filter"]["Prefix"] for regla in configuracion["Rules"]]
    assert "raw/" not in prefijos
    assert "curated/" not in prefijos


def test_an_empty_policy_leaves_no_rules() -> None:
    assert lifecycle_rules({})["Rules"] == []


def test_each_rule_has_an_id_that_says_what_it_does() -> None:
    regla = lifecycle_rules({"enriched/": 30})["Rules"][0]

    assert "enriched" in regla["ID"]
    assert "30" in regla["ID"]
