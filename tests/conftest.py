import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.config import get_settings
from app.db import Base, get_engine, init_db
from app.main import app


@pytest.fixture(scope="session")
def database_schema():
    if not get_settings().db_name.endswith("_test"):
        pytest.fail("Use um DB_NAME terminado em _test; testes nunca limpam o banco da aplicacao")
    init_db()


@pytest.fixture(autouse=True)
def clean_database(request):
    if request.node.get_closest_marker("unit"):
        yield
        return
    request.getfixturevalue("database_schema")
    with get_engine().begin() as connection:
        tables = ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
        connection.execute(text("TRUNCATE " + tables + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client():
    return TestClient(app)
