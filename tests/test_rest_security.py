"""El control de acceso del servicio REST de la plataforma: quién pregunta y cuánto puede."""

import datetime
import logging
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from arrest_model.schemas import MAX_BATCH_REPORTS, CrimeReport
from tp1_rest.app import create_app, service
from tp1_rest.security import (
    ANONYMOUS,
    AUTH_ENV,
    FORBIDDEN_DETAIL,
    INVALID_TOKEN_DETAIL,
    MIN_SECRET_LENGTH,
    REPORTS_PER_DAY,
    REPORTS_PER_MINUTE,
    SECRET_ENV,
    OpenGuard,
    TokenGuard,
    guard_from_env,
    issue_token,
    main,
    report_digest,
)

SECRET = "un-secreto-de-prueba-con-mas-de-32-bytes"


class Clock:
    """Reloj que avanza cuando el test lo dice, para probar las ventanas sin esperarlas."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def credential(token: str) -> HTTPAuthorizationCredentials:
    """Lo que FastAPI le pasa a la dependencia cuando el header `Authorization` trae un Bearer."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_a_token_with_an_allowed_role_identifies_who_asks() -> None:
    guard = TokenGuard(SECRET)

    assert guard.identify(credential(issue_token(SECRET, "bel", "analista"))) == "bel"


def test_without_a_credential_it_is_401() -> None:
    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(None)

    assert fallo.value.status_code == 401


def test_a_token_signed_with_another_secret_is_401() -> None:
    ajeno = issue_token("otro-secreto-igual-de-largo-para-firmar", "bel", "analista")

    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential(ajeno))

    assert fallo.value.status_code == 401


def test_an_expired_token_is_401() -> None:
    # El vencimiento corto es el control: lo que limita el daño de una credencial filtrada es
    # cuánto dura, no cuán largo sea el secreto.
    vencido = issue_token(SECRET, "bel", "analista", minutes=-1)

    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential(vencido))

    assert fallo.value.status_code == 401


def test_a_token_that_declares_no_signature_is_401() -> None:
    # La vulnerabilidad clásica de JWT: aceptar el algoritmo que viene adentro del token deja
    # entrar uno firmado con `none`. Se cierra declarando el algoritmo al verificar.
    sin_firma = jwt.encode(
        {
            "sub": "atacante",
            "rol": "admin",
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential(sin_firma))

    assert fallo.value.status_code == 401


def test_a_valid_token_with_another_role_is_403_and_not_401() -> None:
    # La diferencia importa: le dice al cliente que su credencial está bien pero no alcanza.
    invitado = issue_token(SECRET, "ajeno", "invitado")

    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential(invitado))

    assert fallo.value.status_code == 403
    assert fallo.value.detail == FORBIDDEN_DETAIL


