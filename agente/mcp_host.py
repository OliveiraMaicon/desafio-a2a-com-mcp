"""Cliente MCP HTTP com continuação manual, sem dependência do servidor.

Use ``async with MCPHost() as host``; ``iniciar`` retorna ``Completo`` ou
``Pendente`` imediatamente. Passe a continuação e uma resposta explícita a
``retomar``. Erros de execução são resultados; erros de transporte/protocolo
propagam como exceções do SDK. Catálogo e política são cache da aplicação por
conexão, não uma sessão de protocolo no servidor stateless.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Literal

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp import types


class ContratoMCPInvalido(RuntimeError):
    """Catálogo, política ou pergunta recebida não têm o formato esperado."""


async def _guard_elicitation(context: Any, params: Any) -> Any:
    raise RuntimeError("Callback de elicitation inesperado: use a continuação manual")


@dataclass(frozen=True)
class Completo:
    """Resultado da tool; ``erro`` preserva o texto de falha de execução."""

    resultado: types.CallToolResult
    versao_politica: str
    erro: str | None = None


@dataclass(frozen=True)
class Pendente:
    """Pergunta visível e estado privado opaco para posterior retomada."""

    pergunta: str
    alternativas: tuple[str, ...]
    versao_politica: str
    _nome: str = field(repr=False)
    _argumentos: dict[str, Any] = field(repr=False)
    _chave: str = field(repr=False)
    _token: str = field(repr=False)
    _traceparent: str | None = field(repr=False)


def _meta(traceparent: str | None) -> dict[str, Any]:
    return {"traceparent": traceparent} if traceparent else {}


def _alternativas(schema: dict[str, Any]) -> tuple[str, ...]:
    try:
        sala = schema["properties"]["sala"]
        if "enum" in sala:
            values = sala["enum"]
        elif "const" in sala:
            values = [sala["const"]]
        else:
            values = [item["const"] for item in sala["anyOf"]]
        if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
            raise ValueError
        return tuple(values)
    except (KeyError, TypeError, ValueError):
        raise ContratoMCPInvalido("Alternativas de elicitation inválidas") from None


class MCPHost:
    """Transporte e sessão do SDK; cada operação carrega seu próprio trace."""

    def __init__(self, url: str = "http://localhost:7301/mcp") -> None:
        self.url = url
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: dict[str, types.Tool] | None = None
        self._politica: str | None = None

    async def __aenter__(self) -> MCPHost:
        if self._stack is not None:
            raise RuntimeError("Host já conectado")
        stack = AsyncExitStack()
        try:
            streams = await stack.enter_async_context(streamable_http_client(self.url))
            session = await stack.enter_async_context(ClientSession(*streams, elicitation_callback=_guard_elicitation))
            await session.discover()
        except BaseException:
            await stack.aclose()
            raise
        self._stack, self._session = stack, session
        return self

    async def __aexit__(self, *exc: Any) -> None:
        stack, self._stack = self._stack, None
        self._session = None
        self._tools = self._politica = None
        if stack:
            await stack.__aexit__(*exc)

    def _conexao(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Host não conectado")
        return self._session

    async def _contexto(self, traceparent: str | None) -> None:
        session = self._conexao()
        if self._tools is None:
            tools: dict[str, types.Tool] = {}
            cursor = None
            while True:
                page = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor, _meta=_meta(traceparent)))
                tools.update((tool.name, tool) for tool in page.tools)
                cursor = page.next_cursor
                if not cursor:
                    break
            self._tools = tools
        if self._politica is None:
            resource = await session.read_resource("politica://uso", meta=_meta(traceparent))
            text = resource.contents[0].text if resource.contents and isinstance(resource.contents[0], types.TextResourceContents) else ""
            match = re.fullmatch(r"versao: (\d{4}-\d{2}-\d{2})", text.splitlines()[0] if text else "")
            if match is None:
                raise ContratoMCPInvalido("Primeira linha da política inválida")
            self._politica = match.group(1)

    async def iniciar(self, nome: str, argumentos: dict[str, Any], *, traceparent: str | None = None) -> Completo | Pendente:
        """Descobre catálogo e política, chama uma vez e retorna sem decidir."""
        await self._contexto(traceparent)
        tool = (self._tools or {}).get(nome)
        if tool is None:
            raise ContratoMCPInvalido(f"Tool não encontrada no catálogo: {nome}")
        if tool.input_schema.get("type") != "object" or not isinstance(tool.input_schema.get("properties"), dict):
            raise ContratoMCPInvalido(f"Schema inválido da tool: {nome}")
        args = deepcopy(argumentos)
        result = await self._conexao().call_tool(nome, args, meta=_meta(traceparent), allow_input_required=True)
        return self._resultado(result, nome, args, traceparent)

    async def retomar(self, pendente: Pendente, action: Literal["accept", "decline", "cancel"], *, escolha: str | None = None, traceparent: str | None = None) -> Completo | Pendente:
        """Encaminha resposta explícita, preservando argumentos, chave e token."""
        if action not in ("accept", "decline", "cancel") or (action == "accept" and escolha is None):
            raise ValueError("Resposta de elicitation inválida")
        trace = traceparent if traceparent is not None else pendente._traceparent
        answer = types.ElicitResult(action=action, content={"sala": escolha} if action == "accept" else None)
        args = deepcopy(pendente._argumentos)
        result = await self._conexao().call_tool(pendente._nome, args, input_responses={pendente._chave: answer}, request_state=pendente._token, meta=_meta(trace), allow_input_required=True)
        return self._resultado(result, pendente._nome, args, trace, pendente.versao_politica)

    def _resultado(self, result: Any, nome: str, args: dict[str, Any], trace: str | None, politica: str | None = None) -> Completo | Pendente:
        version = politica or self._politica
        if version is None:
            raise ContratoMCPInvalido("Política indisponível")
        if isinstance(result, types.CallToolResult):
            erro = "\n".join(item.text for item in result.content if isinstance(item, types.TextContent)) if result.is_error else None
            return Completo(result, version, erro)
        if not isinstance(result, types.InputRequiredResult) or len(result.input_requests) != 1 or not isinstance(result.request_state, str):
            raise ContratoMCPInvalido("Continuação MCP inválida")
        key, question = next(iter(result.input_requests.items()))
        if not isinstance(question, types.ElicitRequest) or not isinstance(question.params, types.ElicitRequestFormParams):
            raise ContratoMCPInvalido("Elicitation form esperada")
        return Pendente(question.params.message, _alternativas(question.params.requested_schema), version, nome, deepcopy(args), key, result.request_state, trace)
