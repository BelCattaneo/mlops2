"""Mini-TP 4: corre el flujo y muestra cómo viene, ventana por ventana.

Uso: `uv run python -m tp4_streaming.run [--events N] [--drift-from N]`, o `make stream-run`.
"""

import argparse

from arrest_model.model import load_bundle
from tp4_streaming.consumer import REPORT_EVERY, WindowReport, score_stream
from tp4_streaming.events import crime_stream
from tp4_streaming.sources import QueueSource

EVENTS = 400
# Ritmo de llegada del flujo, en eventos por segundo, y largo de la ventana en segundos.
RATE = 100.0
WINDOW = 1.0


def format_window(window: WindowReport) -> str:
    """Arma la línea que se imprime al cerrar una ventana."""
    aviso = "  ← ALERTA de drift" if window.alert else ""
    return (
        f"ventana @ {window.scored:4} eventos | {window.events:3} en ventana | "
        f"throughput {window.throughput:7.1f} ev/s | p95 {window.p95_ms:5.2f} ms | "
        f"drift {window.drift:5.2f} | probabilidad media {window.mean_probability:.3f}{aviso}"
    )


def run_stream(
    events: int = EVENTS,
    report_every: int = REPORT_EVERY,
    drift_from: int | None = None,
    rate: float = RATE,
) -> int:
    """Puntúa `events` eventos de a uno y devuelve 0; con `drift_from`, corre la zona desde ahí."""
    source = QueueSource(crime_stream(events, drift_from=drift_from), rate=rate)
    for window in score_stream(
        source, load_bundle(), window_seconds=WINDOW, report_every=report_every
    ):
        print(format_window(window))
    return 0


def main() -> int:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser(description="Puntúa un flujo de reportes evento por evento")
    parser.add_argument("--events", type=int, default=EVENTS)
    parser.add_argument("--report-every", type=int, default=REPORT_EVERY)
    parser.add_argument("--drift-from", type=int, default=None)
    parser.add_argument("--rate", type=float, default=RATE, help="eventos por segundo")
    args = parser.parse_args()
    return run_stream(args.events, args.report_every, args.drift_from, args.rate)


if __name__ == "__main__":
    raise SystemExit(main())
