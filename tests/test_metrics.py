import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api import create_app
from app.config import get_settings
from app.db import get_engine
from app.main import app
from app.metrics import apos_commit


def valor(nome, **labels):
    # The registry is global: tests compare deltas, never absolute values.
    return REGISTRY.get_sample_value(nome, labels) or 0.0


def requisicoes(method, route, status):
    return valor('http_requests_total', method=method, route=route, status=status)


@pytest.fixture
def client_teste():
    router = APIRouter()

    @router.get('/itens/{item_id}')
    def item(item_id: str):
        if item_id == 'falha':
            raise RuntimeError('falha simulada')
        return {'id': item_id}

    @router.get('/em-andamento')
    def em_andamento():
        return {'valor': REGISTRY.get_sample_value('http_requests_em_andamento')}

    return TestClient(create_app(router, None), raise_server_exceptions=False)


@pytest.mark.unit
def test_metrics_expoe_formato_prometheus_sem_autenticacao():
    # A fresh app has no dependency overrides: /metrics must not require credentials.
    response = TestClient(create_app(APIRouter(), None)).get('/metrics')
    assert response.status_code == 200
    assert response.headers['content-type'] == CONTENT_TYPE_LATEST
    for linha in ['# TYPE http_requests_total counter', '# TYPE http_request_duration_seconds histogram',
                  '# TYPE http_requests_em_andamento gauge', '# TYPE mensagens_consumidas_total counter',
                  '# TYPE mensagens_publicadas_total counter', '# TYPE worker_conectado gauge']:
        assert linha in response.text
    assert '/metrics' not in TestClient(app).get('/openapi.json').json()['paths']


@pytest.mark.unit
def test_middleware_usa_template_da_rota(client_teste):
    antes = requisicoes('GET', '/itens/{item_id}', '200')
    duracao = valor('http_request_duration_seconds_count', method='GET', route='/itens/{item_id}')
    assert client_teste.get('/itens/1').status_code == 200
    assert client_teste.get('/itens/2').status_code == 200
    assert requisicoes('GET', '/itens/{item_id}', '200') - antes == 2
    assert valor('http_request_duration_seconds_count', method='GET', route='/itens/{item_id}') - duracao == 2
    assert REGISTRY.get_sample_value('http_requests_total', {'method': 'GET', 'route': '/itens/1', 'status': '200'}) is None


@pytest.mark.unit
def test_middleware_agrupa_rotas_nao_mapeadas(client_teste):
    antes = requisicoes('GET', 'nao_mapeada', '404')
    assert client_teste.get('/nao-existe/123').status_code == 404
    assert client_teste.get('/outra-rota').status_code == 404
    assert requisicoes('GET', 'nao_mapeada', '404') - antes == 2


@pytest.mark.unit
def test_middleware_registra_status_de_erro_metodo_e_docs(client_teste):
    antes = {
        'erro': requisicoes('GET', '/itens/{item_id}', '500'),
        'metodo': requisicoes('DELETE', '/itens/{item_id}', '405'),
        'outro': requisicoes('OUTRO', '/itens/{item_id}', '405'),
        'docs': requisicoes('GET', '/docs', '200'),
    }
    assert client_teste.get('/itens/falha').status_code == 500
    assert client_teste.delete('/itens/1').status_code == 405
    assert client_teste.request('PROPFIND', '/itens/1').status_code == 405
    assert client_teste.get('/docs').status_code == 200
    assert requisicoes('GET', '/itens/{item_id}', '500') - antes['erro'] == 1
    assert requisicoes('DELETE', '/itens/{item_id}', '405') - antes['metodo'] == 1
    assert requisicoes('OUTRO', '/itens/{item_id}', '405') - antes['outro'] == 1
    assert requisicoes('GET', '/docs', '200') - antes['docs'] == 1


@pytest.mark.unit
def test_middleware_conta_requisicoes_em_andamento(client_teste):
    antes = valor('http_requests_em_andamento')
    assert client_teste.get('/em-andamento').json()['valor'] >= antes + 1
    assert valor('http_requests_em_andamento') == antes


@pytest.mark.unit
def test_metrics_nao_instrumenta_a_si_mesmo(monkeypatch, client_teste):
    health = requisicoes('GET', '/health', '200')
    assert client_teste.get('/metrics').status_code == 200
    monkeypatch.setenv('ROOT_PATH', '/servico')
    get_settings.cache_clear()
    try:
        prefixado = TestClient(create_app(APIRouter(), None))
        assert prefixado.get('/servico/metrics').status_code == 200
        assert prefixado.get('/metrics').status_code == 200
        assert prefixado.get('/servico/health').status_code == 200
    finally:
        get_settings.cache_clear()
    assert REGISTRY.get_sample_value('http_requests_total', {'method': 'GET', 'route': '/metrics', 'status': '200'}) is None
    assert requisicoes('GET', '/health', '200') - health == 1


class Contador:
    def __init__(self):
        self.total = 0

    def __call__(self):
        self.total += 1


@pytest.mark.integration
def test_incremento_aguarda_commit_da_transacao_raiz():
    contador = Contador()
    with Session(get_engine()) as session, session.begin():
        apos_commit(session, contador)
        savepoint = session.begin_nested()
        apos_commit(session, contador)
        savepoint.commit()
        assert contador.total == 0
    assert contador.total == 2


@pytest.mark.integration
def test_rollback_ou_sessao_sem_commit_descartam_incremento():
    contador = Contador()
    with Session(get_engine()) as session:
        session.execute(text('SELECT 1'))
        apos_commit(session, contador)
        session.rollback()
        session.commit()
        session.execute(text('SELECT 1'))
        apos_commit(session, contador)
    with Session(get_engine()) as session:
        session.commit()
    assert contador.total == 0
