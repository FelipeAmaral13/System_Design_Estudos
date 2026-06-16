# Encurtador de URL

Um encurtador de URL totalmente local/on-premises construído com FastAPI, PostgreSQL, Redis e Celery.

## Arquitetura

- **API** (FastAPI): expõe `POST /urls` para criar uma URL curta e `GET /{code}` para redirecionar
  para a URL original. Limitação de taxa por IP de cliente via `slowapi` (com Redis por trás).
- **Geração de ID**: os códigos são gerados a partir de um ID de 64 bits estilo Snowflake (timestamp +
  node id + sequência) codificado em Base62, então são curtos, ordenáveis e livres de colisão sem
  precisar de uma ida ao banco para alocá-los.
- **Cache**: o Redis armazena em cache as buscas `code -> url` com TTL de 24h. Leituras checam o
  cache antes de acessar o PostgreSQL; escritas populam o cache imediatamente.
- **Banco de dados**: PostgreSQL acessado via engine assíncrona do SQLAlchemy (driver `asyncpg`).
  O schema é gerenciado com migrações do Alembic.
- **Fila assíncrona**: todo redirecionamento enfileira uma task do Celery (broker Redis) que
  registra analytics de clique (`code`, `timestamp`, `user_agent`) sem bloquear a resposta do
  redirecionamento.
- **Circuit breaker**: chamadas ao banco (commit na criação, select na leitura) são envolvidas com
  `pybreaker`, de forma que falhas repetidas no banco abrem o circuito e falham rápido com `503`
  em vez de acumular timeouts lentos.
- **Logging**: logs estruturados em JSON via `structlog` para cada cache hit/miss, erro de banco e
  mudança de estado do circuit breaker.

Diagramas C4 detalhados: [Contexto](docs/c4-context.md) e [Container](docs/c4-container.md).

## Estrutura do projeto

```
app/
  main.py              App FastAPI, lifespan, registro de rotas
  config.py            Configuração via pydantic-settings (lê .env)
  logging_config.py    Configuração do structlog
  limiter.py           Limiter do slowapi (apoiado em Redis)
  base62.py             Codificação/decodificação Base62
  snowflake.py          Gerador de ID Snowflake
  cache.py              Helpers de cache Redis
  circuit_breaker.py     Circuit breaker pybreaker + wrapper de chamada async-safe
  repository.py          Orquestração cache -> circuit breaker -> banco
  deps.py                Dependências do FastAPI (sessão do banco)
  db/
    base.py              Engine assíncrona / factory de sessão
    models.py             Modelo ORM Url
  routers/
    urls.py               POST /urls, GET /{code}
  tasks/
    celery_app.py          Configuração do app Celery
    analytics.py            Task log_click
alembic/                 migrações
tests/                   suíte de testes pytest
docker-compose.yml
Dockerfile
```

## Requisitos

- Python 3.11+
- Docker + Docker Compose (para o stack local completo)
- [`uv`](https://docs.astral.sh/uv/) para gerenciamento local de dependências (opcional, mas recomendado)

## Executando com Docker Compose

Isso sobe o PostgreSQL, o Redis, executa as migrações e então inicia a API e o worker do Celery.

```bash
docker compose up --build
```

Serviços:
- API: http://localhost:8000 (documentação em `/docs`)
- PostgreSQL: localhost:5432 (`shortener` / `shortener`)
- Redis: localhost:6379

O serviço `migrate` executa `alembic upgrade head` uma única vez e encerra antes da `api`/`worker`
iniciarem.

Para parar e remover os containers:

```bash
docker compose down
```

Para também apagar o volume do banco de dados:

```bash
docker compose down -v
```

## Executando localmente sem Docker

1. Suba o PostgreSQL e o Redis você mesmo (ou via `docker compose up postgres redis`).
2. Copie `.env.example` para `.env` e ajuste se seus serviços rodarem em portas diferentes do padrão.
3. Instale as dependências:

   ```bash
   uv sync
   ```

4. Execute as migrações:

   ```bash
   uv run alembic upgrade head
   ```

5. Inicie a API:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

6. Inicie um worker do Celery (em outro terminal):

   ```bash
   uv run celery -A app.tasks.celery_app worker --loglevel=info
   ```

## Migrações do banco de dados

As migrações ficam em `alembic/versions`. A migração inicial (`0001_create_urls_table.py`) cria
a tabela `urls` (`code` como PK, `original_url`, `created_at`, `expires_at`).

Comandos comuns:

```bash
# aplicar todas as migrações pendentes
uv run alembic upgrade head

# criar uma nova migração após alterar app/db/models.py
uv run alembic revision --autogenerate -m "descreva a mudança"

# desfazer a última migração
uv run alembic downgrade -1
```

`alembic/env.py` lê `DATABASE_URL` a partir das configurações do app, então permanece sincronizado
com o que a API usa (sem precisar manter uma string de conexão separada).

## Uso da API

Criar uma URL curta:

```bash
curl -X POST http://localhost:8000/urls \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/some/very/long/path", "ttl_days": 30}'
```

Resposta:

```json
{
  "code": "1B3kP9z",
  "short_url": "http://localhost:8000/1B3kP9z",
  "original_url": "https://example.com/some/very/long/path",
  "created_at": "2026-06-16T12:00:00Z",
  "expires_at": "2026-07-16T12:00:00Z"
}
```

Acessar a URL curta:

```bash
curl -i http://localhost:8000/1B3kP9z
```

Isso retorna um redirecionamento `307` para a URL original e enfileira uma task de analytics de clique.

## Testes

```bash
uv run pytest
```

Os testes usam um banco SQLite em memória (via `aiosqlite`) e `fakeredis` em vez do PostgreSQL/Redis
reais, então rodam sem nenhum serviço externo. O rate limiter do `slowapi` cai para armazenamento em
memória durante os testes (configurado via `REDIS_URL=memory://` em `tests/conftest.py`).

## Configuração

Todas as configurações são variáveis de ambiente (veja `.env.example`), carregadas via `pydantic-settings`:

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://shortener:shortener@localhost:5432/shortener` | URL assíncrona do banco (SQLAlchemy) |
| `REDIS_URL` | `redis://localhost:6379/0` | URL do Redis para cache + rate limiter |
| `CACHE_TTL_SECONDS` | `86400` | TTL do cache (24h) |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Broker do Celery |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Result backend do Celery |
| `SNOWFLAKE_NODE_ID` | `1` | ID do node para o gerador Snowflake (defina um valor único por réplica da API) |
| `BASE_URL` | `http://localhost:8000` | Usado para montar o `short_url` nas respostas |
| `DEFAULT_URL_TTL_DAYS` | `365` | Expiração padrão quando `ttl_days` não é informado |
| `RATE_LIMIT_CREATE` | `10/minute` | Limite de taxa para `POST /urls` |
| `RATE_LIMIT_REDIRECT` | `60/minute` | Limite de taxa para `GET /{code}` |
| `CIRCUIT_BREAKER_FAIL_MAX` | `5` | Falhas consecutivas no banco antes do circuito abrir |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | `30` | Segundos antes de uma tentativa half-open ser feita |

## Notas sobre escalar além de um único node

- `SNOWFLAKE_NODE_ID` deve ser único por réplica da API para garantir códigos globalmente únicos;
  defina um valor por container caso escale a `api` horizontalmente.
- O worker do Celery é stateless e pode ser escalado independentemente da API.
