from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

client = TestClient(app)


def test_health_retorna_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "matricula-solicitacoes"}


def test_root_retorna_nome_do_servico():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "matricula-solicitacoes"}


def test_get_settings_e_singleton():
    # O @lru_cache precisa devolver sempre a mesma instancia.
    assert get_settings() is get_settings()
    assert isinstance(get_settings(), Settings)


def test_settings_tem_os_defaults_do_servico():
    settings = get_settings()

    assert settings.app_name == "matricula-solicitacoes"
    assert settings.port == 8002
    assert settings.db_name == "solicitacoes_db"
