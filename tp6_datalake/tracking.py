"""Mini-TP 6: el experimento registrado en MLflow, con los artefactos en el lake.

MLflow parte el problema en dos. La metadata de la corrida —parámetros, métricas, etiquetas—
va a PostgreSQL, y los artefactos pesados van al lake. Por eso el servidor se levanta con
`--default-artifact-root s3://mlflow/`: le dice al cliente dónde subir.

El cliente sube el artefacto él mismo, directo a MinIO, así que necesita saber el endpoint y
las credenciales. Esas variables se fijan acá para que importar el módulo alcance.
"""

import os
import socket
from pathlib import Path

from arrest_model.model import MODEL_PATH, load_bundle
from tp6_datalake.lake import ACCESS_KEY, ENDPOINT, SECRET_KEY

TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
EXPERIMENT = "chicago-arrest"

# El cliente imprime una sugerencia sobre una skill propia en cada import; en el notebook
# entregable solo agrega ruido.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", ENDPOINT)
os.environ.setdefault("AWS_ACCESS_KEY_ID", ACCESS_KEY)
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", SECRET_KEY)


def tracking_available(uri: str = TRACKING_URI) -> bool:
    """Dice si el servidor de MLflow está escuchando, para saltear lo que lo necesita."""
    host, _, port = uri.removeprefix("http://").removeprefix("https://").partition(":")
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port or 80))) == 0


def log_run(
    experiment: str = EXPERIMENT,
    tracking_uri: str = TRACKING_URI,
    model_path: Path = MODEL_PATH,
) -> str:
    """Registra una corrida con lo que describe el modelo y sube el artefacto; devuelve su id."""
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    metadata = load_bundle(model_path)["metadata"]
    with mlflow.start_run() as corrida:
        mlflow.log_params(
            {
                "modelo": metadata["name"],
                "version": metadata["version"],
                "framework": metadata["framework"],
                "features": len(metadata["features"]),
            }
        )
        mlflow.log_metrics(metadata["metrics"])
        mlflow.log_artifact(str(model_path))
        return corrida.info.run_id


def metrics_of(run_id: str, tracking_uri: str = TRACKING_URI) -> dict[str, float]:
    """Lee del servidor las métricas que quedaron registradas en esa corrida."""
    import mlflow

    return mlflow.MlflowClient(tracking_uri).get_run(run_id).data.metrics


def artifacts_of(run_id: str, tracking_uri: str = TRACKING_URI) -> list[str]:
    """Lista los artefactos de la corrida, que viven en el lake y no en MLflow."""
    import mlflow

    return [item.path for item in mlflow.MlflowClient(tracking_uri).list_artifacts(run_id)]


def main() -> int:
    """Registra una corrida: `uv run python -m tp6_datalake.tracking`."""
    corrida = log_run()
    print(f"corrida {corrida} registrada en {TRACKING_URI}")
    print("artefactos:", ", ".join(artifacts_of(corrida)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
