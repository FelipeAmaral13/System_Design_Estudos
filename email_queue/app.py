"""
app.py
------
Servidor web FastAPI com três responsabilidades:
  1. Servir a interface HTML
  2. Receber pedidos e publicar na queue (producer)
  3. Fazer streaming de status via SSE para o browser
"""

import uuid
import asyncio
import json
from contextlib import asynccontextmanager

import pika
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import RABBITMQ_HOST, QUEUE_NAME, DLQ_NAME, QUEUE_ARGS, PedidoMsg

# pedido_id → {"status": str, "detalhe": str}
status_store: dict[str, dict] = {}

# pedido_id → lista de asyncio.Queue (um por conexão SSE aberta)
# Permite múltiplas abas acompanhando o mesmo pedido
sse_listeners: dict[str, list[asyncio.Queue]] = {}


# Lifespan — inicializa a conexão com RabbitMQ na subida da aplicação
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apenas declara as queues na subida — valida que o RabbitMQ está acessível
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    ch   = conn.channel()
    ch.queue_declare(queue=DLQ_NAME, durable=True)
    ch.queue_declare(queue=QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
    conn.close()
    print("[APP] Queues declaradas. RabbitMQ acessível.")
    yield


def publicar_mensagem(msg: PedidoMsg) -> None:
    """
    Abre uma conexão nova a cada publicação.
    Necessário porque o pika (BlockingConnection) não é thread-safe
    e fecha o canal após inatividade quando usado com FastAPI assíncrono.
    """
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    ch   = conn.channel()
    ch.basic_publish(
        exchange    = "",
        routing_key = QUEUE_NAME,
        body        = msg.to_json(),
        properties  = pika.BasicProperties(
            delivery_mode = 2,
            content_type  = "application/json",
            message_id    = msg.pedido_id,
        ),
    )
    conn.close()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

async def notificar(pedido_id: str, status: str, detalhe: str = "") -> None:
    """Atualiza o store e empurra o evento para o browser via SSE."""
    status_store[pedido_id] = {"status": status, "detalhe": detalhe}
    payload = json.dumps({"status": status, "detalhe": detalhe})
    for q in sse_listeners.get(pedido_id, []):
        await q.put(payload)


class StatusUpdate(BaseModel):
    pedido_id: str
    status:    str
    detalhe:   str = ""

@app.post("/interno/status")
async def receber_status(update: StatusUpdate):
    await notificar(update.pedido_id, update.status, update.detalhe)
    return {"ok": True}


# Endpoint SSE — browser abre uma conexão e recebe eventos em tempo real
@app.get("/status/{pedido_id}")
async def stream_status(pedido_id: str):
    async def generator():
        # Se já existe status (ex: refresh de página), envia imediatamente
        if pedido_id in status_store:
            payload = json.dumps(status_store[pedido_id])
            yield f"data: {payload}\n\n"
            if status_store[pedido_id]["status"] in ("enviado", "falha"):
                return

        # Registra listener e aguarda eventos
        q: asyncio.Queue = asyncio.Queue()
        sse_listeners.setdefault(pedido_id, []).append(q)
        try:
            while True:
                payload = await asyncio.wait_for(q.get(), timeout=30)
                yield f"data: {payload}\n\n"
                data = json.loads(payload)
                if data["status"] in ("enviado", "falha"):
                    break
        except asyncio.TimeoutError:
            yield 'data: {"status":"timeout","detalhe":"Sem resposta do servidor."}\n\n'
        finally:
            sse_listeners[pedido_id].remove(q)

    return StreamingResponse(generator(), media_type="text/event-stream")


# Endpoint principal — recebe o pedido do browser e publica na queue
class PedidoInput(BaseModel):
    cliente_nome:  str
    cliente_email: str
    itens:         list[str]
    valor_total:   float

@app.post("/pedido")
async def criar_pedido(pedido_input: PedidoInput):
    pedido_id = f"PED-{uuid.uuid4().hex[:8].upper()}"

    msg = PedidoMsg(
        pedido_id     = pedido_id,
        cliente_nome  = pedido_input.cliente_nome,
        cliente_email = pedido_input.cliente_email,
        valor_total   = pedido_input.valor_total,
        itens         = pedido_input.itens,
    )

    publicar_mensagem(msg)

    # Status inicial
    await notificar(pedido_id, "na_fila", "Pedido recebido, aguardando processamento...")
    return {"pedido_id": pedido_id}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")