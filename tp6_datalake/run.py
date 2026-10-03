"""Mini-TP 6: recorre el lake de punta a punta.

Uso: `uv run python -m tp6_datalake.run [--bucket X] [--version v1] [--sin-mlflow]`,
o `make lake-run`, con MinIO levantado.
"""

import argparse
from datetime import UTC, datetime

from arrest_model.model import predict
from arrest_model.schemas import EXAMPLE_REPORT, CrimeReport
from tp6_datalake.curated import land_curated
from tp6_datalake.ingest import land_raw
from tp6_datalake.lake import BUCKET, ZONES, client, ensure_bucket
from tp6_datalake.models import VERSION, load_model, publish_model
from tp6_datalake.tracking import log_run, tracking_available


def run_lake(bucket: str = BUCKET, version: str = VERSION, with_mlflow: bool = True) -> int:
    """Crea las zonas, sube los datos y el modelo, y predice con lo que baja del lake."""
    dia = datetime.now(UTC).date().isoformat()
    s3 = client()
    ensure_bucket(s3, bucket)
    print(f"lake      · s3://{bucket} con las zonas {', '.join(ZONES)}")

    aterrizado = land_raw(s3, bucket=bucket, day=dia)
    print(f"raw      · reportes y comisarías, origen {aterrizado['origen']}")
    print(f"           {aterrizado['crimes']}")
    print(f"curated  · {land_curated(s3, bucket=bucket)}")
    print(f"models   · {publish_model(s3, bucket=bucket, version=version)}")

    reporte = CrimeReport.model_validate(EXAMPLE_REPORT)
    prediccion = predict(load_model(s3, bucket=bucket, version=version), [reporte])[0]
    print(
        f"predicción desde el lake · arrest={prediccion.arrest} "
        f"probabilidad={prediccion.probability:.4f} modelo={prediccion.model_name}"
    )

    if with_mlflow and tracking_available():
        print(f"mlflow   · corrida {log_run()} con el artefacto en el lake")
    elif with_mlflow:
        print("mlflow   · no hay servidor en 5001, se omite el registro")
    return 0


def main() -> int:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser(description="Sube datos y modelo al lake y sirve desde ahí")
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--sin-mlflow", action="store_true", help="omite el registro en MLflow")
    args = parser.parse_args()
    return run_lake(args.bucket, args.version, with_mlflow=not args.sin_mlflow)


if __name__ == "__main__":
    raise SystemExit(main())
