from fastapi.testclient import TestClient
from app.main import app


def test_solicitacao_assincrona():
    response = TestClient(app).post('/matriculas', json={'aluno_id': 'aluno-1', 'turma_id': 'turma-1'})
    assert response.status_code == 202
