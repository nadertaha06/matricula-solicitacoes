# matricula-solicitacoes

Solicitacoes de matricula, historico academico e historico das transicoes de estado.

[![CI/CD](https://github.com/nadertaha06/matricula-solicitacoes/actions/workflows/deploy.yml/badge.svg)](https://github.com/nadertaha06/matricula-solicitacoes/actions/workflows/deploy.yml)

Implementacao da **etapa 2** em Python 3.12, FastAPI, PostgreSQL e RabbitMQ.
Este repositorio e um dos tres servicos independentes do sistema.

## Executar a aplicacao completa

Clone os quatro repositorios na mesma pasta e siga o [README da infraestrutura](https://github.com/nadertaha06/matricula-infra).
O comando de demonstracao verifica os tres servicos por HTTP e acompanha os resultados produzidos pelo RabbitMQ:

```sh
python3 ../matricula-infra/scripts/smoke_e2e.py --host 127.0.0.1
```

Swagger: `http://localhost:8002/docs`. OpenAPI: `/openapi.json`.
`GET /health` verifica o processo; `GET /ready` consulta o PostgreSQL.
A prontidao HTTP nao substitui a verificacao da fila: o teste E2E cobre os workers.

## Endpoints

| Rota | Funcao |
|---|---|
| PUT /alunos/{id}/historico | Define disciplinas cursadas, coeficiente e periodo_aluno |
| GET /alunos/{id}/historico | Consulta o registro academico |
| POST /matriculas | Recebe aluno_id/turma_id, persiste e responde 202 |
| GET /matriculas/me?aluno_id=... | Consulta as solicitacoes do aluno de demonstracao |
| GET /matriculas/{id} | Consulta o estado atual |
| GET /matriculas/{id}/historico | Consulta a trilha de estados |
| DELETE /matriculas/{id} | Cancela e agenda a liberacao de vaga |

Horarios usam `dia_semana` de 0 (segunda) a 6 (domingo), `inicio` e `fim` no formato `HH:MM`.
Intervalos adjacentes nao conflitam, e o conflito de matricula se limita ao mesmo periodo letivo.

## Testes e cobertura

Instale as dependencias de desenvolvimento:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
```

Para rodar a suite completa, use **PostgreSQL e RabbitMQ reais**, com banco e vhost exclusivos de teste:

```sh
export DB_HOST=localhost DB_PORT=5432 DB_NAME=solicitacoes_test
export DB_USER=postgres DB_PASSWORD=postgres
export RABBITMQ_URL=amqp://tests:tests@localhost:5672/etapa2-tests
export WORKER_ENABLED=false
python -m pytest
```

Os testes se recusam a limpar bancos cujo nome nao termina em `_test` ou filas fora de um vhost de teste.
A infraestrutura de teste reproduzivel esta em `matricula-infra/compose.test.yml`.
Os testes de regras isoladas podem ser executados com `python -m pytest -m unit -o addopts=''`.

O `pytest-cov` usa o motor [coverage.py](https://coverage.readthedocs.io/) para medir linhas **e branches**.
Essa e a funcao equivalente a cobertura oferecida pelo JaCoCo para Java; nao e um painel simulado.
O limite de **80% por servico** e aplicado por `--cov-fail-under=80` e bloqueia o deploy quando descumprido.
Nenhum modulo de `app/` e retirado da medicao.

Saidas geradas:

- `coverage/index.html`: relatorio oficial navegavel por arquivo e linha.
- `coverage.xml` e `coverage.json`: dados legiveis por ferramentas e pelo CI.
- `reports/junit.xml`: resultados dos testes executados.

Esses arquivos nao sao versionados. Em **Actions > execucao > Summary** ha a tabela medida; o artefato `testes-solicitacoes-<SHA>` contem HTML/XML/JSON/JUnit por 30 dias. Baixe e abra `coverage/index.html`.
O numero de testes e o percentual do resumo sao calculados dos arquivos de saida, sem valores fixos no codigo.

## Garantias e limites

Cada servico acessa somente seu proprio banco (`solicitacoes_db`).
As alteracoes de negocio e os eventos pendentes sao gravados na mesma transacao (outbox).
O worker reutiliza uma conexao RabbitMQ, publica com confirmacao, consome com ACK apos commit e registra `evento_id` (inbox).
As filas sao duraveis, e mensagens usam persistencia. Falhas de consumo passam por uma fila de retentativa temporizada por consumidor e, na terceira falha, chegam a `matriculas.dlq`.
A entrega e **at least once**: idempotencia e revisao de resultado protegem contra repeticao e reordenacao.
Apos resolver uma falha enviada a DLQ, a mensagem deve ser inspecionada e republicada pelo operador; nao ha descarte silencioso.

A reserva bloqueia a turma para evitar exceder capacidade e bloqueia o aluno para impedir reservas simultaneas em horarios conflitantes.
Cancelamento e assincrono: o estado muda para CANCELADA antes da liberacao efetiva; acompanhe a fila ou o teste E2E para confirmar a devolucao.
A lista de espera e ordenada por coeficiente ou periodo decrescente, ou por chegada crescente, com desempate por data e identificador.
O criterio vale para **candidatos em espera**, sem desfazer vagas ja concedidas. A posicao atual vem de `/lista-espera`, nao de um valor desatualizado no evento.
Cada promocao processa um candidato; eventos `lista.reavaliar` continuam o trabalho sem vincular o sucesso a uma chamada posterior.

Strategy e Factory estao em `matricula-processamento/app/strategies.py`.
O Singleton de configuracao/engine usa `lru_cache`; a conexao do broker pertence ao ciclo de vida do worker.
O schema inicial e criado de forma idempotente com SQLAlchemy; futuras alteracoes de schema devem receber migracoes explicitas.

## CI/CD e configuracao

Cada push na `main` ou PR executa a suite com PostgreSQL/RabbitMQ reais. PR nao faz deploy.
Apos aprovacao dos testes na `main`, o CI publica no DockerHub e atualiza a EC2 usando a tag SHA.
`scripts/deploy.sh` serializa deploys na EC2, verifica `/ready` e restaura a imagem anterior se a nova falhar.

Secrets usados no CI: `DOCKERHUB_TOKEN`, `HOST_TEST`, `KEY_TEST`.
Variavel usada: `EC2_HOST_KEY`, chave publica SSH do servidor (pinning).
A configuracao do container vem de `~/.config/matricula/matricula-solicitacoes.env`, com permissao 600 na EC2.
Os secrets antigos `DB_PASSWORD` e `RABBITMQ_URL` nao sao interpolados em comandos shell pelo workflow.
`.env.example` documenta as variaveis da aplicacao.

## Escopo academico

Nesta etapa, a identidade de demonstracao e informada explicitamente; **Auth0 e autorizacao ainda nao estao implementados**, conforme a etapa 3 do enunciado.
Nao use dados pessoais reais nesta demonstracao. A etapa 3 deve derivar aluno_id do JWT e proteger as rotas administrativas e internas.
Prometheus/Grafana, gateway e testes de carga pertencem a etapa 4. Os relatorios de testes desta etapa medem qualidade do codigo; nao representam monitoramento de producao.

## Acesso publico pela porta 8080

Swagger: http://13.220.42.157:8080/api/solicitacoes/docs

O proxy do repositorio de infraestrutura encaminha `/api/solicitacoes/` para este servico. Na EC2, `ROOT_PATH=/api/solicitacoes` mantem o OpenAPI e o Swagger usando o endereco publico correto. A porta interna 8002 continua sendo usada para comunicacao entre servicos.
