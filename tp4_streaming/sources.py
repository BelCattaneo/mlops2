"""Mini-TP 4: de dónde salen los eventos que se puntúan.

Una fuente es cualquier cosa que se pueda recorrer y entregue reportes. El consumidor no sabe
cuál está usando: con eso, el mismo scoring corre contra una cola en memoria o contra un broker.
"""

import queue
import threading
import time
from collections.abc import Iterable, Iterator
from typing import Any

Event = dict[str, Any]

# Marca el final del flujo dentro de la cola; no es un evento y nunca sale de este módulo.
_END = object()


class QueueSource:
    """Fuente en memoria: un hilo publica los reportes en una cola y el consumidor los saca.

    El productor va en su propio hilo a propósito: así generar el evento siguiente no frena al
    que está puntuando, que es lo que distingue un flujo de recorrer una lista.

    Con `rate` en eventos por segundo, el flujo llega a un ritmo parecido al de una fuente real.
    Sin ritmo, los eventos entran de golpe y una ventana por tiempo termina abarcándolos a todos.
    """

    def __init__(self, events: Iterable[Event], rate: float = 0.0, maxsize: int = 100) -> None:
        self.events = events
        self.rate = rate
        self.queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    def _produce(self) -> None:
        """Publica cada evento en la cola, al ritmo pedido, y avisa cuando se terminaron."""
        delay = 1 / self.rate if self.rate > 0 else 0.0
        for event in self.events:
            self.queue.put(event)
            if delay:
                time.sleep(delay)
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
