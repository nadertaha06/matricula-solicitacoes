"""One connection per worker; retryable delivery with persistent outbox/inbox."""
import json
import logging
from threading import Event, Thread
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.broker import Broker, BINDINGS, DLQ
from app.config import get_settings
from app.db import get_engine
from app.events import Outbox, Inbox
from app.metrics import MENSAGENS_CONSUMIDAS, MENSAGENS_PUBLICADAS, WORKER_CONECTADO

logger = logging.getLogger(__name__)


def flush_outbox(broker):
    with Session(get_engine()) as session, session.begin():
        event = session.scalar(select(Outbox).order_by(Outbox.created_at).with_for_update(skip_locked=True).limit(1))
        if event is None:
            return False
        topico = event.topic
        broker.publish(topico, event.payload)
        session.delete(event)
    # Counted only after the broker confirm and the commit that removes the outbox row.
    MENSAGENS_PUBLICADAS.labels(topico=topico).inc()
    return True


def consume_one(broker, handler):
    name = get_settings().app_name.removeprefix("matricula-")
    if name not in BINDINGS:
        return False
    queue = "matriculas." + name
    method, properties, body = broker.receive(queue)
    if method is None:
        return False
    try:
        payload = json.loads(body)
        event_id = payload["evento_id"]
        if not isinstance(event_id, str) or not event_id or len(event_id) > 36:
            raise ValueError("evento_id invalido")
        topic = (properties.headers or {}).get("original_topic", method.routing_key)
        with Session(get_engine()) as session, session.begin():
            # Serialize domain evaluations, including duplicate delivery, across workers.
            session.execute(text("SELECT pg_advisory_xact_lock(220926)"))
            duplicada = session.get(Inbox, event_id) is not None
            if not duplicada:
                handler(session, topic, payload)
                session.add(Inbox(id=event_id))
        broker.channel.basic_ack(method.delivery_tag)
        resultado = "duplicada" if duplicada else "processada"
    except Exception:
        logger.exception("Falha no consumo; nova tentativa ou DLQ")
        resultado = "dlq" if broker.retry(queue, method, properties, body) == DLQ else "retentativa"
    MENSAGENS_CONSUMIDAS.labels(fila=queue, resultado=resultado).inc()
    return True


class Worker:
    def __init__(self, handler):
        self.handler = handler
        self.stop_event = Event()
        self.thread = Thread(target=self.run, name="event-worker", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=15)

    def run(self):
        while not self.stop_event.is_set():
            broker = None
            try:
                broker = Broker()
                WORKER_CONECTADO.set(1)
                while not self.stop_event.is_set():
                    published = flush_outbox(broker)
                    consumed = consume_one(broker, self.handler)
                    broker.connection.process_data_events(time_limit=0)
                    if not published and not consumed:
                        self.stop_event.wait(0.2)
            except Exception:
                logger.exception("Worker indisponivel; reconectando")
            finally:
                WORKER_CONECTADO.set(0)
                if broker is not None:
                    try:
                        broker.close()
                    except Exception:
                        logger.exception("Erro ao fechar broker")
            # The inner loop only ends on failure or stop; after stop this returns at once.
            self.stop_event.wait(2)
