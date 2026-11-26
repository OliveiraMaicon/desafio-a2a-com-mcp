"""Ponte ponta a ponta contra o servidor MCP real, capturando o wire.

O agente roda em processo de teste (ASGI), o MCP em processo separado. O
wrapper de ``httpx2`` registra exatamente os ``tools/call`` emitidos pelo
host, o que permite comparar request inicial, retry, token e id JSON-RPC.
"""

import json
import socket
import sys
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx2
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente.a2a_app import criar_app
from process_harness import ServiceProcess

ROOT = Path(__file__).resolve().parents[1]
ARGS = {"sala": "sala-garagem", "inicio": "2026-11-03T14:00:00-03:00", "fim": "2026-11-03T15:00:00-03:00", "responsavel": "Marty"}
PEDIDO = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
TRACE_A = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
TRACE_B = "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01"


@pytest.fixture
def mcp_process(tmp_path, monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/mcp"
    with ServiceProcess(
        [sys.executable, str(ROOT / "servidor-mcp/main.py")],
        cwd=tmp_path,
        log_dir=tmp_path,
        name="mcp-bridge",
        listen_address=("127.0.0.1", port),
        env={"MCP_PORT": str(port)},
    ) as process:
        process.wait_ready(f"http://127.0.0.1:{port}/", status=404)
        monkeypatch.setenv("MCP_URL", url)
        yield url, process


@pytest.fixture
def captura(monkeypatch):
    registros = []
    original = httpx2.AsyncClient.send

    async def send(self, request, *args, **kwargs):
        response = await original(self, request, *args, **kwargs)
        if request.method == "POST":
            try:
                corpo = json.loads(request.content)
                dados = json.loads(await response.aread())
            except (ValueError, UnicodeDecodeError):
                corpo = dados = None
            if isinstance(corpo, dict) and corpo.get("method") == "tools/call":
                registros.append((corpo, dados))
        return response

    monkeypatch.setattr(httpx2.AsyncClient, "send", send)
    return registros


def send(client, text, task_id=None, traceparent=None):
    message = {"messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    headers = {"traceparent": traceparent} if traceparent else {}
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": message}}, headers=headers).json()


def get_task(client, task_id):
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_id}}).json()["result"]["task"]


def mensagem(task):
    return " ".join(parte["text"] for parte in task["status"]["message"]["parts"])


def artifact(task):
    return json.loads(task["artifacts"][0]["parts"][0]["text"])


