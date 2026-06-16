# C4 - Nível 2: Diagrama de Container

```mermaid
C4Container
    title Encurtador de URL - Diagrama de Container

    Person(cliente, "Cliente", "Acessa URLs encurtadas")
    Person(desenvolvedor, "Desenvolvedor", "Cria URLs encurtadas")

    System_Boundary(sistema, "Limite do Sistema - Encurtador de URL") {
        Container(api, "API Gateway / Application Service", "FastAPI + Uvicorn", "Ponto de entrada único. Valida requisições, aplica rate limiting (slowapi), gera código curto (Snowflake ID + Base62), resolve redirecionamento e aplica circuit breaker nas chamadas ao banco.")
        ContainerDb(cache, "Cache", "Redis", "Camada de leitura rápida. Armazena code -> URL original com TTL de 24h para reduzir latência e carga no banco. Também serve como storage do rate limiter.")
        ContainerDb(banco, "Banco de Dados", "PostgreSQL (SQLAlchemy async)", "Fonte da verdade. Tabela urls (code PK, original_url, created_at, expires_at). Migrações via Alembic.")
        ContainerQueue(broker, "Broker de Fila", "Redis (Celery broker)", "Transporta tasks assíncronas entre a API e o worker.")
        Container(worker, "Worker Assíncrono", "Celery", "Consome tasks de analytics de clique (code, timestamp, user_agent) e registra via structlog, sem bloquear o redirecionamento.")
    }

    Rel(desenvolvedor, api, "Cria URL curta", "HTTPS POST /urls")
    Rel(cliente, api, "Acessa URL curta", "HTTPS GET /{code}")
    Rel(api, cache, "Lê/Escreve", "Redis protocol")
    Rel(api, banco, "Lê/Escreve (via circuit breaker)", "asyncpg")
    Rel(api, broker, "Publica task de clique", "Redis protocol")
    Rel(broker, worker, "Entrega task", "Redis protocol")
    Rel(worker, worker, "Registra log estruturado", "structlog/JSON")
```

## Containers

| Container | Tecnologia | Responsabilidade |
| --- | --- | --- |
| API Gateway / Application Service | FastAPI + Uvicorn | Único ponto de entrada HTTP. Rate limiting (`slowapi`), geração de código (Snowflake + Base62), orquestração cache → circuit breaker → banco, enfileiramento da task de analytics. |
| Cache | Redis | Cache `code -> URL` com TTL de 24h. Também usado como storage do rate limiter. |
| Banco de Dados | PostgreSQL | Fonte da verdade. Tabela `urls`. Acesso assíncrono via SQLAlchemy + `asyncpg`. Migrações via Alembic. |
| Broker de Fila | Redis (DB lógico separado do cache) | Transporta as mensagens de task entre API e worker (broker do Celery). |
| Worker Assíncrono | Celery | Processa a task `log_click`, registrando `code`, `timestamp` e `user_agent` via `structlog`, fora do caminho crítico do redirecionamento. |

## Notas de implementação

- **Circuit breaker** (`pybreaker`): protege as chamadas ao PostgreSQL (commit na criação, select
  na leitura). Após `CIRCUIT_BREAKER_FAIL_MAX` falhas consecutivas, o circuito abre e a API
  responde `503` imediatamente em vez de empilhar timeouts.
- **Cache-aside**: toda leitura primeiro consulta o Redis; em caso de miss, busca no Postgres
  (protegido pelo circuit breaker) e popula o cache antes de responder.
- **Fila assíncrona**: ao contrário do diagrama de referência genérico (que mostra uma
  "Message Queue + DLQ" desacoplada), este projeto usa o Celery com Redis como broker. O Celery
  já oferece retries configuráveis por task; uma DLQ explícita não foi implementada por não ser
  necessária no escopo atual (analytics de clique tolera perda ocasional).
- **Banco relacional em vez de NoSQL**: o diagrama de referência sugere DynamoDB/Cassandra; este
  projeto usa PostgreSQL por requisito explícito do projeto (consistência forte, migrações com
  Alembic, e volume de escrita compatível com um único nó relacional).
