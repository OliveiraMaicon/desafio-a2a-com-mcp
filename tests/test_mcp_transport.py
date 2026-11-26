"""Gate HTTP incremental; nunca modifica dados, exemplos ou validador."""

import asyncio
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
import jsonschema
import pytest
from starlette.testclient import TestClient
from mcp.server import MCPServer

from central_salas.paths import DATA_DIR, PROJECT_ROOT
from central_salas.server import create_app
from central_salas.version_guard import ProtocolVersionGuard
from process_harness import ServiceProcess


def wire(number: str) -> dict:
    path = next((PROJECT_ROOT / "exemplos" / "wire").glob(f"{number}-*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def request(method="tools/list", *, request_id=1, **params):
    body = copy.deepcopy(wire("01")["request"]["body"])
    body.update(method=method, id=request_id)
    body["params"].update(params)
    headers = dict(wire("01")["request"]["headers"])
    headers["Mcp-Method"] = method
    if method in ("tools/call", "resources/read"):
        headers["Mcp-Name"] = params.get("name", params.get("uri"))
    return headers, body


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://127.0.0.1:7301") as client:
        yield client


def test_entrypoint_default_port_and_foreign_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_PORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    with ServiceProcess(
        [sys.executable, str(PROJECT_ROOT / "servidor-mcp" / "main.py")],
        cwd=tmp_path,
        log_dir=tmp_path,
        name="mcp",
        listen_address=("127.0.0.1", 7301),
    ) as process:
        process.wait_ready("http://127.0.0.1:7301/", status=404)
        headers, body = request()
        response = httpx.post("http://127.0.0.1:7301/mcp", headers=headers, json=body)
        assert response.status_code == 200
        assert response.json()["result"]["resultType"] == "complete"
        headers, body = request("tools/call", name="listar_salas", arguments={})
        response = httpx.post("http://127.0.0.1:7301/mcp", headers=headers, json=body)
        assert response.json()["result"]["structuredContent"]["salas"] == json.loads(
            (DATA_DIR / "salas.json").read_text(encoding="utf-8")
        )
        example = wire("05")
        response = httpx.post("http://127.0.0.1:7301/mcp", headers=example["request"]["headers"], json=example["request"]["body"])
        assert response.status_code == example["response"]["httpStatus"]
        assert response.json()["result"]["contents"] == example["response"]["body"]["result"]["contents"]
        assert response.json()["result"]["resultType"] == "complete"
        assert DATA_DIR == PROJECT_ROOT / "dados"
        assert (DATA_DIR / "salas.json").is_file()


def test_discovery_without_initialize(client):
    headers, body = request()
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in response.headers
    assert response.json()["jsonrpc"] == "2.0"
    assert response.json()["id"] == body["id"]
    assert response.json()["result"]["resultType"] == "complete"


def test_listar_salas_schema_and_content(client):
    headers, body = request()
    tools = client.post("/mcp", headers=headers, json=body).json()["result"]["tools"]
    tool = next(tool for tool in tools if tool["name"] == "listar_salas")
    assert tool["inputSchema"]["type"] == "object"
    assert tool["outputSchema"]["type"] == "object"
    jsonschema.Draft202012Validator.check_schema(tool["inputSchema"])
    jsonschema.Draft202012Validator.check_schema(tool["outputSchema"])
    headers, body = request("tools/call", name="listar_salas", arguments={})
    result = client.post("/mcp", headers=headers, json=body).json()["result"]
    structured = result["structuredContent"]
    jsonschema.validate(structured, tool["outputSchema"])
    assert structured["salas"] == json.loads((DATA_DIR / "salas.json").read_text(encoding="utf-8"))
    assert len(structured["salas"]) == 5
    assert json.loads(result["content"][0]["text"]) == structured
    assert result["resultType"] == "complete"


def test_server_declares_tools_and_resources():
    from central_salas.server import create_server

    capabilities = create_server()._lowlevel_server.create_initialization_options().capabilities
    assert capabilities.tools is not None
    assert capabilities.resources is not None


def test_policy_resource_and_unknown_operations(client):
    headers, body = request("resources/read", uri="politica://uso")
    result = client.post("/mcp", headers=headers, json=body).json()["result"]
    content = result["contents"][0]
    assert result["resultType"] == "complete"
    assert content["uri"] == "politica://uso"
    assert content["mimeType"] == "text/markdown"
    assert content["text"] == (DATA_DIR / "politica-de-uso.md").read_text(encoding="utf-8")
    assert content["text"].splitlines()[0] == "versao: 2026-11-01"
    headers, body = request("resources/read", uri="politica://inexistente")
    assert client.post("/mcp", headers=headers, json=body).json()["error"]["code"] == -32602
    headers, body = request("tools/call", name="voar_delorean", arguments={})
    response = client.post("/mcp", headers=headers, json=body).json()
    assert response.get("error", {}).get("code") == -32602 or response.get("result", {}).get("isError") is True


@pytest.mark.parametrize("rejected", [False, True])
def test_request_log_includes_context_without_body(client, capsys, rejected):
    headers, body = request("tools/call", request_id="log-id", name="listar_salas", arguments={"secret": "NAO_REGISTRAR"})
    trace = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    body["params"]["_meta"]["traceparent"] = trace
    if rejected:
        del body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == (400 if rejected else 200)
    if not rejected:
        assert len(response.json()["result"]["structuredContent"]["salas"]) == 5
    log = capsys.readouterr().err
    assert json.loads(log) == {"method": "tools/call", "id": "log-id", "traceparent": trace}
    assert "NAO_REGISTRAR" not in log


@pytest.mark.parametrize("after_valid", [False, True])
@pytest.mark.parametrize(
    "missing",
    ["io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientCapabilities"],
)
def test_missing_metadata_is_rejected_per_request(client, missing, after_valid):
    if after_valid:
        headers, body = request()
        assert client.post("/mcp", headers=headers, json=body).status_code == 200
    headers, body = request(request_id="metadado-ausente")
    del body["params"]["_meta"][missing]
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["id"] == "metadado-ausente"
    assert response.json()["error"]["code"] == -32602


@pytest.mark.parametrize(
    "mismatch", ["version-body", "version-header", "method", "tool-name", "resource-name"]
)
def test_header_mismatch_does_not_execute_operation(mismatch):
    calls = []
    server = MCPServer("header-probe")

    @server.tool()
    def sentinela() -> str:
        calls.append("tool")
        return "executada"

    @server.resource("politica://sentinela", mime_type="text/plain")
    def resource_sentinela() -> str:
        calls.append("resource")
        return "executada"

    headers, body = request("tools/call", name="sentinela", arguments={})
    if mismatch == "version-body":
        body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2025-11-25"
    elif mismatch == "version-header":
        headers["MCP-Protocol-Version"] = "2025-11-25"
    elif mismatch == "method":
        headers["Mcp-Method"] = "tools/list"
    elif mismatch == "tool-name":
        headers["Mcp-Name"] = "outra"
    else:
        headers, body = request("resources/read", uri="politica://sentinela")
        headers["Mcp-Name"] = "politica://outra"

    with TestClient(create_app(server), base_url="http://127.0.0.1:7301") as client:
        response = client.post("/mcp", headers=headers, json=body)
        assert response.json()["error"]["code"] == -32020
        assert response.json()["id"] == body["id"]
        assert calls == []


@pytest.mark.parametrize("legacy", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"])
@pytest.mark.parametrize("request_id", [0, "legacy-check"])
def test_each_legacy_header_rejects_modern_metadata(legacy, request_id, client):
    headers, body = request(request_id=request_id)
    headers["MCP-Protocol-Version"] = legacy
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["id"] == request_id
    assert response.json()["error"]["code"] == -32020


def test_guard_delegates_malformed_body_to_sdk(client):
    headers, _ = request()
    headers["MCP-Protocol-Version"] = "2025-11-25"
    response = client.post("/mcp", headers=headers, content=b"{bad json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700


def test_legacy_header_does_not_mask_missing_modern_metadata(client):
    headers, body = request()
    headers["MCP-Protocol-Version"] = "2026-07-28"
    del body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32602


def test_absent_header_does_not_route_modern_body_to_legacy(client):
    headers, body = request(request_id="sem-header")
    del headers["MCP-Protocol-Version"]
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["id"] == "sem-header"
    assert response.json()["error"]["code"] == -32020


def test_guard_handles_simultaneous_requests(client):
    def send(index):
        headers, body = request(request_id=index)
        if index % 2:
            headers["MCP-Protocol-Version"] = "2025-11-25"
        return client.post("/mcp", headers=headers, json=body).json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(12)))
    for index, result in enumerate(responses):
        assert result["id"] == index
        if index % 2:
            assert result["error"]["code"] == -32020
        else:
            assert result["result"]["resultType"] == "complete"


@pytest.mark.parametrize("modern_body", [True, False])
def test_guard_preserves_or_rejects_fragmented_body(modern_body):
    received = []
    sent = []
    version = "2026-07-28" if modern_body else "2025-11-25"
    payload = json.dumps({"jsonrpc": "2.0", "id": "fragmentado", "params": {
        "_meta": {"io.modelcontextprotocol/protocolVersion": version}
    }}).encode()
    events = [
        {"type": "http.request", "body": payload[:12], "more_body": True},
        {"type": "http.request", "body": payload[12:], "more_body": False},
    ]

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, read, write):
        received.append(await read())
        received.append(await read())

    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": [
        (b"mcp-protocol-version", b"2025-11-25")
    ]}
    asyncio.run(ProtocolVersionGuard(downstream)(scope, receive, send))
    if modern_body:
        assert not received
        assert sent[0]["status"] == 400
        assert json.loads(sent[1]["body"])["id"] == "fragmentado"
        assert json.loads(sent[1]["body"])["error"]["code"] == -32020
    else:
        assert b"".join(event["body"] for event in received) == payload
        assert received[0]["more_body"] is True
        assert received[1]["more_body"] is False
        assert not sent
