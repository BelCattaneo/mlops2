"""Cliente de prueba del Mini-TP 1: llama a la API y muestra cada respuesta."""

import argparse
import json

import requests

from arrest_model.schemas import EXAMPLE_REPORT

# Cada caso rompe una validación distinta del contrato; todos deben dar 422.
INVALID = {
    "sin fecha": {key: value for key, value in EXAMPLE_REPORT.items() if key != "date"},
    "primary_type desconocido": EXAMPLE_REPORT | {"primary_type": "BANANA"},
    "latitud fuera de Chicago": EXAMPLE_REPORT | {"latitude": 40.71},
    "IUCR con formato inválido": EXAMPLE_REPORT | {"iucr": "48"},
    "campo que no está en el contrato": EXAMPLE_REPORT | {"foo": 1},
}


def check(response: requests.Response, expected: int, label: str) -> bool:
    """Muestra status y cuerpo de la respuesta; devuelve si el status es el esperado."""
    ok = response.status_code == expected
    print(f"[{'OK' if ok else 'FALLA'}] {label} -> {response.status_code} (esperado {expected})")
    try:
        body = json.dumps(response.json(), indent=2, ensure_ascii=False)
    except ValueError:
        body = response.text  # un proxy o un error de infraestructura contesta HTML, no JSON
    print(body)
    return ok


def main() -> int:
    """Recorre los casos contra la API; devuelve 0 si todos dan el status esperado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    url = parser.parse_args().url
    try:
        with requests.Session() as http:
            results = [
                check(http.get(f"{url}/health", timeout=10), 200, "GET /health"),
                check(
                    http.post(f"{url}/v1/predict", json=EXAMPLE_REPORT, timeout=10),
                    200,
                    "POST /v1/predict con un payload válido",
                ),
                check(
                    http.post(
                        f"{url}/v1/predict/batch",
                        json={"reports": [EXAMPLE_REPORT, EXAMPLE_REPORT]},
                        timeout=10,
                    ),
                    200,
                    "POST /v1/predict/batch con dos reportes",
                ),
                check(
                    http.post(f"{url}/v1/predict/batch", json={"reports": []}, timeout=10),
                    422,
                    "POST /v1/predict/batch con el lote vacío",
                ),
                *(
                    check(
                        http.post(f"{url}/v1/predict", json=payload, timeout=10),
                        422,
                        f"POST /v1/predict, {label}",
                    )
                    for label, payload in INVALID.items()
                ),
            ]
    except requests.RequestException as exc:  # cubre conexión rechazada y también timeouts
        print(f"Falló la llamada a {url} ({type(exc).__name__}).")
        print("¿Levantaste la API con `make run` o `make up`?")
        return 1
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
