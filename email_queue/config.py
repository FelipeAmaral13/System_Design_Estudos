import json
from dataclasses import dataclass, asdict

RABBITMQ_HOST = "localhost"
QUEUE_NAME    = "email_confirmacao"
DLQ_NAME      = "email_confirmacao_dlq"
MAX_RETRIES   = 3

QUEUE_ARGS = {
    "x-dead-letter-exchange": "",
    "x-dead-letter-routing-key": DLQ_NAME,
    "x-max-delivery-count": MAX_RETRIES,
}

@dataclass
class PedidoMsg:
    pedido_id:      str
    cliente_nome:   str
    cliente_email:  str
    valor_total:    float
    itens:          list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "PedidoMsg":
        return cls(**json.loads(raw))
