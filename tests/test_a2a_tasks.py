import json
import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from mcp.shared.exceptions import MCPError
from starlette.testclient import TestClient
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.context import ServerCallContext
from a2a.types.a2a_pb2 import Task, TaskState, TaskStatus

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente.a2a_app import criar_app
from agente.mcp_host import Completo, Pendente
from process_harness import ServiceProcess

ROOT = Path(__file__).resolve().parents[1]
PEDIDO = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
ARGS = {"sala": "sala-garagem", "inicio": "2026-11-03T14:00:00-03:00", "fim": "2026-11-03T15:00:00-03:00", "responsavel": "Marty"}
TRACE = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
TRACE2 = "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01"


def send(client, text, task_id=None, traceparent=None):
    message = {"messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    headers = {"traceparent": traceparent} if traceparent else {}
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": message}}, headers=headers).json()


async def send_async(client, text, task_id=None, traceparent=None):
    message = {"messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    headers = {"traceparent": traceparent} if traceparent else {}
    response = await client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": message}}, headers=headers)
    return response.json()


def get_task(client, task_id):
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_id}}).json()["result"]["task"]


def mensagem(task):
    return " ".join(parte["text"] for parte in task["status"]["message"]["parts"])


def artifact(task):
    return json.loads(task["artifacts"][0]["parts"][0]["text"])


class HostFalso:
    """Host MCP controlável: pausa, retoma, recusa e falha sem rede."""

    def __init__(self):
        self.iniciados = []
        self.pendentes = []
        self.retomados = []
        self.reservas = []
        self.pausar = False
        self.iniciar_gate = None
        self.retomar_gate = None
        self.retomar_erro = None
        self.retomar_resultado = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iniciar(self, nome, argumentos, *, traceparent=None):
        self.iniciados.append((nome, deepcopy(argumentos), traceparent))
        if self.iniciar_gate is not None:
            await self.iniciar_gate.wait()
        if argumentos["sala"] == "sala-delorean":
            return Completo(SimpleNamespace(), "2026-11-01", "Sala inexistente: sala-delorean")
        if self.pausar or argumentos["sala"] == "sala-garagem":
            pendente = Pendente(
                "Escolha uma sala alternativa",
                ("sala-fusca", "sala-mirante"),
                "2026-11-01",
                nome,
                deepcopy(argumentos),
                f"chave-{len(self.iniciados)}",
                f"token-{len(self.iniciados)}",
                traceparent,
            )
            self.pendentes.append(pendente)
            return pendente
        return self._completo(argumentos, argumentos["sala"])

    async def retomar(self, pendente, action, *, escolha=None, traceparent=None):
        self.retomados.append((pendente, action, escolha, traceparent))
        if self.retomar_erro is not None:
            raise self.retomar_erro
        if self.retomar_resultado is not None:
            return self.retomar_resultado
        if self.retomar_gate is not None:
            await self.retomar_gate.wait()
        if action == "decline":
            return Completo(SimpleNamespace(structured_content={"reservado": False, "motivo": "Escolha recusada"}), "2026-11-01")
        return self._completo(pendente._argumentos, escolha)

    def _completo(self, argumentos, sala):
        content = {"reservado": True, "reserva": f"res-{len(self.reservas) + 1:04d}", **argumentos, "sala": sala}
        self.reservas.append(content)
        return Completo(SimpleNamespace(structured_content=content), "2026-11-01")


def instalar_host(monkeypatch, host):
    class Host:
        def __init__(self, url):
            pass

        async def __aenter__(self):
            return host

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("agente.a2a_app.MCPHost", Host)
    return host


def test_card_and_v1_send_get(monkeypatch):
    host = instalar_host(monkeypatch, HostFalso())
    with TestClient(criar_app()) as client:
        card = client.get("/.well-known/agent-card.json")
        assert card.status_code == 200
        body = card.json()
        assert body["supportedInterfaces"] == [{"url": "http://localhost:7300/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}]
        assert body["defaultInputModes"] == body["defaultOutputModes"] == ["text/plain"]
        assert body["capabilities"]["streaming"] is body["capabilities"]["pushNotifications"] is False
        assert body["skills"][0]["id"] == "reservar-sala"
        response = send(client, "reservar sala=sala-fusca inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty")
        assert response["id"] == 1
        task = response["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert task["artifacts"][0]["artifactId"] and task["artifacts"][0]["name"] == "reserva"
        assert json.loads(task["artifacts"][0]["parts"][0]["text"])["politica"] == "2026-11-01"
        got = client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task["id"]}}).json()
        assert got["id"] == 2
        assert got["result"]["task"] == task
        assert "error" in send(client, "novamente", task["id"])
        assert len(host.iniciados) == 1


