"""Aplicação A2A v1: Tasks públicas em memória e ponte MRTR privada por Task.

A Task pública (estado, histórico e artifact) vive no store do SDK. A
continuação privada (pedido original, pergunta, alternativas, requestState e
trace) vive em ``Continuacoes`` e nunca é anexada à Task. O token é opaco:
guardado e ecoado ao host, nunca interpretado. Tasks não sobrevivem ao restart
do agente; a validade do requestState após restart do MCP pertence à change de
MRTR.
"""

import json
import os
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types.a2a_pb2 import (
    AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part,
    Role, Task, TaskState, TaskStatus,
)
from a2a.utils.errors import UnsupportedOperationError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agente.continuations import Continuacao, Continuacoes
from agente.mcp_host import MCPHost, Pendente
from agente.pedidos import PedidoInvalido, parse_pedido


_TERMINAIS = frozenset({
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
})
_FALHA_HOST = "Falha ao comunicar com o serviço de reservas"


def mensagem_alternativas(alternativas: tuple[str, ...]) -> str:
    """Linha exata da pausa: sem prefixo, saudação ou quebra de linha."""
    return f"alternativas: {', '.join(alternativas)}"


def interpretar_escolha(
    texto: str, alternativas: tuple[str, ...]
) -> tuple[str, str | None] | None:
    """Traduz a resposta fixa do cliente; ``None`` mantém a pausa."""
    if texto == "escolha=recusar":
        return "decline", None
    prefixo = "escolha="
    if texto.startswith(prefixo):
        sala = texto[len(prefixo):]
        if sala in alternativas:
            return "accept", sala
    return None


class VersaoV1Padrao(BaseHTTPMiddleware):
    """Este endpoint é exclusivamente v1, inclusive sem header opcional."""

    async def dispatch(self, request, call_next):
        if request.url.path == "/a2a" and "a2a-version" not in request.headers:
            request.scope["headers"] = [*request.scope["headers"], (b"a2a-version", b"1.0")]
        return await call_next(request)


