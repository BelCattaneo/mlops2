"""Mini-TP 4: de dónde salen los eventos que se puntúan.

Una fuente es cualquier cosa que se pueda recorrer y entregue reportes. El consumidor no sabe
cuál está usando: con eso, el mismo scoring corre contra una cola en memoria o contra un broker.

`kafka-python` se importa recién cuando se usa el broker, así que la cola en memoria funciona
en un entorno donde el grupo `streaming` no esté instalado.
"""

import json
import queue
import socket
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
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


TOPIC = "arrest-events"
SERVERS = ("localhost:9092",)


def broker_available(servers: Sequence[str] = SERVERS) -> bool:
    """Dice si hay un broker aceptando conexiones, para saltear lo que lo necesita."""
    host, _, port = servers[0].partition(":")
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) == 0


def publish(
    events: Iterable[Event],
    topic: str = TOPIC,
    servers: Sequence[str] = SERVERS,
    rate: float = 0.0,
) -> int:
    """Publica los eventos en el topic y devuelve cuántos mandó.

    Con `rate` en eventos por segundo, los publica a ese ritmo: así el consumidor lee mientras
    el productor sigue emitiendo, que es como se comporta un flujo de verdad.
    """
    from kafka import KafkaProducer

    producer = KafkaProducer(
        bootstrap_servers=list(servers),
        value_serializer=lambda event: json.dumps(event).encode(),
    )
    delay = 1 / rate if rate > 0 else 0.0
    published = 0
    for event in events:
        producer.send(topic, event)
        published += 1
        if delay:
            producer.flush()
            time.sleep(delay)
    producer.flush()
    producer.close()
    return published


class KafkaSource:
    """Fuente sobre un topic de Kafka, que es el camino de producción.

    Entrega lo mismo que `QueueSource`, así que el consumidor no cambia. Lee desde el principio
    del topic, sin grupo de consumidores: cada corrida es un lector nuevo, que es lo que hace
    falta para un ejemplo repetible. Corta cuando pasa `timeout_ms` sin mensajes nuevos, porque
    en producción el consumo no termina pero un notebook tiene que terminar.
    """

    def __init__(
        self,
        topic: str = TOPIC,
        servers: Sequence[str] = SERVERS,
        timeout_ms: int = 10_000,
    ) -> None:
        self.topic = topic
        self.servers = servers
        self.timeout_ms = timeout_ms

    def __iter__(self) -> Iterator[Event]:
        """Consume el topic y entrega cada mensaje ya decodificado."""
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            self.topic,
            bootstrap_servers=list(self.servers),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=self.timeout_ms,
            value_deserializer=json.loads,
        )
        try:
            for message in consumer:
                yield message.value
        finally:
            consumer.close()
