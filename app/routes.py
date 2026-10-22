from fastapi import APIRouter, Depends, HTTPException, Query, Path
from prometheus_client import Counter
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db import session_scope
from app.events import emit
from app.domain import validar_transicao
from app.models import Aluno, Solicitacao, HistoricoStatus
from app.schemas import HistoricoInput, SolicitacaoInput

from app.auth import Principal, get_principal, require_permission, require_internal, check_owner

router = APIRouter(dependencies=[Depends(get_principal)])

# Counted after COMMIT; idempotent repetitions are not counted again.
MATRICULAS_SOLICITADAS = Counter('matriculas_solicitadas_total', 'Novas solicitacoes de matricula aceitas.')
MATRICULAS_CANCELADAS = Counter('matriculas_canceladas_total', 'Solicitacoes de matricula canceladas.')


def view(s):
    return {'id':s.id,'aluno_id':s.aluno_id,'turma_id':s.turma_id,'status':s.status,'motivo':s.motivo,
            'revisao':s.revisao,'solicitado_em':s.solicitado_em.isoformat()}


@router.put('/alunos/{aluno_id}/historico', dependencies=[Depends(require_permission('manage:historicos'))])
def salvar_historico(data: HistoricoInput, aluno_id: str = Path(min_length=1, max_length=150), session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:aluno, 0))'), {'aluno': aluno_id})
    aluno = session.get(Aluno, aluno_id)
    if aluno is None:
        aluno = Aluno(id=aluno_id)
        session.add(aluno)
    for key, value in data.model_dump().items():
        setattr(aluno, key, value)
    session.commit()
    return {'aluno_id':aluno_id, **data.model_dump()}


@router.get('/alunos/{aluno_id}/historico')
def obter_historico(aluno_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    check_owner(principal, aluno_id, 'manage:historicos', allow_internal=True)
    aluno = session.get(Aluno, aluno_id)
    if aluno is None:
        raise HTTPException(404, 'Aluno nao encontrado')
    return {'aluno_id':aluno_id,'disciplinas':aluno.disciplinas,'coeficiente':aluno.coeficiente,'periodo_aluno':aluno.periodo_aluno}


@router.post('/matriculas', status_code=202)
def solicitar(data: SolicitacaoInput, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    owner = data.aluno_id or principal.sub
    check_owner(principal, owner)
    data = data.model_copy(update={'aluno_id': owner})
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:aluno, 0))'), {'aluno':data.aluno_id})
    existente = session.scalar(select(Solicitacao).where(Solicitacao.aluno_id == data.aluno_id, Solicitacao.turma_id == data.turma_id,
        Solicitacao.status.in_(['SOLICITADA','EM_ESPERA','DEFERIDA'])))
    if existente:
        return view(existente)
    aluno = session.get(Aluno, data.aluno_id)
    if aluno is None:
        aluno = Aluno(id=data.aluno_id)
        session.add(aluno)
        session.flush()
    solicitacao = Solicitacao(**data.model_dump())
    session.add(solicitacao)
    session.flush()
    session.add(HistoricoStatus(solicitacao_id=solicitacao.id, status='SOLICITADA'))
    emit(session, 'matricula.solicitada', {'solicitacao_id':solicitacao.id, **data.model_dump(),
        'coeficiente':aluno.coeficiente,'periodo_aluno':aluno.periodo_aluno,'solicitado_em':solicitacao.solicitado_em.isoformat()})
    session.commit()
    MATRICULAS_SOLICITADAS.inc()
    return view(solicitacao)


@router.get('/matriculas', dependencies=[Depends(require_permission('manage:matriculas'))])
def listar_matriculas(session: Session = Depends(session_scope)):
    return [view(s) for s in session.scalars(select(Solicitacao).order_by(Solicitacao.solicitado_em.desc()).limit(500))]


@router.get('/matriculas/me')
def minhas_matriculas(aluno_id: str | None = Query(default=None, min_length=1), session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    aluno_id = aluno_id if aluno_id and principal.has('manage:matriculas') else principal.sub
    check_owner(principal, aluno_id)
    return [view(s) for s in session.scalars(select(Solicitacao).where(Solicitacao.aluno_id == aluno_id).order_by(Solicitacao.solicitado_em))]


@router.get('/matriculas/{solicitacao_id}')
def obter(solicitacao_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    s = session.get(Solicitacao, solicitacao_id)
    if s is None:
        raise HTTPException(404, 'Solicitacao nao encontrada')
    check_owner(principal, s.aluno_id, allow_internal=True)
    return view(s)


@router.get('/matriculas/{solicitacao_id}/historico')
def historico_status(solicitacao_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    obter(solicitacao_id, session, principal)
    return [{'status':h.status,'motivo':h.motivo,'ocorrido_em':h.ocorrido_em.isoformat()}
        for h in session.scalars(select(HistoricoStatus).where(HistoricoStatus.solicitacao_id == solicitacao_id).order_by(HistoricoStatus.ocorrido_em))]


@router.delete('/matriculas/{solicitacao_id}')
def cancelar(solicitacao_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    s = session.scalar(select(Solicitacao).where(Solicitacao.id == solicitacao_id).with_for_update())
    if s is None:
        raise HTTPException(404, 'Solicitacao nao encontrada')
    check_owner(principal, s.aluno_id)
    if s.status == 'CANCELADA':
        return view(s)
    try:
        validar_transicao(s.status, 'CANCELADA')
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    s.status = 'CANCELADA'
    s.motivo = None
    session.add(HistoricoStatus(solicitacao_id=s.id, status='CANCELADA'))
    emit(session, 'matricula.cancelada', {'solicitacao_id':s.id,'turma_id':s.turma_id,'aluno_id':s.aluno_id})
    session.commit()
    MATRICULAS_CANCELADAS.inc()
    return view(s)
