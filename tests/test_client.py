"""Cliente de prueba: tiene que informar el caso, no romperse, ante respuestas raras."""

import pytest

from tp1_rest.client import check


class FakeResponse:
    """Lo mínimo que usa `check` de una respuesta de requests."""

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict[str, object]:
        raise ValueError("la respuesta no es JSON")


def test_check_survives_a_response_that_is_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    response = FakeResponse(502, "<html>502 Bad Gateway</html>")
    assert check(response, 200, "GET /health") is False
    salida = capsys.readouterr().out
    assert "502" in salida
    assert "Bad Gateway" in salida
