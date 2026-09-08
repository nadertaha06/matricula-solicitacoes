from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracao do servico, lida de variaveis de ambiente ou de um .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "matricula-solicitacoes"
    port: int = 8002

    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "solicitacoes_db"
    db_user: str = "postgres"
    db_password: str = ""

    rabbitmq_url: str = ""

    auth0_domain: str = ""
    auth0_audience: str = ""


# Padrao Singleton exigido pelo trabalho: o @lru_cache faz com que get_settings()
# construa Settings uma unica vez e devolva sempre a MESMA instancia para todo o
# processo, em vez de reler o ambiente a cada chamada.
@lru_cache
def get_settings() -> Settings:
    return Settings()
