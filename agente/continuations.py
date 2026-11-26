"""Armazenamento privado de continuações MRTR, separado do store público A2A.

Cada Task pausada tem no máximo uma entrada, indexada pelo ``taskId``. A
entrada guarda cópia do pedido original, a pergunta, as alternativas
normalizadas, o ``requestState`` opaco e o ``traceparent`` da Task. O token é
somente guardado e ecoado ao host MCP: este módulo nunca o decodifica,
interpreta, reconstrói ou inclui em representações públicas.

O mapa não é referenciado pela Task pública do SDK. Uma entrada é removida
somente quando a Task atinge estado terminal; uma nova pausa da mesma Task
substitui a entrada anterior. Entradas de Tasks diferentes são independentes.
As travas são locais e curtas: ``GetTask`` não passa por elas.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agente.mcp_host import Pendente


@dataclass(frozen=True)
class Continuacao:
    """Estado privado necessário para repetir o pedido original.

    Os campos usam ``repr=False`` para que um traceback ou log acidental não
    serialize o token, a chave ou o pedido. O token permanece opaco: apenas
    transita de ``Pendente`` para ``Pendente``.
    """

    nome: str = field(repr=False)
    argumentos: dict[str, Any] = field(repr=False)
    pergunta: str = field(repr=False)
    alternativas: tuple[str, ...] = field(repr=False)
    versao_politica: str = field(repr=False)
    chave: str = field(repr=False)
    token: str = field(repr=False)
    traceparent: str | None = field(default=None, repr=False)

    def pendente(self) -> Pendente:
        """Reconstrói a pergunta para o host, sem abrir ou alterar o token."""
        return Pendente(
            pergunta=self.pergunta,
            alternativas=self.alternativas,
            versao_politica=self.versao_politica,
            _nome=self.nome,
            _argumentos=deepcopy(self.argumentos),
            _chave=self.chave,
            _token=self.token,
            _traceparent=self.traceparent,
        )


class Continuacoes:
    """Mapa ``taskId`` -> continuação privada, com trava curta por Task."""

    def __init__(self) -> None:
        self._entradas: dict[str, Continuacao] = {}
        self._travas: dict[str, asyncio.Lock] = {}

    def guardar(
        self,
        task_id: str,
        pendente: Pendente,
        *,
        traceparent: str | None = None,
    ) -> Continuacao:
        """Cria ou substitui a continuação daquela Task.

        Uma nova pausa da mesma Task chama este método novamente, trocando
        somente a entrada correspondente. Outras Tasks não são afetadas.
        """
        trace = traceparent if traceparent is not None else pendente._traceparent
        entrada = Continuacao(
            nome=pendente._nome,
            argumentos=deepcopy(pendente._argumentos),
            pergunta=pendente.pergunta,
            alternativas=pendente.alternativas,
            versao_politica=pendente.versao_politica,
            chave=pendente._chave,
            token=pendente._token,
            traceparent=trace,
        )
        self._entradas[task_id] = entrada
        return entrada

    def obter(self, task_id: str) -> Continuacao | None:
        """Retorna a continuação da Task, sem criar ou interpretar estado."""
        return self._entradas.get(task_id)

    def remover(self, task_id: str) -> None:
        """Remove somente a entrada da Task informada; idempotente."""
        self._entradas.pop(task_id, None)

    def trava(self, task_id: str) -> asyncio.Lock:
        """Trava local por Task para serializar retomadas da mesma Task."""
        return self._travas.setdefault(task_id, asyncio.Lock())

    def __len__(self) -> int:
        return len(self._entradas)