def test_concurrent_working_and_trace_isolation(monkeypatch):
    async def run():
        entered = []
        states = {}
        original_save = InMemoryTaskStore.save
        async def save(self, task, context):
            states.setdefault(task.id, []).append(task.status.state)
            await original_save(self, task, context)
        monkeypatch.setattr(InMemoryTaskStore, "save", save)
        release = asyncio.Event()
        class Host:
            def __init__(self, url): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def iniciar(self, name, args, *, traceparent=None):
                entered.append((args["responsavel"], traceparent))
                await release.wait()
                return Completo(SimpleNamespace(structured_content={"reservado": True, "reserva": "res-1", **args}), "resource-version")
        monkeypatch.setattr("agente.a2a_app.MCPHost", Host)
        app = criar_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            async def start(name, trace):
                text = f"reservar sala=sala-fusca inicio=i fim=f responsavel={name}"
                body = {"jsonrpc": "2.0", "id": name, "method": "SendMessage", "params": {"configuration": {"returnImmediately": True}, "message": {"messageId": name, "role": "ROLE_USER", "parts": [{"text": text}]}}}
                return (await client.post("/a2a", json=body, headers={"traceparent": trace})).json()["result"]["task"]
            traces = ["00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01", "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01"]
            first, second = await asyncio.gather(start("A", traces[0]), start("B", traces[1]))
            for _ in range(100):
                if len(entered) == 2: break
                await asyncio.sleep(.01)
            assert dict(entered) == {"A": traces[0], "B": traces[1]}
            assert first["id"] != second["id"] and first["contextId"] != second["contextId"]
            for task in (first, second):
                got = (await client.post("/a2a", json={"jsonrpc": "2.0", "id": 3, "method": "GetTask", "params": {"id": task["id"]}})).json()["result"]["task"]
                assert got["status"]["state"] == "TASK_STATE_WORKING"
                assert got["history"][0]["role"] == "ROLE_USER"
                assert states[task["id"]][:2] == [TaskState.TASK_STATE_SUBMITTED, TaskState.TASK_STATE_WORKING]
            release.set()
            await asyncio.sleep(.05)
    asyncio.run(run())


def test_error_and_pending_never_leak_state(monkeypatch):
    guard = AsyncMock(side_effect=AssertionError("callback não deve ser chamado"))
    monkeypatch.setattr("agente.mcp_host._guard_elicitation", guard)
    host = instalar_host(monkeypatch, HostFalso())
    with TestClient(criar_app()) as client:
        failed_response = send(client, "reservar sala=sala-delorean inicio=i fim=f responsavel=Marty")
        failed = failed_response["result"]["task"]
        assert failed["status"]["state"] == "TASK_STATE_FAILED"
        assert mensagem(failed) == "Sala inexistente: sala-delorean"
        assert any(m["parts"][0]["text"] == "Sala inexistente: sala-delorean" for m in failed["history"])
        assert not failed.get("artifacts")

        pending_response = send(client, PEDIDO)
        pending = pending_response["result"]["task"]
        assert pending["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(pending) == "alternativas: sala-fusca, sala-mirante"
        assert any(m["parts"][0]["text"] == "alternativas: sala-fusca, sala-mirante" for m in pending["history"])
        assert not pending.get("artifacts")
        token = host.pendentes[0]._token
        assert token not in json.dumps(pending_response)
        assert "requestState" not in json.dumps(pending_response)
        got = get_task(client, pending["id"])
        assert got["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(got) == "alternativas: sala-fusca, sala-mirante"
    guard.assert_not_awaited()
    assert host.retomados == []


def test_terminal_states_and_transport_failure(monkeypatch):
    calls = []
    class Host:
        def __init__(self, url): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def iniciar(self, name, args, *, traceparent=None):
            calls.append(args)
            raise RuntimeError("token-privado requestState")
    monkeypatch.setattr("agente.a2a_app.MCPHost", Host)
    store = InMemoryTaskStore()
    asyncio.run(store.save(Task(id="cancelada", context_id="ctx", status=TaskStatus(state=TaskState.TASK_STATE_CANCELED)), ServerCallContext()))
    monkeypatch.setattr("agente.a2a_app.InMemoryTaskStore", lambda: store)
    with TestClient(criar_app()) as client:
        text = "reservar sala=x inicio=i fim=f responsavel=Marty"
        failed_response = send(client, text)
        failed = failed_response["result"]["task"]
        assert failed["status"]["state"] == "TASK_STATE_FAILED"
        assert failed["status"]["message"]["parts"][0]["text"] == "Falha ao comunicar com o serviço de reservas"
        assert not failed.get("artifacts")
        assert "token-privado" not in json.dumps(failed_response)
        for task_id, state in [(failed["id"], "TASK_STATE_FAILED"), ("cancelada", "TASK_STATE_CANCELED")]:
            assert "error" in send(client, text, task_id)
            got = client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_id}}).json()["result"]["task"]
            assert got["status"]["state"] == state
        assert len(calls) == 1


