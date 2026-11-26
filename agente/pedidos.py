"""Parser puro dos pedidos iniciais de reserva.

Formato aceito, com campos obrigatórios nesta ordem e separados por espaços::

    reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>

O comando e as chaves são literais, em minúsculas. Sala, início e fim são
tokens não vazios, sem espaços ou ``=``. O responsável é todo o restante da
linha após ``responsavel=``: seus espaços, acentos e pontuação são preservados,
mas ele não pode ser vazio ou conter somente espaços. Não há remoção de
espaços externos nem aceitação de pedidos em múltiplas linhas.

Este módulo valida somente a estrutura do pedido. Os horários ISO 8601 são
encaminhados como texto, sem conversão ou normalização; sua validade, a sala,
a ordem do intervalo, a política e os conflitos são responsabilidade do MCP.
Não lê catálogo, arquivos, relógio ou rede e não interpreta continuações.
"""

import re
from typing import TypedDict


class PedidoReserva(TypedDict):
    """Argumentos textuais que poderão ser encaminhados à tool de reserva."""

    sala: str
    inicio: str
    fim: str
    responsavel: str


class PedidoInvalido(ValueError):
    """O texto não segue a estrutura fixa de um pedido inicial de reserva."""


_FORMATO = (
    "Pedido invalido: use reservar sala=<id> inicio=<iso8601> "
    "fim=<iso8601> responsavel=<nome>"
)
_PEDIDO = re.compile(
    r"reservar +sala=(?P<sala>[^\s=]+)"
    r" +inicio=(?P<inicio>[^\s=]+)"
    r" +fim=(?P<fim>[^\s=]+)"
    r" +responsavel=(?P<responsavel>[^\r\n]+)"
)


def parse_pedido(texto: str) -> PedidoReserva:
    """Retorna quatro strings preservadas ou lança ``PedidoInvalido``.

    A mensagem de erro é estável e não inclui o conteúdo recebido. Cada chamada
    devolve um novo dicionário, sem alterar ou compartilhar estado entre pedidos.
    """
    if not isinstance(texto, str):
        raise PedidoInvalido(_FORMATO)

    resultado = _PEDIDO.fullmatch(texto)
    if resultado is None or not resultado["responsavel"].strip():
        raise PedidoInvalido(_FORMATO)

    return PedidoReserva(
        sala=resultado["sala"],
        inicio=resultado["inicio"],
        fim=resultado["fim"],
        responsavel=resultado["responsavel"],
    )
