# matricula-solicitacoes

Servico responsavel por receber e acompanhar as solicitacoes de matricula feitas pelos alunos.

Este repositorio contem **apenas o esqueleto do servico**: aplicacao FastAPI com
endpoints de identificacao e health, configuracao via variaveis de ambiente,
testes, imagem Docker e pipeline de CI/CD. As regras de negocio, o modelo de
dados, a conexao com o banco e o consumo de filas sao entregas posteriores.

| Item | Valor |
| --- | --- |
| Porta | `8002` |
| Imagem Docker | `nadertaha06/matricula-solicitacoes` |
| Container na EC2 | `matricula-solicitacoes` |
| Banco de dados | `solicitacoes_db` |
| Rede Docker | `rede` |

## Endpoints

| Metodo | Rota | Resposta |
| --- | --- | --- |
| `GET` | `/` | `{"service": "matricula-solicitacoes"}` |
| `GET` | `/health` | `{"status": "ok", "service": "matricula-solicitacoes"}` |

Documentacao interativa gerada pelo FastAPI em `http://localhost:8002/docs`.

## Rodando local

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # ajuste os valores; o .env nao vai para o git

uvicorn app.main:app --reload --port 8002
```

Conferindo:

```bash
curl http://localhost:8002/health
# {"status":"ok","service":"matricula-solicitacoes"}
```

## Rodando os testes

```bash
pytest
```

O `pyproject.toml` ja configura `--cov=app --cov-report=term-missing
--cov-fail-under=80`, entao o comando falha sozinho se a cobertura cair abaixo
de 80%.

## Buildando a imagem

```bash
docker build -t nadertaha06/matricula-solicitacoes:latest .

docker run --rm -p 8002:8002 --env-file .env \
  nadertaha06/matricula-solicitacoes:latest
```

Para rodar junto da infraestrutura do repositorio `matricula-infra`, suba o
container na mesma rede:

```bash
docker run -d --name matricula-solicitacoes --network rede --restart unless-stopped \
  -p 8002:8002 --env-file .env \
  nadertaha06/matricula-solicitacoes:latest
```

## Variaveis de ambiente

Todas sao lidas por `app/config.py` (`Settings` do `pydantic-settings`).
Veja `.env.example` para um modelo preenchido com valores de exemplo.

| Variavel | Descricao | Exemplo |
| --- | --- | --- |
| `APP_NAME` | Nome do servico, devolvido em `/` e `/health` | `matricula-solicitacoes` |
| `PORT` | Porta em que o uvicorn escuta | `8002` |
| `DB_HOST` | Host do Postgres. Na EC2 e o `container_name` definido no `matricula-infra` | `postgres` |
| `DB_PORT` | Porta do Postgres | `5432` |
| `DB_NAME` | Banco usado por este servico | `solicitacoes_db` |
| `DB_USER` | Usuario do Postgres | `postgres` |
| `DB_PASSWORD` | Senha do Postgres. Vem do secret `DB_PASSWORD` | *(secret)* |
| `RABBITMQ_URL` | URL AMQP do RabbitMQ. Vem do secret `RABBITMQ_URL` | `amqp://usuario:senha@rabbitmq:5672/` |
| `AUTH0_DOMAIN` | Dominio do tenant Auth0. Vem do secret `AUTH0_DOMAIN` | `seu-tenant.us.auth0.com` |
| `AUTH0_AUDIENCE` | Audience da API no Auth0. Vem do secret `AUTH0_AUDIENCE` | `https://api.matricula.exemplo` |

`get_settings()` e decorada com `@lru_cache`, o que implementa o padrao
**Singleton**: a instancia de `Settings` e construida uma unica vez por processo.

## CI/CD

`.github/workflows/deploy.yml` tem dois jobs:

- **test** — roda em `push` na `main` e em `pull_request`. Sobe um `postgres:16`
  real pelo bloco `services:` do GitHub Actions (healthcheck com `pg_isready`),
  instala as dependencias e roda o `pytest` com o corte de cobertura.
- **deploy** — depende do `test` (`needs`) e roda **somente** em `push` na
  `main`. Faz login no DockerHub, builda e publica a imagem com as tags
  `${{ github.sha }}` e `latest`, e entao conecta por SSH na EC2 para trocar o
  container.

Para adaptar o workflow a outro servico basta editar o bloco `env:` do topo do
arquivo (`IMAGE`, `CONTAINER`, `PORT`, `DB_NAME`).

### Secrets necessarios neste repositorio

| Secret | Para que serve |
| --- | --- |
| `DOCKERHUB_TOKEN` | Access token do DockerHub do usuario `nadertaha06` |
| `HOST_TEST` | IP ou DNS publico da EC2 |
| `KEY_TEST` | Chave SSH privada do usuario `ubuntu` |
| `DB_PASSWORD` | Senha do Postgres, igual a do `matricula-infra` |
| `RABBITMQ_URL` | URL AMQP completa do RabbitMQ |
| `AUTH0_DOMAIN` | Dominio do tenant Auth0 |
| `AUTH0_AUDIENCE` | Audience da API no Auth0 |
