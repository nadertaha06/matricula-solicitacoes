"""Prometheus metrics shared by the services: HTTP, messaging and post-commit increments.

The container runs a single uvicorn process and the messaging worker is a thread of it,
so the default prometheus_client registry is enough.
"""
import time
from prometheus_client import (CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram,
    disable_created_metrics, generate_latest)
from sqlalchemy import event
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.routing import Match, Route

# *_created series would double the series count without being used by the dashboards.
disable_created_metrics()

CAMINHO_METRICAS = "/metrics"
ROTA_NAO_MAPEADA = "nao_mapeada"
METODOS_HTTP = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
BUCKETS_HTTP = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

HTTP_REQUISICOES = Counter("http_requests_total", "Requisicoes HTTP atendidas.",
    ("method", "route", "status"))
HTTP_DURACAO = Histogram("http_request_duration_seconds", "Duracao das requisicoes HTTP.",
    ("method", "route"), buckets=BUCKETS_HTTP)
HTTP_EM_ANDAMENTO = Gauge("http_requests_em_andamento", "Requisicoes HTTP em andamento.")

MENSAGENS_CONSUMIDAS = Counter("mensagens_consumidas_total",
    "Mensagens consumidas do RabbitMQ por fila e resultado.", ("fila", "resultado"))
MENSAGENS_PUBLICADAS = Counter("mensagens_publicadas_total",
    "Eventos do outbox publicados com confirmacao do RabbitMQ.", ("topico",))
WORKER_CONECTADO = Gauge("worker_conectado", "1 enquanto o worker mantem conexao com o RabbitMQ.")


def caminho_relativo(scope):
    """Request path without the public prefix (root_path), as the router sees it."""
    caminho, raiz = scope.get("path", ""), scope.get("root_path", "")
    if raiz and caminho.startswith(raiz + "/"):
        return caminho[len(raiz):]
    return caminho


def rota_casada(scope):
    """Template of the matched route; requests without a route share one label value."""
    rota = scope.get("route")
    if rota is None:
        # FastAPI only sets scope["route"] for APIRoute; /docs and /openapi.json are plain Routes.
        for candidata in getattr(scope.get("router"), "routes", ()):
            if isinstance(candidata, Route) and candidata.matches(scope)[0] is Match.FULL:
                rota = candidata
                break
    return getattr(rota, "path", None) or ROTA_NAO_MAPEADA


class MetricasHTTP:
    """ASGI middleware: count, latency and concurrency by method, route template and status."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or caminho_relativo(scope) == CAMINHO_METRICAS:
            await self.app(scope, receive, send)
            return
        resposta = {"status": 500}  # an unhandled exception becomes a 500 in ServerErrorMiddleware

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                resposta["status"] = mensagem["status"]
            await send(mensagem)

        inicio = time.perf_counter()
        HTTP_EM_ANDAMENTO.inc()
        try:
            await self.app(scope, receive, enviar)
        finally:
            HTTP_EM_ANDAMENTO.dec()
            metodo = scope["method"] if scope["method"] in METODOS_HTTP else "OUTRO"
            rota = rota_casada(scope)
            HTTP_REQUISICOES.labels(method=metodo, route=rota, status=str(resposta["status"])).inc()
            HTTP_DURACAO.labels(method=metodo, route=rota).observe(time.perf_counter() - inicio)


def resposta_metricas():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


_PENDENTES = "metricas_apos_commit"


def apos_commit(session, incremento):
    """Run `incremento` only when the session's root transaction commits.

    Event handlers use it because worker.consume_one owns their COMMIT.
    A rollback, or closing the session without commit, discards it.
    """
    session.info.setdefault(_PENDENTES, []).append(incremento)


@event.listens_for(Session, "after_commit")
def _aplicar_pendentes(session):
    if session.get_nested_transaction() is not None:
        return  # releasing a SAVEPOINT does not commit the root transaction
    for incremento in session.info.pop(_PENDENTES, ()):
        incremento()


@event.listens_for(Session, "after_transaction_end")
def _descartar_pendentes(session, transaction):
    if transaction.parent is None:
        session.info.pop(_PENDENTES, None)
