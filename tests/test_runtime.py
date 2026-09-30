import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from app.main import app
from app.config import get_settings


def test_readiness(client):
    assert client.get('/ready').status_code == 200


def test_readiness_indisponivel(client, monkeypatch):
    from app import api
    engine = create_engine('postgresql+psycopg://invalid:invalid@127.0.0.1:1/invalid', connect_args={'connect_timeout':1})
    monkeypatch.setattr(api, 'get_engine', lambda: engine)
    assert client.get('/ready').status_code == 503
    engine.dispose()


def test_lifespan_com_worker(monkeypatch):
    monkeypatch.setattr(get_settings(), 'worker_enabled', True)
    with TestClient(app) as c:
        assert c.get('/health').status_code == 200


def test_lifespan_sem_worker():
    with TestClient(app) as c:
        assert c.get('/health').status_code == 200