class ReservasExecutor(AgentExecutor):
    """Traduz o ciclo MRTR para a Task A2A; não decide regra de sala."""

    def __init__(self, continuacoes: Continuacoes | None = None) -> None:
        self._continuacoes = continuacoes if continuacoes is not None else Continuacoes()

    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        atual = context.current_task
        if atual is not None and atual.status.state in _TERMINAIS:
            raise UnsupportedOperationError(
                f"Task {context.task_id} está em estado terminal"
            )
        if atual is not None and atual.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            # Ponto da ponte: a segunda mensagem da mesma Task é a resposta à
            # elicitation; o pedido original permanece no mapa privado.
            await self._continuar(context, updater)
            return
        if atual is not None:
            raise UnsupportedOperationError(
                f"Task {context.task_id} não está aguardando escolha"
            )
        if self._continuacoes.obter(context.task_id) is not None:
            raise UnsupportedOperationError(
                f"Task {context.task_id} não possui estado público correspondente"
            )
        await self._iniciar(context, event_queue, updater)

    async def _iniciar(self, context, event_queue, updater):
        await event_queue.enqueue_event(Task(
            id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            history=[context.message],
        ))
        await updater.start_work()

        try:
            args = parse_pedido(context.get_user_input())
        except PedidoInvalido as exc:
            await self._falhar(context, updater, str(exc))
            return
        try:
            headers = context.call_context.state.get("headers", {})
            async with MCPHost(os.environ.get("MCP_URL", "http://localhost:7301/mcp")) as host:
                result = await host.iniciar("reservar_sala", args, traceparent=headers.get("traceparent"))
        except Exception:
            await self._falhar(context, updater, _FALHA_HOST)
            return
        if isinstance(result, Pendente):
            await self._pausar(context, updater, result)
            return
        if result.erro is not None:
            await self._falhar(context, updater, result.erro)
            return
        try:
            await self._concluir(updater, result)
        except Exception:
            await self._falhar(context, updater, "Resposta MCP inválida")

    async def _continuar(self, context, updater):
        task_id = context.task_id
        async with self._continuacoes.trava(task_id):
            entrada = self._continuacoes.obter(task_id)
            if entrada is None:
                raise UnsupportedOperationError(
                    f"Task {task_id} não possui continuação pendente"
                )
            pausou = False
            try:
                escolha = interpretar_escolha(
                    context.get_user_input(), entrada.alternativas
                )
                if escolha is None:
                    # Escolha fora do schema não consome o estado nem chama o MCP.
                    await updater.requires_input(self._mensagem(
                        context, mensagem_alternativas(entrada.alternativas)
                    ))
                    pausou = True
                    return

                action, sala = escolha
                await updater.start_work()
                headers = context.call_context.state.get("headers", {})
                trace = headers.get("traceparent") or entrada.traceparent
                try:
                    async with MCPHost(os.environ.get("MCP_URL", "http://localhost:7301/mcp")) as host:
                        result = await host.retomar(
                            entrada.pendente(), action, escolha=sala, traceparent=trace
                        )
                except Exception:
                    # Falha de protocolo/transporte (token expirado, estado
                    # inválido) vira FAILED segura. O texto do SDK não é
                    # copiado porque pode conter o token.
                    await self._falhar(context, updater, _FALHA_HOST)
                    return

                if isinstance(result, Pendente):
                    # Nova elicitation: substitui somente a continuação desta Task.
                    await self._pausar(context, updater, result, traceparent=trace)
                    pausou = True
                    return
                if result.erro is not None:
                    await self._falhar(
                        context, updater, self._texto_seguro(result.erro, entrada)
                    )
                    return
                if action == "decline":
                    content = result.resultado.structured_content
                    if not isinstance(content, dict) or content.get("reservado") is not False:
                        await self._falhar(context, updater, "Resposta MCP inválida")
                        return
                    await updater.cancel()
                    return
                try:
                    await self._concluir(updater, result)
                except Exception:
                    await self._falhar(context, updater, "Resposta MCP inválida")
            finally:
                # A entrada só sobrevive quando houve nova pausa; conclusão,
                # recusa, falha e exceções encerram a continuação desta Task.
                if not pausou:
                    self._continuacoes.remover(task_id)

    async def _pausar(self, context, updater, pendente, *, traceparent=None):
        self._continuacoes.guardar(context.task_id, pendente, traceparent=traceparent)
        message = self._mensagem(
            context, mensagem_alternativas(pendente.alternativas)
        )
        try:
            # A transição WORKING com a mesma mensagem garante que o texto
            # exato apareça no status e no histórico da Task devolvida.
            await updater.start_work(message)
            await updater.requires_input(message)
        except BaseException:
            self._continuacoes.remover(context.task_id)
            raise

    async def _concluir(self, updater, result):
        content = result.resultado.structured_content
        if not isinstance(content, dict) or not content.get("reservado"):
            raise ValueError("Resposta MCP inválida")
        produto = {key: content[key] for key in ("reserva", "sala", "inicio", "fim", "responsavel")}
        produto["politica"] = result.versao_politica
        await updater.add_artifact([Part(text=json.dumps(produto, ensure_ascii=False))], name="reserva")
        await updater.complete()

    async def _falhar(self, context, updater, texto):
        message = self._mensagem(context, texto)
        # O SDK move a mensagem anterior ao histórico na próxima transição.
        await updater.start_work(message)
        await updater.failed(message)

    @staticmethod
    def _mensagem(context, texto):
        return Message(message_id=str(uuid4()), role=Role.ROLE_AGENT,
                       task_id=context.task_id, context_id=context.context_id,
                       parts=[Part(text=texto)])

    @staticmethod
    def _texto_seguro(texto: str, entrada: Continuacao) -> str:
        if entrada.token in texto or entrada.chave in texto:
            return _FALHA_HOST
        return texto

    async def cancel(self, context, event_queue):
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def criar_app():
    url = os.environ.get("A2A_URL", "http://localhost:7300/a2a")
    card = AgentCard(
        name="Central de Salas", description="Reserva determinística de salas", version="1.0.0",
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        skills=[AgentSkill(id="reservar-sala", name="Reservar sala", description="Reserva uma sala", tags=["reserva"])],
    )
    continuacoes = Continuacoes()
    handler = DefaultRequestHandler(
        agent_executor=ReservasExecutor(continuacoes),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    rpc_route = create_jsonrpc_routes(handler, "/a2a")[0]
    sdk_endpoint = rpc_route.endpoint

    async def endpoint(request):
        # O contrato local de GetTask usa result.task, como SendMessage.
        # O dispatcher oficial v1 retorna diretamente a Task em result.
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            payload = None
        response = await sdk_endpoint(request)
        if isinstance(payload, dict) and payload.get("method") == "GetTask" and isinstance(response, JSONResponse):
            body = json.loads(response.body)
            if "result" in body:
                body["result"] = {"task": body["result"]}
                headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
                return JSONResponse(body, status_code=response.status_code, headers=headers)
        return response

    from starlette.routing import Route
    app = Starlette(routes=create_agent_card_routes(card) + [Route("/a2a", endpoint, methods=["POST"])])
    app.add_middleware(VersaoV1Padrao)
    return app


app = criar_app()
