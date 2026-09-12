"""Mini-TP 3: servicio gRPC."""

import filecmp
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROTO = "tp3_grpc/scoring.proto"
STUBS = ("tp3_grpc/scoring_pb2.py", "tp3_grpc/scoring_pb2_grpc.py")


def _generate_stubs(output_dir: Path) -> None:
    """Genera los stubs dentro de output_dir, con el mismo comando que `make grpc-stubs`."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I",
            ".",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            PROTO,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"protoc falló: {result.stderr}"


def test_versioned_stubs_match_the_proto(tmp_path: Path) -> None:
    for stub in STUBS:
        assert (REPO / stub).exists(), f"falta {stub}: corré `make grpc-stubs`"
    _generate_stubs(tmp_path)
    for stub in STUBS:
        assert filecmp.cmp(REPO / stub, tmp_path / stub, shallow=False), (
            f"{stub} no coincide con {PROTO}: corré `make grpc-stubs`"
        )
