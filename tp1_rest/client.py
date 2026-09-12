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
# Cada caso rompe una validación distinta del contrato; todos deben dar 422.
INVALID = {
    "sin fecha": {key: value for key, value in VALID.items() if key != "date"},
    "primary_type desconocido": VALID | {"primary_type": "BANANA"},
    "latitud fuera de Chicago": VALID | {"latitude": 40.71},
    "IUCR con formato inválido": VALID | {"iucr": "48"},
    "campo que no está en el contrato": VALID | {"foo": 1},
}


def check(response: requests.Response, expected: int, label: str) -> bool:
    """Muestra status y cuerpo de la respuesta; devuelve si el status es el esperado."""
    ok = response.status_code == expected
    print(f"[{'OK' if ok else 'FALLA'}] {label} -> {response.status_code} (esperado {expected})")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
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
                    http.post(f"{url}/v1/predict", json=VALID, timeout=10),
                    200,
                    "POST /v1/predict con un payload válido",
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
    except requests.ConnectionError:
        print(f"No se pudo conectar a {url}: ¿levantaste la API con `make run` o `make up`?")
        return 1
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
