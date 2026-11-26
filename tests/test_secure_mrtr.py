"""MRTR via HTTP: o token nunca é inspecionado ou registrado pelo cliente."""

import sys
import time
import socket
import importlib.util
import contextlib
import io
import json

import httpx
import pytest
from starlette.testclient import TestClient

from central_salas.paths import PROJECT_ROOT
from central_salas.server import create_app
from process_harness import ServiceProcess
from test_mcp_transport import request

ARGS = {"sala": "sala-garagem", "inicio": "2026-11-03T14:00:00-03:00", "fim": "2026-11-03T15:00:00-03:00", "responsavel": "Marty"}


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://127.0.0.1:7301") as client:
        yield client


def send(client, args=None, **extra):
    headers, body = request("tools/call", request_id=extra.pop("request_id", 1), name=extra.pop("name", "reservar_sala"), arguments=args or ARGS)
    caps = extra.pop("caps", None)
    if caps is not None:
        body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"] = caps
    body["params"].update(extra)
    return client.post("/mcp", headers=headers, json=body)


def pause(client):
    response = send(client)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["resultType"] == "input_required"
    return result


def retry(client, result, action="accept", selected="sala-fusca", key=None, **extra):
    key = key or next(iter(result["inputRequests"]))
    answer = {"action": action}
    if action == "accept":
        answer["content"] = {"sala": selected}
    return send(client, request_id=2, requestState=result["requestState"], inputResponses={key: answer}, **extra)


def available(client, sala="sala-fusca"):
    response = send(client, name="consultar_disponibilidade", args={"sala": sala, "inicio": ARGS["inicio"], "fim": ARGS["fim"]})
    return response.json()["result"]["structuredContent"]["livre"]


def test_pause_and_accept(client):
    result = pause(client)
    assert available(client)
    assert len(result["inputRequests"]) == 1
    question = next(iter(result["inputRequests"].values()))
    schema = question["params"]["requestedSchema"]
    assert question["method"] == "elicitation/create" and question["params"]["mode"] == "form"
    assert schema["type"] == "object" and schema["required"] == ["sala"]
    assert schema["properties"]["sala"]["enum"] == ["sala-fusca", "sala-mirante"]
    response = retry(client, result)
    assert response.status_code == 200
    done = response.json()["result"]
    assert done["resultType"] == "complete" and done["structuredContent"]["reservado"]
    assert done["structuredContent"]["sala"] == "sala-fusca"
    assert done["structuredContent"]["responsavel"] == ARGS["responsavel"]
    assert done["structuredContent"]["inicio"] == ARGS["inicio"] and done["structuredContent"]["fim"] == ARGS["fim"]


@pytest.mark.parametrize("caps", [{}, {"elicitation": {}}])
def test_missing_form(client, caps):
    response = send(client, caps=caps)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32021
    assert response.json()["error"]["data"]["requiredCapabilities"] == {"elicitation": {"form": {}}}
    assert available(client)


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_decline_cancel(client, action):
    done = retry(client, pause(client), action=action).json()["result"]
    assert done["resultType"] == "complete" and not done.get("isError", False)
    assert not done["structuredContent"]["reservado"] and done["structuredContent"]["motivo"]
    assert available(client)


@pytest.mark.parametrize("field,value", [("sala", "sala-fusca"), ("inicio", "2026-11-03T13:30:00-03:00"), ("fim", "2026-11-03T15:30:00-03:00"), ("responsavel", "Doc")])
def test_changed_arguments(client, field, value):
    result = pause(client)
    response = retry(client, result, args={**ARGS, field: value})
    assert response.json()["error"]["code"] == -32602
    assert available(client)
    query = {"sala": "sala-fusca", "inicio": ARGS["inicio"], "fim": ARGS["fim"]}
    if field in ("inicio", "fim"):
        query[field] = value
    assert send(client, name="consultar_disponibilidade", args=query).json()["result"]["structuredContent"]["livre"]


def test_wrong_key_and_choice(client):
    result = pause(client)
    assert retry(client, result, key="wrong").json()["error"]["code"] == -32602
    assert retry(client, result, selected="sala-aquario").json()["error"]["code"] == -32602
    assert available(client) and available(client, "sala-aquario")


