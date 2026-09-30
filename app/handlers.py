from sqlalchemy import select
from app.domain import validar_transicao
from app.models import Solicitacao, HistoricoStatus


def handle_event(session, topic, payload):
    if topic != 'matricula.avaliada':
        raise ValueError('Evento desconhecido')
    resultado = payload['resultado']
    revisao = payload['revisao']
    if resultado not in {'DEFERIDA', 'INDEFERIDA', 'EM_ESPERA'} or not isinstance(revisao, int) or revisao < 1:
        raise ValueError('Resultado ou revisao invalida')
    solicitacao = session.scalar(select(Solicitacao).where(Solicitacao.id == payload['solicitacao_id']).with_for_update())
    if solicitacao is None:
        raise ValueError('Solicitacao nao encontrada')
    # Cancellation is terminal. Old/out-of-order results must never resurrect a seat.
    if solicitacao.status == 'CANCELADA' or revisao <= solicitacao.revisao:
        return
    if solicitacao.status == resultado:
        # A newer evaluation can update the waiting reason without a new state transition.
        solicitacao.motivo = payload.get('motivo')
        solicitacao.revisao = revisao
        return
    validar_transicao(solicitacao.status, resultado)
    solicitacao.status = resultado
    solicitacao.motivo = payload.get('motivo')
    solicitacao.revisao = revisao
    session.add(HistoricoStatus(solicitacao_id=solicitacao.id, status=resultado, motivo=solicitacao.motivo))
