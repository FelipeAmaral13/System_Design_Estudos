"""
consumer.py
-----------
Worker independente que:
  1. Escuta a queue do RabbitMQ
  2. Valida e "envia" o e-mail
  3. Chama POST /interno/status na app para atualizar o browser via SSE

Rode em terminal separado:
    python consumer.py
"""

import re
import time
import json
import requests
import pika

from config import RABBITMQ_HOST, QUEUE_NAME, DLQ_NAME, QUEUE_ARGS, PedidoMsg

APP_URL = "http://localhost:8000"

def notificar_app(pedido_id: str, status: str, detalhe: str = "") -> None:
    try:
        requests.post(
            f"{APP_URL}/interno/status",
            json={"pedido_id": pedido_id, "status": status, "detalhe": detalhe},
            timeout=5,
        )
    except Exception as e:
        print(f"[CONSUMER] Aviso: não conseguiu notificar app — {e}")


def email_valido(email: str) -> bool:
    return bool(re.match(r"^[\w.+-]+@[\w.-]+\.[a-z]{2,}$", email))

def enviar_email(pedido: PedidoMsg) -> None:
    if not email_valido(pedido.cliente_email):
        raise ValueError(f"E-mail inválido: {pedido.cliente_email}")

    # Simula latência de SMTP
    time.sleep(1.5)

    print(f"""
  ✉  E-mail enviado
  ├─ Para:   {pedido.cliente_nome} <{pedido.cliente_email}>
  ├─ Pedido: {pedido.pedido_id}
  ├─ Itens:  {', '.join(pedido.itens)}
  └─ Total:  R$ {pedido.valor_total:.2f}
    """)


def processar(channel, method, properties, body: bytes) -> None:
    pedido_id = properties.message_id or "desconhecido"
    print(f"\n[CONSUMER] Processando {pedido_id}...")

    notificar_app(pedido_id, "processando", "Validando e enviando e-mail...")

    try:
        pedido = PedidoMsg.from_json(body.decode())
        enviar_email(pedido)

        channel.basic_ack(delivery_tag=method.delivery_tag)
        notificar_app(
            pedido_id,
            "enviado",
            f"E-mail de confirmação enviado para {pedido.cliente_email}.",
        )
        print(f"[CONSUMER] ACK — {pedido_id} concluído.")

    except Exception as erro:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        notificar_app(
            pedido_id,
            "falha",
            f"Não foi possível processar o pedido: {erro}",
        )
        print(f"[CONSUMER] NACK — {pedido_id} enviado para DLQ. Motivo: {erro}")


def main() -> None:
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST)
    )
    channel = connection.channel()
    channel.queue_declare(queue=DLQ_NAME, durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=processar)

    print("[CONSUMER] Aguardando mensagens. Ctrl+C para parar.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("\n[CONSUMER] Encerrado.")
        connection.close()


if __name__ == "__main__":
    main()
