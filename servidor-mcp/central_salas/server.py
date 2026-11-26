"""Catálogo MCP: listar_salas devolve o JSON de salas em ambas as representações.

Os arquivos do starter são lidos sem escrita e com caminho independente do cwd.
O SDK é responsável pelo protocolo, schemas e serialização da resposta.
"""

import os
import re
import json
import secrets

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, RequestStateSecurity
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult, TextContent
from pydantic import BaseModel
from starlette.applications import Starlette

from salas import AgendaSalas, ConflitoReserva, ErroDominio
from central_salas.paths import DATA_DIR
from central_salas.request_log import RequestLog
from central_salas.version_guard import ProtocolVersionGuard


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class DisponibilidadeOut(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    reservado: bool
    reserva: str | None = None
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


def create_server() -> MCPServer:
    secret = os.environ.get("REQUEST_STATE_SECRET", "")
    if len(secret) < 64 or len(secret) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", secret):
        raise ValueError("REQUEST_STATE_SECRET deve conter ao menos 32 bytes em hexadecimal")
    security = RequestStateSecurity(keys=[bytes.fromhex(secret)], ttl=900.0)
    server = MCPServer("central-de-salas", version="1.0.0", request_state_security=security)
    agenda = AgendaSalas.carregar(DATA_DIR)

    @server.tool()
    def listar_salas() -> ListaDeSalas:
        """Lista todas as salas com capacidade e recursos."""
        return ListaDeSalas(salas=agenda.listar_salas())

    @server.tool()
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> DisponibilidadeOut:
        """Consulta reservas sobrepostas no intervalo informado."""
        try:
            return DisponibilidadeOut(**agenda.consultar_disponibilidade(sala, inicio, fim))
        except ValueError as erro:
            raise ToolError(str(erro)) from None

    @server.tool()
    def reservar_sala(sala: str, inicio: str, fim: str, responsavel: str, ctx: Context) -> ReservaOut | InputRequiredResult:
        """Retorna a pergunta no HTTP, sem back-channel; recusa não é erro."""
        original = {"sala": sala, "inicio": inicio, "fim": fim, "responsavel": responsavel}
        if ctx.request_state is not None or ctx.input_responses is not None:
            try:
                state = json.loads(ctx.request_state or "")
                key = state["key"]
                alternatives = state["alternatives"]
                if state["arguments"] != original or set(ctx.input_responses or {}) != {key}:
                    raise ValueError
                answer = ctx.input_responses[key]
                if not isinstance(answer, ElicitResult):
                    raise ValueError
                if answer.action in ("decline", "cancel"):
                    return ReservaOut(reservado=False, motivo="Escolha recusada" if answer.action == "decline" else "Escolha cancelada")
                selected = (answer.content or {}).get("sala")
                if not isinstance(selected, str) or selected not in alternatives:
                    raise ValueError
                sala = selected
            except (KeyError, TypeError, ValueError):
                raise MCPError(code=-32602, message="Invalid input response") from None
        try:
            return ReservaOut(**agenda.reservar_sala(sala, inicio, fim, responsavel))
        except ConflitoReserva:
            alternatives = agenda.alternativas(original["sala"], inicio, fim)
            if not alternatives:
                raise ToolError("Sem alternativas disponiveis no intervalo") from None
            capabilities = ctx.client_capabilities
            if capabilities is None or capabilities.elicitation is None or capabilities.elicitation.form is None:
                raise MCPError(code=-32021, message="Missing required client capability", data={"requiredCapabilities": {"elicitation": {"form": {}}}})
            key = secrets.token_urlsafe(16)
            return InputRequiredResult(
                input_requests={key: ElicitRequest(params=ElicitRequestFormParams(
                    message="Escolha uma sala alternativa",
                    requested_schema={"type": "object", "properties": {"sala": {"type": "string", "enum": alternatives}}, "required": ["sala"]},
                ))},
                request_state=json.dumps({"key": key, "arguments": original, "alternatives": alternatives}),
            )
        except ValueError as erro:
            if isinstance(erro, ErroDominio) and str(erro) == f"Sala inexistente: {sala}":
                return CallToolResult(is_error=True, content=[TextContent(type="text", text=str(erro))])
            raise ToolError(str(erro)) from None

    @server.resource("politica://uso", mime_type="text/markdown")
    def politica() -> str:
        """Texto integral da política de uso."""
        return (DATA_DIR / "politica-de-uso.md").read_text(encoding="utf-8")

    return server


def create_app(server: MCPServer | None = None) -> Starlette:
    server = server if server is not None else create_server()
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
    app.add_middleware(ProtocolVersionGuard)
    app.add_middleware(RequestLog)
    return app
