"""Compara la latencia de gRPC contra REST sirviendo el mismo modelo.

**Simetría**: los dos protocolos hacen exactamente el mismo trabajo (validar, codificar y
predecir) y se miden en el mismo lugar. Si uno corriera en contenedor y el otro local, se
estaría midiendo el empaquetado y no el protocolo.

Se mide REST de dos formas a propósito: sin sesión (conexión nueva por llamada) y con
keep-alive. gRPC reutiliza el canal siempre, así que la comparación justa es contra keep-alive;
la otra muestra cuánto cuesta el handshake.

Uso: `uv run python -m tp3_grpc.benchmark [--n 300] [--rest-url ...] [--grpc-target ...]`
"""

import argparse
import math
import time
from collections.abc import Callable
from typing import Any

import grpc
import requests

from arrest_model.schemas import EXAMPLE_REPORT
from tp3_grpc import scoring_pb2, scoring_pb2_grpc
from tp3_grpc.client import crime_report

REST_URL = "http://127.0.0.1:8000"
GRPC_TARGET = "127.0.0.1:50051"


def percentile(samples: list[float], fraction: float) -> float:
    """Percentil por rango más cercano: el p95 de 100 muestras es la muestra 95."""
    rank = max(1, math.ceil(fraction * len(samples)))
    return sorted(samples)[rank - 1]


def summarize(samples: list[float]) -> dict[str, float]:
    """Media, mediana y p95 de las latencias, en ms."""
    return {
        "media": sum(samples) / len(samples),
        "p50": percentile(samples, 0.50),
        "p95": percentile(samples, 0.95),
    }


def elapsed_ms(call: Callable[[], Any]) -> float:
    """Milisegundos que tarda una sola llamada."""
    started = time.perf_counter()
    call()
    return (time.perf_counter() - started) * 1000


def measure(call: Callable[[], Any], n: int, warmup: int) -> dict[str, float]:
    """Descarta `warmup` llamadas y resume la latencia de las `n` siguientes."""
    for _ in range(warmup):
        call()
    return summarize([elapsed_ms(call) for _ in range(n)])


def run_benchmark(
    rest_url: str = REST_URL,
    grpc_target: str = GRPC_TARGET,
    n: int = 300,
    warmup: int = 30,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Corre las dos comparaciones (una llamada, y un lote) y devuelve los números."""
    payload = dict(EXAMPLE_REPORT)
    predict_url, batch_url = f"{rest_url}/v1/predict", f"{rest_url}/v1/predict/batch"
    message = crime_report()
    batch = scoring_pb2.CrimeBatch(items=[crime_report()] * batch_size)

    with requests.Session() as session, grpc.insecure_channel(grpc_target) as channel:
        grpc.channel_ready_future(channel).result(timeout=15)
        stub = scoring_pb2_grpc.ArrestScoringStub(channel)
        unary = {
            "REST sin sesión": measure(
                lambda: requests.post(predict_url, json=payload, timeout=10), n, warmup
            ),
            "REST keep-alive": measure(
                lambda: session.post(predict_url, json=payload, timeout=10), n, warmup
            ),
            "gRPC": measure(lambda: stub.Predict(message), n, warmup),
        }
        lote = {
            f"{batch_size} POST /v1/predict": elapsed_ms(
                lambda: [
                    session.post(predict_url, json=payload, timeout=10) for _ in range(batch_size)
                ]
            ),
            "1 POST /v1/predict/batch": elapsed_ms(
                lambda: session.post(
                    batch_url, json={"reports": [payload] * batch_size}, timeout=30
                )
            ),
            "1 PredictStream": elapsed_ms(lambda: list(stub.PredictStream(batch))),
        }
    return {"n": n, "batch_size": batch_size, "unary": unary, "lote": lote}


def format_results(results: dict[str, Any]) -> str:
    """Arma las dos tablas en markdown, listas para pegar en el README o el notebook."""
    lines = [f"Una llamada, {results['n']} repeticiones (ms):", "", "| forma | media | p50 | p95 |"]
    lines.append("|---|---|---|---|")
    for label, stats in results["unary"].items():
        lines.append(
            f"| {label} | {stats['media']:.2f} | {stats['p50']:.2f} | {stats['p95']:.2f} |"
        )
    lines += ["", f"Lote de {results['batch_size']} reportes (ms totales):", ""]
    lines += ["| forma | total |", "|---|---|"]
    for label, total in results["lote"].items():
        lines.append(f"| {label} | {total:.1f} |")
    return "\n".join(lines)


def main() -> int:
    """Punto de entrada: corre el benchmark e imprime las tablas."""
    parser = argparse.ArgumentParser(description="Latencia de gRPC contra REST")
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--rest-url", default=REST_URL)
    parser.add_argument("--grpc-target", default=GRPC_TARGET)
    args = parser.parse_args()
    try:
        results = run_benchmark(
            rest_url=args.rest_url,
            grpc_target=args.grpc_target,
            n=args.n,
            warmup=args.warmup,
            batch_size=args.batch_size,
        )
    except (requests.RequestException, grpc.FutureTimeoutError) as exc:
        print(f"No se pudo medir ({type(exc).__name__}).")
        print("Tienen que estar los dos servicios arriba y del mismo lado: ver `make help`.")
        return 1
    print(format_results(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
