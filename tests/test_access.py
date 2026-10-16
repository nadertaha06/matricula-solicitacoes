import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.unit
@pytest.mark.parametrize("method,path", [('get', '/matriculas/me'), ('get', '/matriculas/x'), ('delete', '/matriculas/x'), ('put', '/alunos/a/historico')])
def test_routes_require_authentication(method, path):
    assert getattr(TestClient(app), method)(path).status_code == 401

@pytest.fixture
def student_client():
    from app.auth import get_principal, Principal
    app.dependency_overrides[get_principal] = lambda: Principal('auth0|a', frozenset())
    yield TestClient(app)
    app.dependency_overrides.pop(get_principal, None)

def test_student_cannot_impersonate_or_write_history(student_client):
    c = student_client
    assert c.post('/matriculas', json={'aluno_id':'auth0|b','turma_id':'t'}).status_code == 403
    assert c.put('/alunos/auth0|a/historico', json={'coeficiente':10}).status_code == 403
    created = c.post('/matriculas', json={'turma_id':'t'})
    assert created.status_code == 202
    assert created.json()['aluno_id'] == 'auth0|a'
    assert c.get('/matriculas/me?aluno_id=auth0|b').json()[0]['id'] == created.json()['id']
    assert c.get('/matriculas').status_code == 403

def test_student_cannot_read_or_cancel_other_student(student_client):
    from app.auth import get_principal, Principal
    c = student_client
    own = c.post('/matriculas', json={'turma_id':'t'}).json()['id']
    app.dependency_overrides[get_principal] = lambda: Principal('auth0|b', frozenset())
    for path in [f'/matriculas/{own}', f'/matriculas/{own}/historico', '/alunos/auth0|a/historico']:
        assert c.get(path).status_code == 403
    assert c.delete(f'/matriculas/{own}').status_code == 403
    assert c.get('/matriculas/me').json() == []
