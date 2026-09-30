import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import get_settings


@pytest.mark.unit
def test_swagger_usa_prefixo_publico(monkeypatch):
    monkeypatch.setenv('ROOT_PATH', '/servico')
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(APIRouter(), None))
        assert '/servico/openapi.json' in client.get('/docs').text
        assert client.get('/openapi.json').json()['servers'] == [{'url':'/servico'}]
        assert client.get('/health').status_code == 200
    finally:
        get_settings.cache_clear()
