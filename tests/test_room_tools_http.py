"""Contratos HTTP das tools de salas, com estado isolado por teste."""

import json

import jsonschema
import pytest
from starlette.testclient import TestClient

from central_salas.paths import DATA_DIR
from central_salas.server import create_app
from test_mcp_transport import request


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://127.0.0.1:7301") as client:
        yield client


def call(client, name, **arguments):
    headers, body = request("tools/call", name=name, arguments=arguments)
    response = client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["resultType"] == "complete"
    return result


def args(sala="sala-aquario", inicio="2026-11-03T09:00:00-03:00", fim="2026-11-03T10:00:00-03:00"):
    return {"sala": sala, "inicio": inicio, "fim": fim}


def test_discovery_schemas_and_equivalent_json(client):
    headers, body = request()
    tools = {tool["name"]: tool for tool in client.post("/mcp", headers=headers, json=body).json()["result"]["tools"]}
    assert set(tools) == {"listar_salas", "consultar_disponibilidade", "reservar_sala"}
    for name, required in (("listar_salas", set()), ("consultar_disponibilidade", {"sala", "inicio", "fim"}), ("reservar_sala", {"sala", "inicio", "fim", "responsavel"})):
        tool = tools[name]
        for schema in (tool["inputSchema"], tool["outputSchema"]):
            assert schema["type"] == "object"
            jsonschema.Draft202012Validator.check_schema(schema)
        assert set(tool["inputSchema"].get("required", [])) == required
    for name, arguments in (("listar_salas", {}), ("consultar_disponibilidade", args()), ("reservar_sala", {**args(), "responsavel": "Doc"})):
        result = call(client, name, **arguments)
        assert not result.get("isError", False)
        jsonschema.validate(result["structuredContent"], tools[name]["outputSchema"])
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    jsonschema.validate({"reservado": False, "motivo": "recusa"}, tools["reservar_sala"]["outputSchema"])


@pytest.mark.parametrize("name", ["consultar_disponibilidade", "reservar_sala"])
@pytest.mark.parametrize("arguments,message", [
    (args(sala="sala-delorean"), "Sala inexistente: sala-delorean"),
    (args(inicio="2026-11-03T07:00:00-03:00", fim="2026-11-03T08:00:00-03:00"), "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"),
    (args(fim="2026-11-03T12:00:00-03:00"), "Duracao acima do limite: a politica permite no maximo 2 horas"),
    (args(fim="2026-11-03T09:00:00-03:00"), "Intervalo invalido: fim deve ser posterior a inicio"),
])
def test_validation_errors_are_complete(client, name, arguments, message):
    if name == "reservar_sala":
        arguments = {**arguments, "responsavel": "Doc"}
    result = call(client, name, **arguments)
    assert result["isError"] is True
    assert message in result["content"][0]["text"]


def test_reservation_unknown_room_exact_error_and_other_errors_unchanged(client):
    missing = call(client, "reservar_sala", **args(sala="sala-delorean"), responsavel="Doc")
    assert missing["isError"] is True
    assert missing["content"] == [{"type": "text", "text": "Sala inexistente: sala-delorean"}]
    invalid = call(client, "reservar_sala", **args(fim="2026-11-03T09:00:00-03:00"), responsavel="Doc")
    assert invalid["isError"] is True
    assert invalid["content"][0]["text"] == "Error executing tool reservar_sala: Intervalo invalido: fim deve ser posterior a inicio"


def test_consult_create_conflict_and_starter_preserved(client):
    before = {path: path.read_bytes() for path in DATA_DIR.iterdir()}
    occupied = args("sala-garagem", "2026-11-03T14:00:00-03:00", "2026-11-03T15:00:00-03:00")
    original = call(client, "consultar_disponibilidade", **occupied)["structuredContent"]
    assert original == {"sala": "sala-garagem", "livre": False, "conflitos": [{"id": "res-0001", "inicio": occupied["inicio"], "fim": occupied["fim"], "responsavel": "Marty"}]}
    headers, body = request("tools/call", name="reservar_sala", arguments={**occupied, "responsavel": "Doc"})
    result = client.post("/mcp", headers=headers, json=body).json()["result"]
    assert result["resultType"] == "input_required"
    assert call(client, "consultar_disponibilidade", **occupied)["structuredContent"] == original
    adjacent = args("sala-garagem", "2026-11-03T15:00:00-03:00", "2026-11-03T16:00:00-03:00")
    assert call(client, "consultar_disponibilidade", **adjacent)["structuredContent"]["livre"] is True
    created = call(client, "reservar_sala", **adjacent, responsavel="Doc")["structuredContent"]
    assert created["reserva"] == "res-0003"
    assert created["reservado"] is True
    assert {key: created[key] for key in adjacent} == adjacent
    assert created["responsavel"] == "Doc" and created["politica"] == "2026-11-01"
    assert call(client, "consultar_disponibilidade", **adjacent)["structuredContent"]["conflitos"][0]["id"] == created["reserva"]
    assert before == {path: path.read_bytes() for path in DATA_DIR.iterdir()}
