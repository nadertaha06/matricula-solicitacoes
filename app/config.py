from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "matricula-solicitacoes"
    port: int = 8002
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "solicitacoes_db"
    db_user: str = "postgres"
    db_password: str = ""
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    root_path: str = ""
    worker_enabled: bool = True
    retry_delay_ms: int = 1000
    disciplinas_url: str = "http://matricula-disciplinas:8001"
    solicitacoes_url: str = "http://matricula-solicitacoes:8002"
    criterio_desempate: str = "coeficiente"
    auth0_domain: str = ""
    auth0_audience: str = ""

    @property
    def database_url(self):
        return URL.create("postgresql+psycopg", username=self.db_user, password=self.db_password,
            host=self.db_host, port=self.db_port, database=self.db_name)


@lru_cache
def get_settings():
    return Settings()
