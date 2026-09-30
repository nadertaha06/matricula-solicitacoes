from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints, model_validator

Identificador = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Codigo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class HistoricoInput(BaseModel):
    disciplinas: list[Codigo] = Field(default_factory=list, max_length=200)
    coeficiente: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    periodo_aluno: int = Field(default=1, ge=1, le=30)

    @model_validator(mode='after')
    def validar(self):
        if len(set(self.disciplinas)) != len(self.disciplinas):
            raise ValueError('Disciplinas repetidas')
        return self


class SolicitacaoInput(BaseModel):
    aluno_id: Identificador
    turma_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)]
