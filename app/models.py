from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base, new_id


class Aluno(Base):
    __tablename__ = 'aluno'
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    disciplinas: Mapped[list] = mapped_column(JSON, default=list)
    coeficiente: Mapped[float] = mapped_column(Float, default=0)
    periodo_aluno: Mapped[int] = mapped_column(Integer, default=1)


class Solicitacao(Base):
    __tablename__ = 'solicitacao'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aluno_id: Mapped[str] = mapped_column(ForeignKey('aluno.id'), index=True)
    turma_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default='SOLICITADA')
    motivo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revisao: Mapped[int] = mapped_column(Integer, default=0)
    solicitado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class HistoricoStatus(Base):
    __tablename__ = 'historico_status'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    solicitacao_id: Mapped[str] = mapped_column(ForeignKey('solicitacao.id'), index=True)
    status: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
