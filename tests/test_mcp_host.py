"""Exercício do host contra processo MCP separado, sem A2A."""

import asyncio
import ast
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente.mcp_host import MCPHost, Completo, Pendente, ContratoMCPInvalido, _alternativas
from process_harness import ServiceProcess

ROOT = Path(__file__).resolve().parents[1]
ARGS = {"sala": "sala-garagem", "inicio": "2026-11-03T14:00:00-03:00", "fim": "2026-11-03T15:00:00-03:00", "responsavel": "Marty"}
TRACE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
TRACE2 = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"


@pytest.fixture
def server(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with ServiceProcess([sys.executable, str(ROOT / "servidor-mcp/main.py")], cwd=tmp_path, log_dir=tmp_path, name="host", listen_address=("127.0.0.1", port), env={"MCP_PORT": str(port)}) as process:
        process.wait_ready(f"http://127.0.0.1:{port}/", status=404)
        yield f"http://127.0.0.1:{port}/mcp", process


@pytest.fixture
def requests(monkeypatch):
    seen = []
    original = httpx2.AsyncClient.send

    async def capture(self, request, *args, **kwargs):
        if request.method == "POST":
            seen.append((dict(request.headers), json.loads(request.content)))
        return await original(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx2.AsyncClient, "send", capture)
    return seen


def test_manual_cycle(server, requests, monkeypatch):
    url, process = server
    guard = AsyncMock(side_effect=AssertionError("elicitation automática"))
    monkeypatch.setattr("agente.mcp_host._guard_elicitation", guard)
    continuation = {}

    async def run():
        async with MCPHost(url) as host:
            args = dict(ARGS)
            pending = await host.iniciar("reservar_sala", args, traceparent=TRACE)
            assert isinstance(pending, Pendente)
            assert pending.alternativas == ("sala-fusca", "sala-mirante")
            assert pending.versao_politica == "2026-11-01"
            continuation.update(token=pending._token, key=pending._chave)
            args["responsavel"] = "modificado"
            assert len([b for _, b in requests if b["method"] == "tools/call"]) == 1
            check = await host.iniciar("consultar_disponibilidade", {k: ARGS[k] for k in ("inicio", "fim")} | {"sala": "sala-fusca"}, traceparent=TRACE2)
            assert check.resultado.structured_content["livre"]
            done = await host.retomar(pending, "accept", escolha="sala-fusca")
            assert isinstance(done, Completo) and done.resultado.structured_content["reservado"]
            assert done.resultado.structured_content["responsavel"] == "Marty"
            error = await host.iniciar("reservar_sala", ARGS | {"sala": "sala-delorean"}, traceparent=TRACE2)
            assert error.erro == "Sala inexistente: sala-delorean"
            with pytest.raises(ContratoMCPInvalido, match="não encontrada"):
                await host.iniciar("ausente", {})
        with pytest.raises(RuntimeError, match="não conectado"):
            await host.iniciar("reservar_sala", ARGS)

    asyncio.run(run())
    guard.assert_not_awaited()
    messages = [(h, b) for h, b in requests if b["method"] != "server/discover"]
    assert [b["method"] for _, b in messages][:3] == ["tools/list", "resources/read", "tools/call"]
    calls = [(h, b) for h, b in messages if b["method"] == "tools/call"]
    assert len({b["id"] for _, b in messages}) == len(messages)
    assert calls[0][1]["params"]["_meta"]["traceparent"] == TRACE
    assert calls[1][1]["params"]["_meta"]["traceparent"] == TRACE2
    assert calls[2][1]["params"]["_meta"]["traceparent"] == TRACE
    assert calls[2][1]["params"]["arguments"] == ARGS
    assert calls[2][1]["params"]["requestState"].encode() == continuation["token"].encode()
    assert calls[2][1]["params"]["inputResponses"] == {continuation["key"]: {"action": "accept", "content": {"sala": "sala-fusca"}}}
    log = [json.loads(line) for line in process.stderr_path.read_text().splitlines() if line.startswith('{"method"')]
    methods = [entry["method"] for entry in log]
    assert methods.index("tools/list") < methods.index("tools/call")
    for headers, body in messages:
        params = body["params"]
        meta = params["_meta"]
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert meta["io.modelcontextprotocol/clientCapabilities"]["elicitation"]["form"] == {}
        assert headers["mcp-protocol-version"] == "2026-07-28"
        assert headers["mcp-method"] == body["method"]
        if body["method"] in ("tools/call", "resources/read"):
            assert headers["mcp-name"] == params.get("name", params.get("uri"))


def test_decline(server, requests):
    continuation = {}
    async def run():
        async with MCPHost(server[0]) as host:
            pending = await host.iniciar("reservar_sala", ARGS)
            continuation.update(token=pending._token, key=pending._chave)
            result = await host.retomar(pending, "decline")
            assert not result.resultado.structured_content["reservado"]
            available = await host.iniciar("consultar_disponibilidade", {k: ARGS[k] for k in ("inicio", "fim")} | {"sala": "sala-fusca"})
            assert available.resultado.structured_content["livre"]
    asyncio.run(run())
    calls = [body for _, body in requests if body["method"] == "tools/call"]
    assert calls[1]["id"] != calls[0]["id"]
    assert calls[1]["params"]["requestState"].encode() == continuation["token"].encode()
    assert calls[1]["params"]["inputResponses"] == {continuation["key"]: {"action": "decline"}}


def test_alternativa_unica():
    assert _alternativas({"properties": {"sala": {"const": "unica"}}}) == ("unica",)


def test_free_reservation(server):
    async def run():
        async with MCPHost(server[0]) as host:
            result = await host.iniciar("reservar_sala", ARGS | {"sala": "sala-fusca"})
            assert isinstance(result, Completo)
            assert result.resultado.structured_content["reservado"]
    asyncio.run(run())


def test_protocol_error_is_not_execution_result(server):
    from mcp.shared.exceptions import MCPError

    async def run():
        async with MCPHost(server[0]) as host:
            pending = await host.iniciar("reservar_sala", ARGS)
            with pytest.raises(MCPError):
                await host.retomar(pending, "accept", escolha="sala-invalida")
    asyncio.run(run())


def test_invalid_policy_is_controlled():
    from mcp import types

    async def run():
        host = MCPHost()
        host._session = SimpleNamespace(
            list_tools=AsyncMock(return_value=SimpleNamespace(tools=[], next_cursor=None)),
            read_resource=AsyncMock(return_value=SimpleNamespace(contents=[types.TextResourceContents(uri="politica://uso", text="versao invalida")]))
        )
        with pytest.raises(ContratoMCPInvalido, match="política inválida"):
            await host.iniciar("reservar_sala", {})
    asyncio.run(run())


def test_host_does_not_import_server_domain():
    tree = ast.parse((ROOT / "agente/mcp_host.py").read_text())
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(name == "salas" or name.startswith("central_salas") for name in imports)
