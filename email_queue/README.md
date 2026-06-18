# E-commerce com Message Queue

Sistema de finalização de pedidos com processamento assíncrono via RabbitMQ,
feedback em tempo real no browser via Server-Sent Events (SSE), e tratativa
de erros em duas camadas: validação no frontend e rejeição no consumer com
roteamento para Dead Letter Queue.

---

## O problema que este projeto resolve

Em um e-commerce, o envio de e-mail de confirmação **não deve bloquear** a
resposta ao cliente. Se o servidor de e-mail estiver lento ou fora do ar, o
usuário não pode ficar esperando — e o pedido não pode ser perdido.

A solução: o servidor web publica o pedido em uma fila e responde ao cliente
imediatamente. Um worker independente processa os e-mails em background, com
retry automático em caso de falha e rastreamento de status em tempo real.

---

## Arquitetura

```
Browser
  │
  ├─ GET  /              → serve a interface HTML
  ├─ POST /pedido        → valida, publica na queue, retorna pedido_id
  └─ GET  /status/{id}  → abre conexão SSE (recebe eventos do servidor)
          │
          ▼
      FastAPI (app.py)
          │
      publica mensagem JSON
          │
          ▼
      RabbitMQ
      ├── email_confirmacao       (queue principal)
      └── email_confirmacao_dlq  (Dead Letter Queue)
          │
      consumer.py consome
          │
      ├── sucesso → ACK  → POST /interno/status {status: "enviado"}
      └── falha   → NACK → mensagem vai para DLQ
                         → POST /interno/status {status: "falha"}
          │
          ▼
      FastAPI empurra evento SSE → browser atualiza sem refresh
```

---

## Estrutura de arquivos

```
ecommerce/
├── config.py          # constantes, nomes das queues e modelo PedidoMsg
├── app.py             # servidor FastAPI (producer + SSE + endpoints)
├── consumer.py        # worker RabbitMQ (processa mensagens em background)
└── templates/
    └── index.html     # interface web (carrinho + status em tempo real)
```

---

## Descrição de cada componente

### `config.py`
Define as constantes compartilhadas entre `app.py` e `consumer.py`:
- Endereço do RabbitMQ e nomes das queues
- Argumento `x-dead-letter-routing-key` que liga a queue principal à DLQ
- Dataclass `PedidoMsg` com serialização/deserialização JSON (`to_json` / `from_json`)

### `app.py` — servidor web (FastAPI)
Três responsabilidades:

| Função | Descrição |
|---|---|
| `lifespan` | Na subida, declara as queues no RabbitMQ para garantir que existem |
| `publicar_mensagem` | Abre conexão com RabbitMQ, publica e fecha. Conexão por chamada — necessário porque o pika (BlockingConnection) não é compatível com o loop assíncrono do FastAPI e fecha o canal após inatividade |
| `notificar` | Atualiza o `status_store` em memória e empurra o evento para todas as conexões SSE abertas daquele pedido |
| `POST /pedido` | Recebe o pedido do browser, gera um `pedido_id`, publica na queue, retorna o id |
| `GET /status/{id}` | Endpoint SSE — mantém uma conexão HTTP aberta e envia eventos ao browser conforme chegam via `POST /interno/status` |
| `POST /interno/status` | Endpoint interno chamado pelo consumer para reportar resultado do processamento |
| `GET /` | Serve a interface HTML via Jinja2 |

**Por que conexão por publicação?**
O pika é uma biblioteca bloqueante. O FastAPI roda em loop assíncrono (asyncio).
Manter uma conexão global resulta em `ChannelWrongStateError` após o primeiro
período de inatividade. A solução correta para este cenário é abrir, publicar
e fechar — o overhead é mínimo para volumes baixos.

### `consumer.py` — worker de background
Roda como processo independente. Fluxo para cada mensagem:

1. Recebe a mensagem da queue e notifica a app (`status: processando`)
2. Deserializa o JSON para `PedidoMsg`
3. Valida o e-mail com regex
4. Simula o envio (substitua por `smtplib` ou SDK do SendGrid em produção)
5. **Sucesso** → `basic_ack` + notifica (`status: enviado`)
6. **Falha** → `basic_nack(requeue=False)` + notifica (`status: falha`)
   O RabbitMQ roteia automaticamente para a DLQ

`basic_qos(prefetch_count=1)` garante que o consumer processa uma mensagem
por vez — sem isso, o RabbitMQ despejaria todas as mensagens de uma vez.

### `templates/index.html` — interface web
Interface em HTML/CSS/JS puro, sem framework.

**Carrinho:**
- Catálogo de 6 produtos renderizado via JS
- Adicionar e remover itens com soma automática

**Validação em duas camadas:**

| Camada | Onde | O que valida |
|---|---|---|
| Frontend | `validarFormulario()` | Nome preenchido + regex de e-mail antes do POST |
| Backend | `consumer.py` | Mesma regex — rejeita e manda para DLQ se passar direto |

Erros de validação mostram borda vermelha + mensagem inline abaixo do campo.
A mensagem desaparece automaticamente (`oninput`) conforme o usuário corrige.

**Status em tempo real (SSE):**
Após o POST `/pedido`, o browser abre uma conexão `EventSource` em
`/status/{pedido_id}`. O servidor envia eventos conforme o consumer processa:

| Status | Quando ocorre |
|---|---|
| `na_fila` | Imediatamente após publicar na queue |
| `processando` | Consumer recebeu a mensagem |
| `enviado` | E-mail enviado com sucesso — ACK |
| `falha` | Consumer rejeitou — NACK + DLQ. Exibe motivo e opção de novo pedido |
| `timeout` | SSE sem resposta por 30s (consumer offline) |

---

## Conceitos de Message Queue aplicados

| Conceito | Onde aparece |
|---|---|
| `durable=True` | Queue sobrevive a restart do RabbitMQ |
| `delivery_mode=2` | Mensagem persistida em disco |
| `basic_qos(prefetch_count=1)` | Fair dispatch — um por vez |
| `basic_ack` | Confirma sucesso → mensagem deletada da queue |
| `basic_nack(requeue=False)` | Sinaliza falha → aciona dead letter routing |
| Dead Letter Queue | Fila separada para mensagens que não puderam ser processadas |
| SSE | Servidor empurra eventos ao browser sem polling |

---

## Como executar

### Pré-requisitos
```bash
pip install fastapi uvicorn pika requests jinja2
```

### 3 terminais

```bash
# Terminal 1 — RabbitMQ
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Terminal 2 — Servidor web
uvicorn app:app --reload

# Terminal 3 — Worker consumer
python consumer.py
```

Acesse: **http://localhost:8000**

O painel de administração do RabbitMQ fica em **http://localhost:15672**
(usuário: `guest`, senha: `guest`) — útil para observar a DLQ em tempo real.

---

## Cenários de teste

| Cenário | Como reproduzir | Resultado esperado |
|---|---|---|
| Pedido válido | Nome + e-mail válido + itens | ✅ Status `enviado` via SSE |
| E-mail inválido (frontend) | Digitar `imail` no campo | Campo vermelho, POST bloqueado |
| E-mail inválido (backend) | Editar o valor via DevTools e submeter | ❌ Status `falha` com motivo + link DLQ |
| Consumer offline | Parar `consumer.py`, fazer pedido | Status fica em `na_fila`; ao religar o consumer, processa e atualiza o browser |
| Múltiplos consumers | Rodar `python consumer.py` em dois terminais | Mensagens distribuídas automaticamente entre os workers |
