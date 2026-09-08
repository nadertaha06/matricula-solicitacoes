from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Servico de solicitacoes de matricula",
    version="0.1.0",
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Identifica o servico."""
    return {"service": settings.app_name}


@app.get("/health")
def health() -> dict[str, str]:
    """Healthcheck usado pelo Docker e pelo deploy."""
    return {"status": "ok", "service": settings.app_name}
