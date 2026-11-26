"""Testes do armazenamento privado: independência, substituição e opacidade."""

import asyncio
import json
import sys
from pathlib import Path

from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore
from a2a.types.a2a_pb2 import Task, TaskState, TaskStatus
from google.protobuf.json_format import MessageToDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente.continuations import Continuacoes
from agente.mcp_host import Pendente

ARGS_A = {"sala": "sala-garagem", "inicio": "2026-11-03T14:00:00-03:00", "fim": "2026-11-03T15:00:00-03:00", "responsavel": "Marty"}
ARGS_B = {"sala": "sala-fusca", "inicio": "2026-11-03T16:00:00-03:00", "fim": "2026-11-03T17:00:00-03:00", "responsavel": "Lorraine"}


def pendente(args, *, alternativas=("sala-fusca", "sala-mirante"), token="token-A", chave="chave-A", trace="00-aaaa-bbbb-01"):
    return Pendente(
        "Escolha uma sala alternativa",
        alternativas,
        "2026-11-01",
        "reservar_sala",
        dict(args),
        chave,
        token,
        trace,
    )


def test_entradas_independentes_e_token_opaco():
    continuacoes = Continuacoes()
    a = continuacoes.guardar("task-a", pendente(ARGS_A, token="token-A", chave="chave-A", trace="trace-A"))
    b = continuacoes.guardar("task-b", pendente(ARGS_B, alternativas=("sala-mirante",), token="token-B", chave="chave-B", trace="trace-B"))

    assert continuacoes.obter("task-a") is a
    assert continuacoes.obter("task-b") is b
    assert a.token == "token-A" and b.token == "token-B"
    assert a.chave == "chave-A" and b.chave == "chave-B"
    assert a.alternativas == ("sala-fusca", "sala-mirante")
    assert b.alternativas == ("sala-mirante",)
    assert a.argumentos["responsavel"] == "Marty"
    assert b.argumentos["responsavel"] == "Lorraine"
    assert a.traceparent == "trace-A" and b.traceparent == "trace-B"

    # O token é somente guardado/ecoado; nunca aparece em repr acidental.
    assert "token-A" not in repr(a) and "chave-A" not in repr(a)
    assert "token-B" not in repr(b) and "chave-B" not in repr(b)

    # Reconstruir a pergunta devolve o token intacto, sem interpretar o conteúdo.
    reconstruida = a.pendente()
    assert reconstruida._token == "token-A"
    assert reconstruida._chave == "chave-A"
    assert reconstruida._argumentos == ARGS_A
    reconstruida._argumentos["responsavel"] = "alterado"
    assert a.argumentos["responsavel"] == "Marty"

    # Remover uma Task não remove a continuação da outra.
    continuacoes.remover("task-a")
    assert continuacoes.obter("task-a") is None
    assert continuacoes.obter("task-b") is b
    assert len(continuacoes) == 1


def test_nova_pausa_substitui_somente_a_mesma_task():
    continuacoes = Continuacoes()
    continuacoes.guardar("task-a", pendente(ARGS_A, token="token-1", chave="chave-1"))
    continuacoes.guardar("task-b", pendente(ARGS_B, token="token-B", chave="chave-B"))

    nova = continuacoes.guardar(
        "task-a",
        pendente(ARGS_A, alternativas=("sala-mirante",), token="token-2", chave="chave-2", trace="trace-2"),
    )

    assert continuacoes.obter("task-a") is nova
    assert nova.token == "token-2" and nova.chave == "chave-2"
    assert nova.alternativas == ("sala-mirante",)
    assert nova.traceparent == "trace-2"
    assert continuacoes.obter("task-b").token == "token-B"
    assert len(continuacoes) == 2


def test_store_publico_nao_recebe_continuacao():
    async def run():
        store = InMemoryTaskStore()
        task = Task(
            id="task-a",
            context_id="ctx",
            status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
        )
        await store.save(task, ServerCallContext())
        antes = MessageToDict(await store.get("task-a", ServerCallContext()))

        continuacoes = Continuacoes()
        continuacoes.guardar("task-a", pendente(ARGS_A, token="token-secreto", chave="chave-secreta"))
        depois = MessageToDict(await store.get("task-a", ServerCallContext()))

        assert depois == antes
        serializado = json.dumps(depois, ensure_ascii=False)
        assert "token-secreto" not in serializado
        assert "chave-secreta" not in serializado
        assert "requestState" not in serializado
        assert "request_state" not in serializado

    asyncio.run(run())


def test_trava_serializa_retomadas_da_mesma_task():
    async def run():
        continuacoes = Continuacoes()
        ordem = []

        async def retomar(n):
            async with continuacoes.trava("task-a"):
                ordem.append(("inicio", n))
                await asyncio.sleep(0.01)
                ordem.append(("fim", n))

        await asyncio.gather(retomar(1), retomar(2))
        assert ordem == [("inicio", 1), ("fim", 1), ("inicio", 2), ("fim", 2)]

    asyncio.run(run())
