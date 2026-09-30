from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db import session_scope
from app.events import emit
from app.domain import validar_transicao
from app.models import Aluno, Solicitacao, HistoricoStatus
from app.schemas import HistoricoInput, SolicitacaoInput

router = APIRouter()


def view(s):
    return {'id':s.id,'aluno_id':s.aluno_id,'turma_id':s.turma_id,'status':s.status,'motivo':s.motivo,
            'revisao':s.revisao,'solicitado_em':s.solicitado_em.isoformat()}


@router.put('/alunos/{aluno_id}/historico')
def salvar_historico(data: HistoricoInput, aluno_id: str = Path(min_length=1, max_length=150), session: Session = Depends(session_scope)):
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
def obter_historico(aluno_id: str, session: Session = Depends(session_scope)):
    aluno = session.get(Aluno, aluno_id)
    if aluno is None:
        raise HTTPException(404, 'Aluno nao encontrado')
    return {'aluno_id':aluno_id,'disciplinas':aluno.disciplinas,'coeficiente':aluno.coeficiente,'periodo_aluno':aluno.periodo_aluno}


@router.post('/matriculas', status_code=202)
def solicitar(data: SolicitacaoInput, session: Session = Depends(session_scope)):
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
    return view(solicitacao)


@router.get('/matriculas/me')
def minhas_matriculas(aluno_id: str = Query(min_length=1), session: Session = Depends(session_scope)):
    # Explicit demo identity in stage 2. Stage 3 must derive identity from Auth0 sub.
    return [view(s) for s in session.scalars(select(Solicitacao).where(Solicitacao.aluno_id == aluno_id).order_by(Solicitacao.solicitado_em))]


@router.get('/matriculas/{solicitacao_id}')
def obter(solicitacao_id: str, session: Session = Depends(session_scope)):
    s = session.get(Solicitacao, solicitacao_id)
    if s is None:
        raise HTTPException(404, 'Solicitacao nao encontrada')
    return view(s)


@router.get('/matriculas/{solicitacao_id}/historico')
def historico_status(solicitacao_id: str, session: Session = Depends(session_scope)):
    obter(solicitacao_id, session)
    return [{'status':h.status,'motivo':h.motivo,'ocorrido_em':h.ocorrido_em.isoformat()}
        for h in session.scalars(select(HistoricoStatus).where(HistoricoStatus.solicitacao_id == solicitacao_id).order_by(HistoricoStatus.ocorrido_em))]


@router.delete('/matriculas/{solicitacao_id}')
def cancelar(solicitacao_id: str, session: Session = Depends(session_scope)):
    s = session.scalar(select(Solicitacao).where(Solicitacao.id == solicitacao_id).with_for_update())
    if s is None:
        raise HTTPException(404, 'Solicitacao nao encontrada')
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
    return view(s)
