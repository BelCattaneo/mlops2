"""Cliente de prueba del Mini-TP 1: llama a la API y muestra cada respuesta."""

import argparse
import json

import requests

# Primera fila real de Crimes_Chicago_2024.csv (TP-final) con los 6 campos del contrato.
VALID = {
    "iucr": "1310",
    "primary_type": "CRIMINAL DAMAGE",
    "location_description": "APARTMENT",
    "date": "2024-12-31T23:58:00",
    "latitude": 41.771470188,
    "longitude": -87.59074212,
}
WITHOUT_DATE = {key: value for key, value in VALID.items() if key != "date"}


def check(response: requests.Response, expected: int, label: str) -> bool:
    """Muestra status y cuerpo de la respuesta; devuelve si el status es el esperado."""
    ok = response.status_code == expected
    print(f"[{'OK' if ok else 'FALLA'}] {label} -> {response.status_code} (esperado {expected})")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    url = parser.parse_args().url
    try:
        with requests.Session() as http:
            results = [
                check(http.get(f"{url}/health", timeout=10), 200, "GET /health"),
                check(
                    http.post(f"{url}/v1/predict", json=VALID, timeout=10),
                    200,
                    "POST /v1/predict con un payload válido",
                ),
                check(
                    http.post(f"{url}/v1/predict", json=WITHOUT_DATE, timeout=10),
                    422,
                    "POST /v1/predict sin fecha (inválido)",
                ),
            ]
    except requests.ConnectionError:
        print(f"No se pudo conectar a {url}: ¿levantaste la API con `make run` o `make up`?")
        return 1
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
