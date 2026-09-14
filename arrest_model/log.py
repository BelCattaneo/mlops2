"""El logging de los servicios, sin tocarle el del resto del proceso."""

import logging

# El mismo formato que usa uvicorn, para que las líneas propias no desentonen con las suyas.
FORMAT = "%(levelname)s:     %(message)s"


def service_logger(name: str) -> logging.Logger:
    """Devuelve el logger del servicio, con su propio handler y en nivel INFO.

    No usa `logging.basicConfig` porque eso configura el logger root, o sea el proceso entero:
    al hacerlo mientras se importa el módulo, cualquiera que importe el servicio —los tests, el
    notebook, el otro servicio— se quedaba con el logging cambiado sin haberlo pedido.

    El handler propio igual hace falta: uvicorn configura sus loggers pero deja el root sin
    ninguno, y logging descarta los INFO que no llegan a ningún handler. Sin esto, el log por
    request no aparecería en el contenedor.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:  # importar dos veces no puede dejar la línea duplicada
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
