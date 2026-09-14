"""Que importar un servicio no le cambie el logging al resto del proceso.

`logging.basicConfig` configura el logger root, o sea todo el proceso. Llamarlo al importar el
módulo le cambia el logging a cualquiera que importe el servicio: los tests, el notebook o el
otro servicio. Cada uno tiene que configurar su propio logger y nada más.

Corre en un subproceso a propósito: bajo pytest el root ya tiene handlers y `basicConfig` no
hace nada, así que un test en este mismo proceso pasaría sin haber probado nada.
"""

import subprocess
import sys

import pytest

SONDA = "import logging, {modulo}; print(len(logging.root.handlers), logging.root.level)"

# Los valores por defecto de logging: el root sin handlers y en WARNING.
ROOT_INTACTO = ["0", "30"]


@pytest.mark.parametrize("modulo", ["tp1_rest.app", "tp3_grpc.server"])
def test_importing_a_service_leaves_the_root_logger_alone(modulo: str) -> None:
    salida = subprocess.run(
        [sys.executable, "-c", SONDA.format(modulo=modulo)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert salida.stdout.split() == ROOT_INTACTO
