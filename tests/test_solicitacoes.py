import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.integration


def test_matricula_duplicada_retorna_mesma_solicitacao():
    client = TestClient(app)
    payload = {'aluno_id':'aluno-1','turma_id':'turma-1'}
    primeira = client.post('/matriculas', json=payload)
    segunda = client.post('/matriculas', json=payload)
    assert primeira.status_code == segunda.status_code == 202
    assert primeira.json()['id'] == segunda.json()['id']
    assert primeira.json()['status'] == 'SOLICITADA'


def test_historico_persistido():
    client = TestClient(app)
    body = {'disciplinas':['CAL1'],'coeficiente':8.5,'periodo_aluno':4}
    assert client.put('/alunos/aluno-1/historico', json=body).status_code == 200
    assert client.get('/alunos/aluno-1/historico').json()['disciplinas'] == ['CAL1']


def test_cancelamento_terminal():
    client = TestClient(app)
    r = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'})
    assert r.status_code == 202
    sid = r.json()['id']
    assert client.delete(f'/matriculas/{sid}').json()['status'] == 'CANCELADA'
    assert client.delete(f'/matriculas/{sid}').json()['status'] == 'CANCELADA'


def test_listagem_historico_e_evento_transacional(client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.db import get_engine
    from app.events import Outbox
    body = {'disciplinas':['A'],'coeficiente':9,'periodo_aluno':5}
    client.put('/alunos/a/historico', json=body)
    r = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()
    client.put('/alunos/a/historico', json={**body,'disciplinas':['A','B']})
    assert client.get('/alunos/a/historico').json()['disciplinas'] == ['A','B']
    assert client.get('/matriculas/me?aluno_id=a').json()[0]['id'] == r['id']
    assert client.get('/matriculas/me?aluno_id=b').json() == []
    assert client.get(f"/matriculas/{r['id']}").json()['status'] == 'SOLICITADA'
    assert client.get(f"/matriculas/{r['id']}/historico").json()[0]['status'] == 'SOLICITADA'
    with Session(get_engine()) as s:
        event = s.scalar(select(Outbox))
        assert event.topic == 'matricula.solicitada'
        assert event.payload['coeficiente'] == 9
        assert event.payload['periodo_aluno'] == 5


def aplicar(sid, resultado, revisao=1):
    from sqlalchemy.orm import Session
    from app.db import get_engine
    from app.handlers import handle_event
    with Session(get_engine()) as s, s.begin():
        handle_event(s, 'matricula.avaliada', {'solicitacao_id':sid, 'resultado':resultado, 'revisao':revisao, 'motivo':'SEM_VAGAS' if resultado == 'EM_ESPERA' else None})


def test_resultados_ordenados_e_cancelamento(client):
    sid = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()['id']
    aplicar(sid, 'EM_ESPERA')
    aplicar(sid, 'DEFERIDA', 2)
    aplicar(sid, 'EM_ESPERA', 1)
    assert client.get(f'/matriculas/{sid}').json()['status'] == 'DEFERIDA'
    assert len(client.get(f'/matriculas/{sid}/historico').json()) == 3
    assert client.delete(f'/matriculas/{sid}').json()['status'] == 'CANCELADA'
    aplicar(sid, 'DEFERIDA', 3)
    assert client.get(f'/matriculas/{sid}').json()['status'] == 'CANCELADA'
    novo = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()
    assert novo['id'] != sid


def test_indeferimento_terminal(client):
    sid = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()['id']
    aplicar(sid, 'INDEFERIDA')
    assert client.delete(f'/matriculas/{sid}').status_code == 409
    with pytest.raises(ValueError, match='Transicao invalida'):
        aplicar(sid, 'DEFERIDA', 2)


@pytest.mark.parametrize('resultado,revisao', [('INVALIDO',1),('DEFERIDA',0),('DEFERIDA','1')])
def test_resultado_invalido(client, resultado, revisao):
    sid = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()['id']
    with pytest.raises(ValueError, match='invalida'):
        aplicar(sid, resultado, revisao)


def test_evento_desconhecido_e_solicitacao_ausente():
    from sqlalchemy.orm import Session
    from app.db import get_engine
    from app.handlers import handle_event
    with Session(get_engine()) as s:
        with pytest.raises(ValueError, match='desconhecido'):
            handle_event(s, 'outro', {})
    with pytest.raises(ValueError, match='nao encontrada'):
        aplicar('ausente','DEFERIDA')


def test_recursos_ausentes(client):
    for path in ['/alunos/a/historico','/matriculas/a','/matriculas/a/historico']:
        assert client.get(path).status_code == 404
    assert client.delete('/matriculas/a').status_code == 404


@pytest.mark.parametrize('body', [{'disciplinas':['A','A']}, {'coeficiente':11}, {'coeficiente':-1}, {'periodo_aluno':0}])
def test_historico_invalido(client, body):
    assert client.put('/alunos/a/historico',json=body).status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize('origem,destino,valida', [
    ('SOLICITADA','DEFERIDA',True), ('SOLICITADA','EM_ESPERA',True),
    ('EM_ESPERA','DEFERIDA',True), ('EM_ESPERA','INDEFERIDA',True),
    ('DEFERIDA','CANCELADA',True), ('CANCELADA','DEFERIDA',False),
    ('INDEFERIDA','SOLICITADA',False), ('DESCONHECIDA','DEFERIDA',False)])
def test_maquina_de_estados(origem, destino, valida):
    from app.domain import validar_transicao
    if valida:
        validar_transicao(origem, destino)
    else:
        with pytest.raises(ValueError):
            validar_transicao(origem, destino)


def test_atualizacao_da_espera_nao_cria_transicao_duplicada(client):
    sid = client.post('/matriculas', json={'aluno_id':'a','turma_id':'t'}).json()['id']
    aplicar(sid, 'EM_ESPERA', 1)
    aplicar(sid, 'EM_ESPERA', 2)
    assert client.get(f'/matriculas/{sid}').json()['revisao'] == 2
    assert [x['status'] for x in client.get(f'/matriculas/{sid}/historico').json()] == ['SOLICITADA','EM_ESPERA']
