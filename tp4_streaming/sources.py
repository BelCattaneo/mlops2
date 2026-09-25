"""Mini-TP 4: de dónde salen los eventos que se puntúan.

Una fuente es cualquier cosa que se pueda recorrer y entregue reportes. El consumidor no sabe
cuál está usando: con eso, el mismo scoring corre contra una cola en memoria o contra un broker.
"""

import queue
import threading
from collections.abc import Iterable, Iterator
from typing import Any

Event = dict[str, Any]

# Marca el final del flujo dentro de la cola; no es un evento y nunca sale de este módulo.
_END = object()


class QueueSource:
    """Fuente en memoria: un hilo publica los reportes en una cola y el consumidor los saca.

    El productor va en su propio hilo a propósito: así generar el evento siguiente no frena al
    que está puntuando, que es lo que distingue un flujo de recorrer una lista.
    """

    def __init__(self, events: Iterable[Event], maxsize: int = 100) -> None:
        self.events = events
        self.queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    def _produce(self) -> None:
        """Publica cada evento en la cola y avisa cuando se terminaron."""
        for event in self.events:
            self.queue.put(event)
        self.queue.put(_END)

    def __iter__(self) -> Iterator[Event]:
        """Arranca el productor y entrega los eventos a medida que llegan."""
        producer = threading.Thread(target=self._produce, daemon=True)
        producer.start()
        while True:
            event = self.queue.get()
            if event is _END:
                break
            yield event
        producer.join()
