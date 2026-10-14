"""Quién pregunta y cuánto puede preguntarle al modelo.

El servicio de la plataforma deja de ser anónimo: cada predicción tiene un responsable, un rol
que la autoriza y un presupuesto. El emisor de los tokens queda afuera a propósito —en producción
es un IdP—; acá el servicio solo verifica la firma del secreto que le da el entorno.

El presupuesto se cuenta en reportes y no en llamadas porque una llamada puede traer mil, así que
limitar llamadas no acota el trabajo. Los números salen del volumen medido: el portal publica 633
reportes por día, o sea 0,44 por minuto, y el contrato acepta hasta `MAX_BATCH_REPORTS` por
llamada. El tope del minuto son dos lotes máximos —uno solo haría que la llamada más grande que
el contrato permite necesitara el minuto limpio, medido contra la plataforma— y el del día son
5000, unas ocho veces el volumen real, así que ningún consumidor legítimo los ve.

Lo que compran es acotar la extracción del modelo: con tope diario, reconstruir la frontera
preguntando es lento y queda en el registro de auditoría, que es donde se ve a quien sostiene el
tope. El límite no vuelve imposible el robo del modelo, lo vuelve lento y visible.
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from arrest_model.schemas import MAX_BATCH_REPORTS

SECRET_ENV = "REST_JWT_SECRET"
AUTH_ENV = "REST_AUTH"
MIN_SECRET_LENGTH = 32

ALLOWED_ROLES = frozenset({"analista", "admin"})
TOKEN_MINUTES = 15
REPORTS_PER_MINUTE = 2 * MAX_BATCH_REPORTS
REPORTS_PER_DAY = 5000
MINUTE = 60.0
DAY = 24 * 60 * MINUTE

ANONYMOUS = "anónimo"
INVALID_TOKEN_DETAIL = "credencial inválida"
FORBIDDEN_DETAIL = "el rol no autoriza a pedir predicciones"
THROTTLED_DETAIL = "presupuesto de reportes agotado"


def issue_token(
    secret: str,
    user: str,
    role: str,
    *,
    minutes: int = TOKEN_MINUTES,
    now: datetime.datetime | None = None,
) -> str:
    """Firma un token para ese usuario y rol, con vencimiento corto."""
    momento = now or datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": user,
        "rol": role,
        "exp": momento + datetime.timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def report_digest(reports: Sequence[Mapping[str, object]]) -> str:
    """Huella de la entrada, para que el registro de auditoría no sea la entrada.

    Un reporte trae la latitud y la longitud de un hecho, así que guardarlo entero convertiría el
    registro en una segunda base de datos personales, que es justo lo que la auditoría debería
    proteger. Con la huella alcanza para lo que sirve: probar que dos consultas fueron por lo
    mismo y atar cada respuesta a su entrada.
    """
    canonical = json.dumps(list(reports), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


class OpenGuard:
    """Sin control de acceso: lo que sirve el mini-TP 1, que se entrega abierto.

    Existe para que la plataforma y el mini-TP compartan el mismo código del servicio sin que el
    camino protegido se llene de `if`: el que no protege también es un guardia.
    """

    def identify(self, credential: HTTPAuthorizationCredentials | None) -> str:
        """Siempre el mismo llamador anónimo, que es lo que queda en el log."""
        return ANONYMOUS

    def charge(self, user: str, reports: int) -> None:
        """No hay presupuesto que gastar."""


@dataclass
class TokenGuard:
    """Verifica el token, exige un rol autorizado y cobra el presupuesto de reportes."""

    secret: str
    roles: frozenset[str] = ALLOWED_ROLES
    per_minute: int = REPORTS_PER_MINUTE
    per_day: int = REPORTS_PER_DAY
    clock: Callable[[], float] = time.time
    spent: dict[str, list[tuple[float, int]]] = field(default_factory=dict, repr=False)

    def identify(self, credential: HTTPAuthorizationCredentials | None) -> str:
        """Devuelve quién pregunta, o corta con 401 si no se sabe y 403 si no está autorizado."""
        if credential is None:
            raise HTTPException(401, INVALID_TOKEN_DETAIL)
        try:
            # El algoritmo va declarado: aceptar el que viene adentro del token es la
            # vulnerabilidad clásica de JWT, porque deja entrar uno firmado con `none`.
            claims = jwt.decode(credential.credentials, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            # El motivo exacto le sirve a quien prueba credenciales: va al log, no a la respuesta.
            raise HTTPException(401, INVALID_TOKEN_DETAIL) from None
        user = claims.get("sub")
        if not isinstance(user, str) or not user:
            raise HTTPException(401, INVALID_TOKEN_DETAIL)  # sin `sub` no hay a quién auditar
        if claims.get("rol") not in self.roles:
            raise HTTPException(403, FORBIDDEN_DETAIL)
        return user

    def charge(self, user: str, reports: int) -> None:
        """Cobra `reports` al presupuesto del usuario, o corta con 429 si ya no le queda.

        Se cobra después de validar y antes de predecir: un payload que el contrato rechaza no
        gasta cupo de nadie, y uno válido no llega al modelo si el presupuesto está agotado.
        """
        ahora = self.clock()
        historia = [(t, n) for t, n in self.spent.get(user, []) if ahora - t < DAY]
        del_minuto = sum(n for t, n in historia if ahora - t < MINUTE)
        del_dia = sum(n for _, n in historia)
        if del_minuto + reports > self.per_minute or del_dia + reports > self.per_day:
            self.spent[user] = historia
            raise HTTPException(429, THROTTLED_DETAIL)
        self.spent[user] = [*historia, (ahora, reports)]


def guard_from_env(env: Mapping[str, str]) -> OpenGuard | TokenGuard:
    """El guardia que corresponde al entorno, o `RuntimeError` si no alcanza para decidir.

    Falla cerrado: sin secreto el servicio no arranca. Servir abierto es una decisión que hay
    que decir en voz alta —`REST_AUTH=off`, como hacen los targets del mini-TP 1— y no el default
    de un deploy al que se le olvidó la variable.
    """
    if env.get(AUTH_ENV, "").lower() == "off":
        return OpenGuard()
    secret = env.get(SECRET_ENV, "")
    if not secret:
        raise RuntimeError(
            f"Falta {SECRET_ENV}: el servicio no sirve el modelo sin control de acceso. "
            f"Para servirlo abierto, {AUTH_ENV}=off."
        )
    if len(secret.encode("utf-8")) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"{SECRET_ENV} tiene que tener al menos {MIN_SECRET_LENGTH} bytes: "
            "un secreto corto de HS256 se prueba por fuerza bruta."
        )
    return TokenGuard(secret)


def main(argv: Sequence[str] | None = None) -> None:
    """Firma un token para pedirle predicciones al servicio, con el secreto de su entorno.

    Corre dentro del contenedor del servicio —`make stack-token`— justamente para que el secreto
    no tenga que salir de ahí. En producción esto lo hace un IdP; acá alcanza para operar y para
    mostrar el control funcionando.
    """
    parser = argparse.ArgumentParser(description="Firma un token de acceso al servicio REST.")
    parser.add_argument("user", help="a quién se le emite, que es lo que queda en la auditoría")
    parser.add_argument("role", nargs="?", default="analista", choices=sorted(ALLOWED_ROLES))
    parser.add_argument("--minutes", type=int, default=TOKEN_MINUTES)
    args = parser.parse_args(argv)

    guard = guard_from_env(os.environ)
    if not isinstance(guard, TokenGuard):
        # Un token firmado con un secreto que nadie verifica da una falsa sensación de control.
        sys.exit(f"El servicio está abierto ({AUTH_ENV}=off): no hay token que emitir.")
    print(issue_token(guard.secret, args.user, args.role, minutes=args.minutes))


if __name__ == "__main__":
    main()
