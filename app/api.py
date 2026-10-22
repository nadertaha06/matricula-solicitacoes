from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db import init_db, get_engine
from app.worker import Worker
from app.auth import get_principal
from app.metrics import MetricasHTTP, resposta_metricas


def create_app(router, handler):
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app):
        init_db()
        worker = Worker(handler) if settings.worker_enabled else None
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan, root_path=settings.root_path,
        description="Portal de matricula com autenticacao Auth0 e permissoes por operacao.")
    app.add_middleware(MetricasHTTP)
    app.include_router(router)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        # Public gateway blocks /metrics; Prometheus scrapes it over the internal Docker network.
        return resposta_metricas()

    @app.get("/session")
    def session_info(principal=Depends(get_principal)):
        return {"sub": principal.sub, "permissions": sorted(principal.permissions)}

    @app.get("/")
    def root():
        return {"service": settings.app_name}

    @app.get("/health")
    def health():
        return {"status": "ok", "service": settings.app_name}

    @app.get("/ready")
    def ready():
        try:
            with Session(get_engine()) as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(503, "Banco indisponivel") from exc
        return {"status": "ready", "service": settings.app_name}

    return app
