"""
producer.py
-----------
Simula o endpoint do e-commerce que recebe o pedido.
Em vez de enviar o e-mail na hora (bloqueante), publica
uma mensagem na queue e responde ao cliente imediatamente.

Uso:
    python producer.py
"""

import pika
import uuid
from config import (
    RABBITMQ_HOST,
    QUEUE_NAME,
    DLQ_NAME,
    MAX_RETRIES,
    PedidoConfirmacao,
)


def criar_canal(connection: pika.BlockingConnection) -> pika.channel.Channel:
    """
    Declara a queue principal e a DLQ.
    Declarar é idempotente: seguro chamar toda vez que a app sobe.
    """
    channel = connection.channel()

    # Dead Letter Queue — recebe mensagens que esgotaram retries
    channel.queue_declare(queue=DLQ_NAME, durable=True)

    # Queue principal com referência para a DLQ
    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True,                         # sobrevive a restart do RabbitMQ
        arguments={
            "x-dead-letter-exchange": "",     # usa o default exchange
            "x-dead-letter-routing-key": DLQ_NAME,
            "x-max-delivery-count": MAX_RETRIES,
        },
    )

    return channel


def publicar_pedido(pedido: PedidoConfirmacao) -> None:
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST)
    )
    channel = criar_canal(connection)

    mensagem = pedido.to_json()

    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=mensagem,
        properties=pika.BasicProperties(
            delivery_mode=2,            # persiste a mensagem em disco
            content_type="application/json",
            message_id=str(uuid.uuid4()),
        ),
    )

    print(f"[PRODUCER] Pedido {pedido.pedido_id} publicado na queue.")
    connection.close()


# --- Simula 3 pedidos chegando no servidor web ---
if __name__ == "__main__":
    pedidos = [
        PedidoConfirmacao(
            pedido_id="PED-001",
            cliente_nome="Ana Lima",
            cliente_email="ana@email.com",
            valor_total=349.90,
            itens=["Tênis Nike", "Meia esportiva"],
        ),
        PedidoConfirmacao(
            pedido_id="PED-002",
            cliente_nome="Carlos Souza",
            cliente_email="carlos@email.com",
            valor_total=89.00,
            itens=["Livro Python Fluente"],
        ),
        PedidoConfirmacao(
            pedido_id="PED-FALHA",              # este vai simular falha no consumer
            cliente_nome="Maria Erro",
            cliente_email="invalido@@email",    # e-mail inválido → vai para DLQ
            valor_total=0.0,
            itens=[],
        ),
    ]

    for pedido in pedidos:
        publicar_pedido(pedido)

    print("\n[PRODUCER] Todos os pedidos foram enfileirados.")
    print("[PRODUCER] O servidor web já pode responder ao cliente — sem esperar o e-mail.")
