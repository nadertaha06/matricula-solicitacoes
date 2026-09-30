"""Durable topic queues, publisher confirms and bounded retry with a DLQ."""
import json
import pika
from app.config import get_settings

BINDINGS = {
    "processamento": ("matricula.solicitada", "matricula.cancelada", "vaga.liberada", "lista.reavaliar"),
    "solicitacoes": ("matricula.avaliada",),
}


class Broker:
    def __init__(self):
        params = pika.URLParameters(get_settings().rabbitmq_url)
        params.socket_timeout = 5
        params.blocked_connection_timeout = 5
        params.connection_attempts = 1
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange="matriculas", exchange_type="topic", durable=True)
        self.channel.queue_declare(queue="matriculas.dlq", durable=True)
        for name, topics in BINDINGS.items():
            queue = "matriculas." + name
            self.channel.queue_declare(queue=queue, durable=True)
            self.channel.queue_declare(queue=queue + ".retry", durable=True, arguments={
                "x-message-ttl": get_settings().retry_delay_ms,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": queue,
            })
            for topic in topics:
                self.channel.queue_bind(exchange="matriculas", queue=queue, routing_key=topic)
        self.channel.confirm_delivery()
        self.channel.basic_qos(prefetch_count=1)

    def publish(self, topic, payload):
        self.channel.basic_publish(exchange="matriculas", routing_key=topic,
            body=json.dumps(payload), mandatory=True,
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"))

    def receive(self, queue):
        return self.channel.basic_get(queue=queue, auto_ack=False)

    def retry(self, queue, method, properties, body):
        headers = dict(properties.headers or {})
        attempts = int(headers.get("tentativas", 0)) + 1
        headers["tentativas"] = attempts
        headers["original_topic"] = headers.get("original_topic", method.routing_key)
        destination = "matriculas.dlq" if attempts >= 3 else queue + ".retry"
        self.channel.basic_publish(exchange="", routing_key=destination, body=body, mandatory=True,
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json", headers=headers))
        self.channel.basic_ack(method.delivery_tag)

    def close(self):
        if self.connection.is_open:
            self.connection.close()