def test_a_token_without_a_subject_is_401() -> None:
    # Sin `sub` no hay a quién auditar ni a quién cobrarle la cuota.
    anonimo = jwt.encode(
        {"rol": "analista", "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(5)},
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential(anonimo))

    assert fallo.value.status_code == 401


def test_the_rejection_does_not_echo_the_library_message() -> None:
    # El motivo exacto le sirve a quien prueba credenciales, no a quien usa el servicio: va al
    # log del servidor y no a la respuesta.
    with pytest.raises(HTTPException) as fallo:
        TokenGuard(SECRET).identify(credential("esto-no-es-un-token"))

    assert fallo.value.detail == INVALID_TOKEN_DETAIL


def test_the_largest_batch_passes_even_if_the_minute_already_had_traffic() -> None:
    # Medido contra la plataforma: con la cuota del minuto igual al tope del lote, una
    # predicción suelta antes vuelve imposible la llamada más grande que el contrato acepta. El
    # cuota tiene que dejar lugar al lote máximo más el tráfico normal del minuto.
    guard = TokenGuard(SECRET, clock=Clock())
    guard.charge("bel", 1)

    guard.charge("bel", MAX_BATCH_REPORTS)

    assert [gasto for _, gasto in guard.spent["bel"]] == [1, MAX_BATCH_REPORTS]


def test_spending_more_than_the_minute_quota_is_429() -> None:
    guard = TokenGuard(SECRET, clock=Clock())
    guard.charge("bel", REPORTS_PER_MINUTE)

    with pytest.raises(HTTPException) as fallo:
        guard.charge("bel", 1)

    assert fallo.value.status_code == 429


def test_the_quota_is_per_user() -> None:
    # Se cobra por usuario del token y no por IP: detrás de un proxy todas las consultas llegan
    # con la misma IP, así que limitar por IP castigaría a todos por el abuso de uno.
    guard = TokenGuard(SECRET, clock=Clock())
    guard.charge("bel", REPORTS_PER_MINUTE)

    guard.charge("otra", REPORTS_PER_MINUTE)

    assert [gasto for _, gasto in guard.spent["otra"]] == [REPORTS_PER_MINUTE]


def test_the_minute_window_slides() -> None:
    reloj = Clock()
    guard = TokenGuard(SECRET, clock=reloj)
    guard.charge("bel", REPORTS_PER_MINUTE)

    reloj.advance(61)

    guard.charge("bel", REPORTS_PER_MINUTE)

    # Las dos pasaron, y las dos siguen contando para la cuota del día.
    assert [gasto for _, gasto in guard.spent["bel"]] == [REPORTS_PER_MINUTE] * 2


def test_the_daily_quota_caps_what_the_minute_quota_lets_through() -> None:
    # Lotes máximos repartidos en la hora pasan todos por minuto y agotan el día: lo que acota
    # la extracción del modelo es este segundo tope.
    reloj = Clock()
    guard = TokenGuard(SECRET, clock=reloj)
    for _ in range(REPORTS_PER_DAY // MAX_BATCH_REPORTS):
        guard.charge("bel", MAX_BATCH_REPORTS)
        reloj.advance(61)

    with pytest.raises(HTTPException) as fallo:
        guard.charge("bel", 1)

    assert fallo.value.status_code == 429


def test_the_daily_window_also_slides() -> None:
    reloj = Clock()
    guard = TokenGuard(SECRET, clock=reloj)
    for _ in range(REPORTS_PER_DAY // MAX_BATCH_REPORTS):
        guard.charge("bel", MAX_BATCH_REPORTS)
        reloj.advance(61)

    reloj.advance(24 * 60 * 60)

    guard.charge("bel", MAX_BATCH_REPORTS)

    # El día viejo se olvidó: lo único que queda contando es lo que se acaba de cobrar.
    assert [gasto for _, gasto in guard.spent["bel"]] == [MAX_BATCH_REPORTS]


def test_the_open_guard_serves_without_credentials() -> None:
    # Es lo que sirve el mini-TP 1, que se entrega abierto y no es parte del integrador.
    guard = OpenGuard()

    assert guard.identify(None) == ANONYMOUS
    guard.charge(ANONYMOUS, REPORTS_PER_DAY * 10)


def test_without_a_secret_the_service_does_not_start() -> None:
    with pytest.raises(RuntimeError, match=SECRET_ENV):
        guard_from_env({})


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(RuntimeError, match=str(MIN_SECRET_LENGTH)):
        guard_from_env({SECRET_ENV: "corto"})


def test_opening_the_service_has_to_be_said_out_loud() -> None:
    # Sin secreto el servicio no arranca; abrirlo es una decisión explícita y visible, no el
    # default de un deploy al que se le olvidó la variable.
    assert isinstance(guard_from_env({AUTH_ENV: "off"}), OpenGuard)


def test_with_a_secret_it_guards_with_that_secret() -> None:
    guard = guard_from_env({SECRET_ENV: SECRET})

    assert isinstance(guard, TokenGuard)
    assert guard.identify(credential(issue_token(SECRET, "bel", "admin"))) == "bel"


# El servicio con el control puesto ────────────────────────────────────────────────────────────


def guarded(bundle: dict[str, Any], **limits: int) -> tuple[TestClient, TokenGuard]:
    """Un cliente del servicio protegido y el guardia que lo cuida, para mirarle las cuentas."""
    guard = TokenGuard(SECRET, clock=Clock(), **limits)
    return TestClient(create_app(lambda: bundle, guard=guard)), guard


def header(user: str = "bel", role: str = "analista") -> dict[str, str]:
    """El header `Authorization` que manda un consumidor del servicio."""
    return {"Authorization": f"Bearer {issue_token(SECRET, user, role)}"}


def test_the_platform_does_not_predict_without_a_token(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    client, _ = guarded(bundle)

    with client:
        assert client.post("/v1/predict", json=valid_payload).status_code == 401


def test_an_authorized_role_predicts(
    bundle: dict[str, Any], valid_payload: dict[str, Any], reference_probability: float
) -> None:
    client, _ = guarded(bundle)

    with client:
        response = client.post("/v1/predict", json=valid_payload, headers=header())

    assert response.status_code == 200
    assert response.json()["probability"] == pytest.approx(reference_probability)


def test_a_valid_token_with_another_role_cannot_predict(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    client, _ = guarded(bundle)

    with client:
        response = client.post(
            "/v1/predict", json=valid_payload, headers=header("ajeno", "invitado")
        )

    assert response.status_code == 403


def test_the_metadata_of_the_model_needs_a_token(bundle: dict[str, Any]) -> None:
    # Publica las métricas, las features y el umbral de decisión: es lo que necesita quien quiere
    # entrenar un sustituto del modelo.
    client, _ = guarded(bundle)

    with client:
        assert client.get("/v1/metadata").status_code == 401
        assert client.get("/v1/metadata", headers=header()).status_code == 200


def test_a_batch_charges_every_report_it_carries(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    # La cuota se cuenta en reportes y no en llamadas: una llamada puede traer mil.
    client, _ = guarded(bundle, per_minute=2, per_day=99)

    with client:
        lote = client.post(
            "/v1/predict/batch", json={"reports": [valid_payload] * 2}, headers=header()
        )
        siguiente = client.post("/v1/predict", json=valid_payload, headers=header())

    assert lote.status_code == 200
    assert siguiente.status_code == 429


def test_a_payload_the_contract_rejects_does_not_spend_quota(
    bundle: dict[str, Any], valid_payload: dict[str, Any]
) -> None:
    # Se cobra después de validar: un reporte fuera de Chicago no le gasta el cupo a nadie.
    client, _ = guarded(bundle, per_minute=1, per_day=99)

    with client:
        fuera = client.post(
            "/v1/predict", json={**valid_payload, "latitude": 0.0}, headers=header()
        )
        valido = client.post("/v1/predict", json=valid_payload, headers=header())

    assert (fuera.status_code, valido.status_code) == (422, 200)


def test_the_probe_stays_open(bundle: dict[str, Any]) -> None:
    # El healthcheck del compose y cualquier sonda no llevan credenciales.
    client, _ = guarded(bundle)

    with client:
        assert client.get("/health").status_code == 200


def test_the_audit_names_who_asked_and_the_hash_of_what_asked(
    bundle: dict[str, Any], valid_payload: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="tp1_rest")
    client, _ = guarded(bundle)

    with client:
        client.post("/v1/predict", json=valid_payload, headers=header())

    linea = [record.getMessage() for record in caplog.records if record.name == "tp1_rest"][-1]
    assert "usuario bel" in linea
    # El hash es del reporte ya validado y no del payload crudo: dos escrituras del mismo
    # reporte (la fecha con T o con espacio, el lugar en minúsculas) dan el mismo hash.
    assert f"entrada {report_digest([CrimeReport(**valid_payload).model_dump()])}" in linea


def test_the_audit_also_records_what_was_rejected(
    bundle: dict[str, Any], valid_payload: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    # El pico de 401 o de 429 es la señal que hay que poder ver después: un registro que solo
    # guarda lo que salió bien no sirve para detectar el abuso.
    caplog.set_level(logging.INFO, logger="tp1_rest")
    client, _ = guarded(bundle)

    with client:
        client.post("/v1/predict", json=valid_payload)

    linea = [record.getMessage() for record in caplog.records if record.name == "tp1_rest"][-1]
    assert "POST /v1/predict -> 401" in linea


def test_the_hash_does_not_carry_the_report(valid_payload: dict[str, Any]) -> None:
    # Un reporte trae la latitud y la longitud de un hecho: guardarlo entero convertiría el
    # registro de auditoría en una segunda base de datos personales.
    hash_entrada = report_digest([valid_payload])

    assert str(valid_payload["latitude"]) not in hash_entrada
    assert valid_payload["iucr"] not in hash_entrada


def test_the_same_report_hashes_the_same_however_it_was_written(
    valid_payload: dict[str, Any],
) -> None:
    # Para lo que sirve el hash: probar que dos consultas fueron por lo mismo. El contrato
    # normaliza antes, así que el mismo reporte escrito distinto cae en el mismo hash.
    otra_escritura = {
        **valid_payload,
        "location_description": " apartment ",
        "date": "2024-12-31 23:58:00",
    }
    otro_reporte = {**valid_payload, "iucr": "0820"}

    como_llega = report_digest([CrimeReport(**valid_payload).model_dump()])

    assert report_digest([CrimeReport(**otra_escritura).model_dump()]) == como_llega
    assert report_digest([CrimeReport(**otro_reporte).model_dump()]) != como_llega


def test_the_platform_service_does_not_start_without_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SECRET_ENV, raising=False)
    monkeypatch.delenv(AUTH_ENV, raising=False)

    with pytest.raises(RuntimeError, match=SECRET_ENV):
        service()


def test_the_token_cli_mints_one_the_service_accepts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # El token lo firma el propio servicio con su secreto: no hay un segundo lugar donde viva.
    monkeypatch.setenv(SECRET_ENV, SECRET)
    monkeypatch.delenv(AUTH_ENV, raising=False)

    main(["bel", "analista"])

    token = capsys.readouterr().out.strip()
    assert TokenGuard(SECRET).identify(credential(token)) == "bel"


def test_the_token_cli_refuses_when_the_service_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    # Un token firmado con un secreto que nadie verifica da una falsa sensación de control.
    monkeypatch.setenv(AUTH_ENV, "off")

    with pytest.raises(SystemExit):
        main(["bel", "analista"])


def test_a_service_outage_does_not_spend_the_quota(valid_payload: dict[str, Any]) -> None:
    # Si no hay modelo que servir, la respuesta es 503 y la cuota queda intacta: una caída
    # del servicio no puede costarle el cupo del día a quien la sufre.
    guard = TokenGuard(SECRET, clock=Clock(), per_minute=2, per_day=2)
    sin_modelo = TestClient(create_app(lambda: None, guard=guard))

    with sin_modelo:
        lote = sin_modelo.post(
            "/v1/predict/batch", json={"reports": [valid_payload] * 2}, headers=header()
        )
        suelta = sin_modelo.post("/v1/predict", json=valid_payload, headers=header())

    assert (lote.status_code, suelta.status_code) == (503, 503)
    assert guard.spent.get("bel", []) == []