@pytest.mark.parametrize("mutation", ["prefix", "suffix", "malformed"])
def test_tampered_and_other_tool(client, mutation):
    result = pause(client)
    token = result["requestState"]
    modified = {"prefix": ("A" if token[0] != "A" else "B") + token[1:], "suffix": token[:-6] + "!!!!!!", "malformed": "not-a-token"}[mutation]
    key = next(iter(result["inputRequests"]))
    response = send(client, requestState=modified, inputResponses={key: {"action": "decline"}})
    assert response.json()["error"]["code"] == -32602
    assert available(client)
    response = send(client, name="consultar_disponibilidade", args={k: ARGS[k] for k in ("sala", "inicio", "fim")}, requestState=token, inputResponses={key: {"action": "decline"}})
    assert response.json()["error"]["code"] == -32602


def test_expiry(client, monkeypatch):
    import mcp.server.request_state as state
    clock = time.time()
    monkeypatch.setattr(state.time, "time", lambda: clock)
    result = pause(client)
    monkeypatch.setattr(state.time, "time", lambda: clock + 901)
    assert retry(client, result).json()["error"]["code"] == -32602
    assert available(client)


def test_alternative_taken(client):
    result = pause(client)
    assert send(client, args={**ARGS, "sala": "sala-fusca"}).json()["result"]["structuredContent"]["reservado"]
    again = retry(client, result).json()["result"]
    assert again["resultType"] == "input_required"
    question = next(iter(again["inputRequests"].values()))
    assert question["params"]["requestedSchema"]["properties"]["sala"]["enum"] == ["sala-mirante"]
    assert available(client, "sala-mirante")


def test_no_alternative(client):
    occupied = {**ARGS, "sala": "sala-mirante"}
    assert send(client, args=occupied).json()["result"]["structuredContent"]["reservado"]
    result = send(client, args=occupied, caps={}).json()["result"]
    assert result["resultType"] == "complete" and result["isError"]
    assert "Sem alternativas disponiveis no intervalo" in result["content"][0]["text"]


def test_restart(tmp_path):
    env = {"REQUEST_STATE_SECRET": "ab" * 32}
    def free_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]
    def process(name, port):
        return ServiceProcess([sys.executable, str(PROJECT_ROOT / "servidor-mcp" / "main.py")], cwd=tmp_path, log_dir=tmp_path, name=name, listen_address=("127.0.0.1", port), env={**env, "MCP_PORT": str(port)})
    before, after = free_port(), free_port()
    with process("before", before) as server:
        with httpx.Client(base_url=f"http://127.0.0.1:{before}", timeout=5) as client:
            server.wait_ready(f"http://127.0.0.1:{before}/", status=404)
            result = pause(client)
    with process("after", after) as server:
        with httpx.Client(base_url=f"http://127.0.0.1:{after}", timeout=5) as client:
            server.wait_ready(f"http://127.0.0.1:{after}/", status=404)
            assert retry(client, result).json()["result"]["structuredContent"]["reservado"]
    for path in tmp_path.glob("*.stderr"):
        log = path.read_text()
        assert env["REQUEST_STATE_SECRET"] not in log and result["requestState"] not in log


def test_original_validator_mcp_only(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    secret = "cd" * 32
    spec = importlib.util.spec_from_file_location("validador_original", PROJECT_ROOT / "validador" / "validar.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    with ServiceProcess([sys.executable, str(PROJECT_ROOT / "servidor-mcp" / "main.py")], cwd=tmp_path, log_dir=tmp_path, name="validator", listen_address=("127.0.0.1", port), env={"REQUEST_STATE_SECRET": secret, "MCP_PORT": str(port)}) as server:
        server.wait_ready(f"http://127.0.0.1:{port}/", status=404)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            token = validator.verificar_mcp(f"http://127.0.0.1:{port}/mcp")
        assert (validator.R.passou, validator.R.falhou) == (20, 0), output.getvalue()
    log = server.stderr_path.read_text()
    assert secret not in log and token not in log
    for body in validator.R.corpos:
        state = json.loads(body).get("result", {}).get("requestState")
        if state:
            assert state not in log
    entries = [json.loads(line) for line in log.splitlines() if line.startswith('{"method"')]
    ids = [entry["id"] for entry in entries]
    assert len(ids) >= 20 and len(ids) == len(set(ids))