def test_retry_preserva_pedido_original_e_nao_vaza_token(captura, mcp_process, monkeypatch):
    guard = AsyncMock(side_effect=AssertionError("elicitation automática não deve ocorrer"))
    monkeypatch.setattr("agente.mcp_host._guard_elicitation", guard)
    with TestClient(criar_app()) as client:
        card = client.get("/.well-known/agent-card.json").json()
        pausada_resp = send(client, PEDIDO, traceparent=TRACE_A)
        pausada = pausada_resp["result"]["task"]
        assert pausada["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(pausada) == "alternativas: sala-fusca, sala-mirante"
        assert not pausada.get("artifacts")

        invalida_resp = send(client, "escolha=sala-aquario", pausada["id"])
        assert invalida_resp["result"]["task"]["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert len(captura) == 1

        concluida_resp = send(client, "escolha=sala-fusca", pausada["id"], traceparent=TRACE_A)
        concluida = concluida_resp["result"]["task"]
        assert concluida["status"]["state"] == "TASK_STATE_COMPLETED"
        assert artifact(concluida)["sala"] == "sala-fusca"
        consulta_resp = get_task(client, pausada["id"])
        assert consulta_resp == concluida
        terminal_resp = send(client, "escolha=sala-mirante", pausada["id"])

    assert len(captura) == 2
    (inicial, resposta_inicial), (retry, resposta_retry) = captura
    assert inicial["id"] != retry["id"]
    assert retry["params"]["arguments"] == inicial["params"]["arguments"] == ARGS
    assert inicial["params"]["_meta"]["traceparent"] == retry["params"]["_meta"]["traceparent"] == TRACE_A
    chave = next(iter(resposta_inicial["result"]["inputRequests"]))
    assert retry["params"]["inputResponses"] == {chave: {"action": "accept", "content": {"sala": "sala-fusca"}}}
    assert retry["params"]["requestState"] == resposta_inicial["result"]["requestState"]
    assert resposta_retry["result"]["structuredContent"]["sala"] == "sala-fusca"
    assert resposta_retry["result"]["structuredContent"]["responsavel"] == "Marty"

    token = resposta_inicial["result"]["requestState"]
    for corpo in (card, pausada_resp, invalida_resp, concluida_resp, consulta_resp, terminal_resp):
        serializado = json.dumps(corpo)
        assert token not in serializado
        assert "requestState" not in serializado
    guard.assert_not_awaited()


def test_duas_tasks_pausadas_retomadas_em_ordem_inversa(captura, mcp_process):
    _, process = mcp_process
    pedido_a = "reservar sala=sala-fusca inicio=2026-11-03T16:00:00-03:00 fim=2026-11-03T17:00:00-03:00 responsavel=Lorraine"
    pedido_b = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=George"
    with TestClient(criar_app()) as client:
        resposta_a = send(client, pedido_a, traceparent=TRACE_A)
        resposta_b = send(client, pedido_b, traceparent=TRACE_B)
        a, b = resposta_a["result"]["task"], resposta_b["result"]["task"]
        assert a["status"]["state"] == b["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert a["id"] != b["id"]

        resposta_rb = send(client, "escolha=sala-mirante", b["id"], traceparent=TRACE_B)
        resposta_ra = send(client, "escolha=sala-mirante", a["id"], traceparent=TRACE_A)
        rb, ra = resposta_rb["result"]["task"], resposta_ra["result"]["task"]
        assert rb["status"]["state"] == ra["status"]["state"] == "TASK_STATE_COMPLETED"
        cb, ca = artifact(rb), artifact(ra)
        assert cb["sala"] == ca["sala"] == "sala-mirante"
        assert cb["responsavel"] == "George" and ca["responsavel"] == "Lorraine"
        assert cb["inicio"] == "2026-11-03T14:00:00-03:00" and ca["inicio"] == "2026-11-03T16:00:00-03:00"
        assert cb["reserva"] != ca["reserva"]
        consulta_b = get_task(client, b["id"])
        consulta_a = get_task(client, a["id"])

    assert len(captura) == 4
    (inicial_a, resposta_wire_a), (inicial_b, resposta_wire_b), (retry_b, _), (retry_a, _) = captura
    token_a = resposta_wire_a["result"]["requestState"]
    token_b = resposta_wire_b["result"]["requestState"]
    assert token_a != token_b
    assert inicial_a["params"]["arguments"]["responsavel"] == "Lorraine"
    assert inicial_b["params"]["arguments"]["responsavel"] == "George"
    assert retry_b["params"]["requestState"] == token_b
    assert retry_a["params"]["requestState"] == token_a
    assert retry_b["params"]["arguments"] == inicial_b["params"]["arguments"]
    assert retry_a["params"]["arguments"] == inicial_a["params"]["arguments"]
    assert retry_b["params"]["inputResponses"] != retry_a["params"]["inputResponses"]
    for corpo in (resposta_a, resposta_b, resposta_rb, resposta_ra, consulta_b, consulta_a):
        serializado = json.dumps(corpo)
        assert token_a not in serializado
        assert token_b not in serializado
        assert "requestState" not in serializado

    logs = [json.loads(line) for line in process.stderr_path.read_text().splitlines() if line.startswith('{"method"')]
    traces = [row["traceparent"] for row in logs if row["method"] == "tools/call"]
    assert traces == [TRACE_A, TRACE_B, TRACE_B, TRACE_A]


def test_pausas_equivalentes_sao_deterministicas_sem_reserva(captura, mcp_process):
    """Duas pausas iguais têm texto idêntico e ids distintos.

    Determinismo não adiciona idempotência de reservas: cada pedido é uma Task
    própria e o conflito é reavaliado pelo MCP, sem reserva criada na pausa.
    """
    with TestClient(criar_app()) as client:
        a_resp = send(client, PEDIDO)
        b_resp = send(client, PEDIDO)
        a, b = a_resp["result"]["task"], b_resp["result"]["task"]
        assert a["id"] != b["id"]
        assert mensagem(a) == mensagem(b) == "alternativas: sala-fusca, sala-mirante"
        assert not a.get("artifacts") and not b.get("artifacts")

    assert len(captura) == 2
    assert all(corpo["params"]["arguments"] == ARGS for corpo, _ in captura)