def test_pause_invalid_choice_and_resume(monkeypatch):
    host = instalar_host(monkeypatch, HostFalso())
    with TestClient(criar_app()) as client:
        resposta = send(client, PEDIDO, traceparent=TRACE)
        task = resposta["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(task) == "alternativas: sala-fusca, sala-mirante"
        assert [m["parts"][0]["text"] for m in task["history"]] == [PEDIDO, "alternativas: sala-fusca, sala-mirante"]
        assert not task.get("artifacts")
        assert host.retomados == []
        assert get_task(client, task["id"]) == task

        invalida = send(client, "escolha=sala-aquario", task["id"])
        t2 = invalida["result"]["task"]
        assert t2["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(t2) == "alternativas: sala-fusca, sala-mirante"
        assert host.retomados == []

        concluida = send(client, "escolha=sala-fusca", task["id"], traceparent=TRACE)
        t3 = concluida["result"]["task"]
        assert t3["status"]["state"] == "TASK_STATE_COMPLETED"
        assert artifact(t3) == {**ARGS, "reserva": "res-0001", "sala": "sala-fusca", "politica": "2026-11-01"}
        assert len(host.retomados) == 1
        pendente, action, escolha, trace_retry = host.retomados[0]
        assert action == "accept" and escolha == "sala-fusca"
        assert pendente._nome == "reservar_sala"
        assert pendente._argumentos == ARGS
        assert pendente._chave == "chave-1"
        assert pendente._token == "token-1"
        assert trace_retry == TRACE
        assert "error" in send(client, "escolha=sala-mirante", task["id"])

        for corpo in (resposta, invalida, concluida):
            serializado = json.dumps(corpo)
            assert "token-1" not in serializado
            assert "requestState" not in serializado


def test_decline_cancels_without_artifact(monkeypatch):
    host = instalar_host(monkeypatch, HostFalso())
    with TestClient(criar_app()) as client:
        pausada = send(client, PEDIDO)["result"]["task"]
        resposta = send(client, "escolha=recusar", pausada["id"])
        cancelada = resposta["result"]["task"]
        assert cancelada["status"]["state"] == "TASK_STATE_CANCELED"
        assert not cancelada.get("artifacts")
        assert host.reservas == []
        pendente, action, escolha, _ = host.retomados[0]
        assert action == "decline" and escolha is None
        assert pendente._token == "token-1"
        assert "error" in send(client, "escolha=sala-fusca", pausada["id"])
        assert "requestState" not in json.dumps(resposta)


def test_retry_error_is_safe_failure(monkeypatch):
    host = HostFalso()
    # Simula token expirado/adulterado: o SDK rejeita o retry com -32602 e o
    # texto do protocolo pode carregar o estado privado; ele não pode vazar.
    host.retomar_erro = MCPError(-32602, "Invalid input response token-1 requestState chave-1")
    instalar_host(monkeypatch, host)
    with TestClient(criar_app()) as client:
        pausada = send(client, PEDIDO)["result"]["task"]
        resposta = send(client, "escolha=sala-fusca", pausada["id"])
        falha = resposta["result"]["task"]
        assert falha["status"]["state"] == "TASK_STATE_FAILED"
        assert mensagem(falha) == "Falha ao comunicar com o serviço de reservas"
        assert any(m["parts"][0]["text"] == "Falha ao comunicar com o serviço de reservas" for m in falha["history"])
        assert not falha.get("artifacts")
        assert "token-1" not in json.dumps(resposta)
        assert "requestState" not in json.dumps(resposta)
        assert "error" in send(client, "escolha=sala-mirante", pausada["id"])


def test_new_elicitation_replaces_only_same_task(monkeypatch):
    host = HostFalso()
    novo = Pendente(
        "Nova pergunta",
        ("sala-mirante",),
        "2026-11-01",
        "reservar_sala",
        dict(ARGS),
        "chave-nova",
        "token-novo",
        None,
    )
    host.retomar_resultado = novo
    instalar_host(monkeypatch, host)
    with TestClient(criar_app()) as client:
        pausada = send(client, PEDIDO)["result"]["task"]
        resposta = send(client, "escolha=sala-fusca", pausada["id"])
        nova = resposta["result"]["task"]
        assert nova["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert mensagem(nova) == "alternativas: sala-mirante"
        assert host.retomados[0][0]._token == "token-1"

        host.retomar_resultado = None
        concluida = send(client, "escolha=sala-mirante", pausada["id"])["result"]["task"]
        assert concluida["status"]["state"] == "TASK_STATE_COMPLETED"
        assert host.retomados[1][0]._token == "token-novo"
        assert host.retomados[1][0]._chave == "chave-nova"
        assert "token-novo" not in json.dumps(resposta)


def test_get_task_not_blocked_during_retry(monkeypatch):
    async def run():
        host = HostFalso()
        host.retomar_gate = asyncio.Event()
        instalar_host(monkeypatch, host)
        app = criar_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            pausada = (await send_async(client, PEDIDO))["result"]["task"]
            retomada = asyncio.create_task(send_async(client, "escolha=sala-fusca", pausada["id"]))
            for _ in range(100):
                if host.retomados:
                    break
                await asyncio.sleep(.01)
            assert host.retomados
            got = (await client.post("/a2a", json={"jsonrpc": "2.0", "id": 9, "method": "GetTask", "params": {"id": pausada["id"]}})).json()["result"]["task"]
            assert got["status"]["state"] == "TASK_STATE_WORKING"
            host.retomar_gate.set()
            concluida = (await retomada)["result"]["task"]
            assert concluida["status"]["state"] == "TASK_STATE_COMPLETED"
    asyncio.run(run())


def test_two_paused_tasks_reverse_order(monkeypatch):
    host = HostFalso()
    host.pausar = True
    instalar_host(monkeypatch, host)
    pedido_a = "reservar sala=sala-fusca inicio=2026-11-03T16:00:00-03:00 fim=2026-11-03T17:00:00-03:00 responsavel=Lorraine"
    pedido_b = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=George"
    with TestClient(criar_app()) as client:
        a = send(client, pedido_a, traceparent=TRACE)["result"]["task"]
        b = send(client, pedido_b, traceparent=TRACE2)["result"]["task"]
        assert a["status"]["state"] == b["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert a["id"] != b["id"]

        rb = send(client, "escolha=sala-mirante", b["id"])["result"]["task"]
        ra = send(client, "escolha=sala-mirante", a["id"])["result"]["task"]
        assert rb["status"]["state"] == ra["status"]["state"] == "TASK_STATE_COMPLETED"
        cb, ca = artifact(rb), artifact(ra)
        assert cb["sala"] == ca["sala"] == "sala-mirante"
        assert cb["responsavel"] == "George" and ca["responsavel"] == "Lorraine"
        assert cb["inicio"] == "2026-11-03T14:00:00-03:00" and ca["inicio"] == "2026-11-03T16:00:00-03:00"
        assert cb["reserva"] != ca["reserva"]
        assert [r[0]._token for r in host.retomados] == ["token-2", "token-1"]
        assert [r[0]._argumentos["responsavel"] for r in host.retomados] == ["George", "Lorraine"]
        assert [r[3] for r in host.retomados] == [TRACE2, TRACE]


def test_deterministic_pause_without_reservation(monkeypatch):
    host = instalar_host(monkeypatch, HostFalso())
    with TestClient(criar_app()) as client:
        a = send(client, PEDIDO)["result"]["task"]
        b = send(client, PEDIDO)["result"]["task"]
        assert a["id"] != b["id"]
        assert mensagem(a) == mensagem(b) == "alternativas: sala-fusca, sala-mirante"
        assert len(host.iniciados) == 2
        assert host.retomados == []
        assert host.reservas == []


def test_same_task_concurrent_continuations_no_double_completion(monkeypatch):
    async def run():
        host = HostFalso()
        host.retomar_gate = asyncio.Event()
        instalar_host(monkeypatch, host)
        app = criar_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            pausada = (await send_async(client, PEDIDO))["result"]["task"]
            primeira = asyncio.create_task(send_async(client, "escolha=sala-fusca", pausada["id"]))
            segunda = asyncio.create_task(send_async(client, "escolha=sala-fusca", pausada["id"]))
            for _ in range(100):
                if host.retomados:
                    break
                await asyncio.sleep(.01)
            await asyncio.sleep(.05)
            host.retomar_gate.set()
            resultados = await asyncio.gather(primeira, segunda)
            tarefas = [r.get("result", {}).get("task", {}) for r in resultados]
            assert all(t.get("id") == pausada["id"] for t in tarefas)
            # O SDK serializa as duas requisições; a segunda pode receber a Task
            # já concluída pela primeira. O que não pode é haver dupla retomada.
            assert any(t.get("status", {}).get("state") == "TASK_STATE_COMPLETED" for t in tarefas)
            assert len(host.retomados) == 1
            assert len(host.reservas) == 1
    asyncio.run(run())


def test_separate_processes(tmp_path):
    def port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]
    mcp_port, a2a_port = port(), port()
    mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"
    a2a_url = f"http://127.0.0.1:{a2a_port}/a2a"
    with ServiceProcess([sys.executable, str(ROOT / "servidor-mcp/main.py")], cwd=tmp_path, log_dir=tmp_path, name="mcp-a2a", listen_address=("127.0.0.1", mcp_port), env={"MCP_PORT": str(mcp_port)}) as mcp:
        mcp.wait_ready(f"http://127.0.0.1:{mcp_port}/", status=404)
        with ServiceProcess([sys.executable, "-m", "agente.main"], cwd=tmp_path, log_dir=tmp_path, name="a2a", listen_address=("127.0.0.1", a2a_port), env={"PYTHONPATH": str(ROOT), "MCP_URL": mcp_url, "A2A_PORT": str(a2a_port), "A2A_URL": a2a_url}) as agent:
            agent.wait_ready(f"http://127.0.0.1:{a2a_port}/.well-known/agent-card.json")
            with httpx.Client(base_url=f"http://127.0.0.1:{a2a_port}") as client:
                assert client.get("/.well-known/agent-card.json").json()["supportedInterfaces"][0]["url"] == a2a_url

                livre = "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
                task = send(client, livre)["result"]["task"]
                assert task["status"]["state"] == "TASK_STATE_COMPLETED"
                assert artifact(task)["politica"] == "2026-11-01"
                assert get_task(client, task["id"]) == task
                assert "error" in send(client, livre, task["id"])

                failed = send(client, "reservar sala=sala-delorean inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc")["result"]["task"]
                assert failed["status"]["state"] == "TASK_STATE_FAILED"
                assert mensagem(failed) == "Sala inexistente: sala-delorean"

                pending = send(client, PEDIDO)
                pausada = pending["result"]["task"]
                assert pausada["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
                assert mensagem(pausada) == "alternativas: sala-fusca, sala-mirante"
                assert not pausada.get("artifacts")
                assert "requestState" not in json.dumps(pending)

                invalida = send(client, "escolha=sala-aquario", pausada["id"])
                assert invalida["result"]["task"]["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
                assert mensagem(invalida["result"]["task"]) == "alternativas: sala-fusca, sala-mirante"

                concluida = send(client, "escolha=sala-fusca", pausada["id"], traceparent=TRACE)["result"]["task"]
                assert concluida["status"]["state"] == "TASK_STATE_COMPLETED"
                assert artifact(concluida)["sala"] == "sala-fusca"
                assert "error" in send(client, "escolha=sala-mirante", pausada["id"])

                recusavel = send(client, "reservar sala=sala-garagem inicio=2026-11-03T14:30:00-03:00 fim=2026-11-03T15:30:00-03:00 responsavel=Biff")["result"]["task"]
                assert recusavel["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
                cancelada = send(client, "escolha=recusar", recusavel["id"])["result"]["task"]
                assert cancelada["status"]["state"] == "TASK_STATE_CANCELED"
                assert not cancelada.get("artifacts")

                traces = [TRACE, TRACE2]
                def traced(index):
                    body = {"jsonrpc": "2.0", "id": index, "method": "SendMessage", "params": {"message": {"messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": "reservar sala=sala-delorean inicio=i fim=f responsavel=Doc"}]}}}
                    return client.post("/a2a", json=body, headers={"traceparent": traces[index]}).json()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    assert all(response["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED" for response in pool.map(traced, range(2)))
                logs = [json.loads(line) for line in mcp.stderr_path.read_text().splitlines() if line.startswith('{"method"')]
                assert {row["traceparent"] for row in logs if row["method"] == "tools/call"} >= set(traces)
                mcp.close()
                unavailable = send(client, PEDIDO)["result"]["task"]
                assert unavailable["status"]["state"] == "TASK_STATE_FAILED"
                assert mensagem(unavailable) == "Falha ao comunicar com o serviço de reservas"
                assert not unavailable.get("artifacts")
