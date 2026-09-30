import json
import time
from uuid import uuid4
import pytest
import pika
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.broker import Broker, BINDINGS
from app.config import get_settings
from app.db import get_engine
from app.events import emit, Outbox, Inbox
from app.worker import Worker, flush_outbox, consume_one

pytestmark = pytest.mark.integration


@pytest.fixture
def broker():
    # Refuse to purge any application vhost, even if credentials were misconfigured.
    assert "test" in pika.URLParameters(get_settings().rabbitmq_url).virtual_host
    b = Broker()
    for name in BINDINGS:
        for suffix in ("", ".retry"):
            b.channel.queue_purge("matriculas." + name + suffix)
    b.channel.queue_purge("matriculas.dlq")
    yield b
    b.close()
    b.close()  # repeated shutdown is harmless


def test_outbox_publica_no_broker_real(broker):
    with Session(get_engine()) as s, s.begin():
        eid = emit(s, "matricula.solicitada", {"solicitacao_id":"s1"})
    assert flush_outbox(broker)
    assert not flush_outbox(broker)
    method, _, body = broker.receive("matriculas.processamento")
    assert json.loads(body)["evento_id"] == eid
    broker.channel.basic_ack(method.delivery_tag)
    with Session(get_engine()) as s:
        assert s.scalar(select(func.count()).select_from(Outbox)) == 0


def test_rollback_nao_publica_evento(broker):
    with Session(get_engine()) as s:
        emit(s, "matricula.solicitada", {"solicitacao_id":"nao-confirmada"})
        s.flush()
        s.rollback()
    assert not flush_outbox(broker)
    assert broker.receive("matriculas.processamento")[0] is None


def test_inbox_descarta_duplicata(broker, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_name", "matricula-solicitacoes")
    eid = str(uuid4())
    payload = {"evento_id":eid}
    for _ in range(2):
        broker.publish("matricula.avaliada", payload)
    def handler(s, topic, p):
        emit(s, "matricula.solicitada", {"origem":p["evento_id"]})
    assert consume_one(broker, handler)
    assert consume_one(broker, handler)
    assert not consume_one(broker, handler)
    with Session(get_engine()) as s:
        assert s.get(Inbox, eid) is not None
        assert s.scalar(select(func.count()).select_from(Outbox)) == 1
    monkeypatch.setattr(get_settings(), "app_name", "matricula-disciplinas")
    assert not consume_one(broker, handler)


def test_mensagem_invalida_chega_na_dlq_apos_tres_tentativas(broker, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_name", "matricula-solicitacoes")
    broker.publish("matricula.avaliada", {"evento_id":""})
    deadline = time.monotonic() + 12
    delivered = 0
    while time.monotonic() < deadline:
        delivered += bool(consume_one(broker, None))
        method, properties, body = broker.receive("matriculas.dlq")
        if method:
            assert delivered == 3
            assert properties.headers["tentativas"] == 3
            assert properties.headers["original_topic"] == "matricula.avaliada"
            assert json.loads(body) == {"evento_id":""}
            broker.channel.basic_ack(method.delivery_tag)
            return
        time.sleep(.1)
    pytest.fail("Mensagem nao chegou a DLQ")


def test_worker_publica_pendente_e_encerra(broker, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_name", "matricula-disciplinas")
    with Session(get_engine()) as s, s.begin():
        eid = emit(s, "matricula.solicitada", {"solicitacao_id":"background"})
    worker = Worker(None)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            method, _, body = broker.receive("matriculas.processamento")
            if method:
                assert json.loads(body)["evento_id"] == eid
                broker.channel.basic_ack(method.delivery_tag)
                break
            time.sleep(.1)
        else:
            pytest.fail("Worker nao publicou")
    finally:
        worker.stop()
    assert not worker.thread.is_alive()


def test_indisponibilidade_preserva_outbox(monkeypatch):
    monkeypatch.setattr(get_settings(), "rabbitmq_url", "amqp://guest:guest@127.0.0.1:1/")
    with Session(get_engine()) as s, s.begin():
        emit(s, "matricula.solicitada", {"solicitacao_id":"pendente"})
    worker = Worker(None)
    worker.start()
    time.sleep(.2)
    worker.stop()
    with Session(get_engine()) as s:
        assert s.scalar(select(func.count()).select_from(Outbox)) == 1
    assert not worker.thread.is_alive()
