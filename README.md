# A Ponte: um agente A2A com MCP por dentro

Entrega do desafio da Central de Salas. São dois processos Python separados:

- **servidor MCP** em Streamable HTTP na porta `7301`, no caminho `/mcp`;
- **agente A2A** na porta `7300`, com Agent Card em `/.well-known/agent-card.json`
  e JSON-RPC em `/a2a`.

O agente descobre e chama as tools do servidor MCP por HTTP, como um host MCP
independente. Não há LLM, banco nem sessão de protocolo: o estado da reserva
viaja no `requestState` do MRTR e o estado público viaja na Task do A2A.

## Como rodar

### Pré-requisitos

- Python 3.11 ou superior. A execução documentada abaixo foi verificada com
  **CPython 3.14.0**.
- Git.
- As duas portas livres: `7300` (agente) e `7301` (servidor MCP).

### Instalação a partir de um clone limpo

```bash
git clone https://github.com/OliveiraMaicon/desafio-a2a-com-mcp.git
cd desafio-a2a-com-mcp

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.lock
```

O `requirements.lock` fixa as versões de runtime, testes e build. As dependências
diretas também estão travadas no `pyproject.toml`.

### Terminal 1: servidor MCP

Gere a chave de integridade do `requestState` e exporte-a **somente** neste
terminal. O valor abaixo é gerado na hora e nunca deve ser commitado:

```bash
export REQUEST_STATE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
.venv/bin/python servidor-mcp/main.py
```

O processo recusa iniciar se a variável estiver ausente, não for hexadecimal ou
tiver menos de 32 bytes decodificados. O stderr registra cada request com
método, id e `traceparent`.

### Terminal 2: agente A2A

```bash
.venv/bin/python -m agente.main
```

O agente usa `MCP_URL` (padrão `http://localhost:7301/mcp`), `A2A_URL` (padrão
`http://localhost:7300/a2a`) e `A2A_PORT` (padrão `7300`).

### Conferir o Agent Card

```bash
curl -s http://localhost:7300/.well-known/agent-card.json | python3 -m json.tool
```

### Rodar o validador

Com **os dois processos recém-iniciados**, em um terceiro terminal:

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

O validador cria reservas durante a execução. Reinicie os dois processos antes
de cada nova execução; rodar duas vezes seguidas no mesmo processo produz
resultados falsos por causa do estado já alterado.

### Reiniciar o servidor MCP entre a pausa e o retry

O `requestState` continua válido depois de reiniciar o servidor MCP, desde que o
novo processo use **a mesma `REQUEST_STATE_SECRET` e a mesma identidade do
servidor**. Exporte novamente o mesmo valor no Terminal 1 e suba o processo; o
cliente pode reenviar o retry sem repetir a chamada inicial. Reservas novas
continuam em memória e são perdidas no restart, conforme o contrato.

### Testes automatizados

```bash
.venv/bin/python -m pytest -q
python3 -m unittest discover -s tests -p test_process_harness.py -v
```

O harness de `tests/process_harness.py` cria processos isolados, espera a
prontidão por HTTP e encerra apenas os PIDs que ele próprio iniciou. O autoteste
cobre duas execuções consecutivas independentes, falha de startup, timeout e
encerramento seletivo.

## Onde a ponte acontece

O ponto de pausa está em `agente/a2a_app.py`, em `ReservasExecutor._pausar`:
quando `agente/mcp_host.py` devolve um `Pendente` (o `InputRequiredResult` cru do
MCP), o executor guarda a continuação privada em
`agente/continuacoes.py:Continuacoes.guardar`, associada ao `taskId`, e chama
`TaskUpdater.requires_input` com a linha exata
`alternativas: <ids na ordem do enum>`. A Task passa a
`TASK_STATE_INPUT_REQUIRED`; nenhum callback de elicitation é executado.

O ponto de retomada está em `ReservasExecutor._continuar`. A segunda mensagem da
mesma Task é interpretada por `interpretar_escolha` e entregue a
`agente/mcp_host.py:MCPHost.retomar`, que repete o `tools/call` com um **id
JSON-RPC novo**, os mesmos argumentos originais, a mesma chave de pergunta e o
`requestState` ecoado sem interpretação. No servidor, `reservar_sala` em
`servidor-mcp/central_salas/server.py` recebe o estado já verificado pelo SDK,
confere os argumentos selados e a alternativa escolhida e só então cria a
reserva. O token nunca é anexado à Task, ao card, ao artifact ou a uma resposta
A2A.

## Decisões técnicas

### Proteção e validade do `requestState`

O servidor configura `RequestStateSecurity(keys=[...], ttl=900.0)` em
`servidor-mcp/central_salas/server.py`. O SDK oficial sela o conteúdo com
integridade (HMAC/AEAD) e verifica o token antes de entregá-lo de volta à tool.
O TTL é de **15 minutos** (900 segundos), dentro da faixa de 5 a 30 minutos do
enunciado.

A chave vem exclusivamente de `REQUEST_STATE_SECRET`, com pelo menos 32 bytes
hexadecimais; não há segredo no código. Um token adulterado, expirado, de outra
operação ou com chave de pergunta incorreta é rejeitado com `-32602`. No retry,
os argumentos reenviados são comparados com os valores selados; qualquer
divergência também resulta em `-32602`, sem efeito colateral.

O conteúdo do estado é legível, mas não adulterável: o agente o trata como
opaco — apenas guarda e ecoa. O restart do MCP funciona porque o estado viaja
no token e não em memória do processo; a mesma chave e a mesma identidade do
servidor precisam ser preservadas.

### Estado das Tasks e do agente

As Tasks públicas ficam no `InMemoryTaskStore` do SDK A2A. As continuações
privadas ficam em `agente/continuacoes.py:Continuacoes`, em memória, indexadas
por `taskId`, com trava por Task. Uma entrada é removida na conclusão, recusa,
falha ou substituição por nova pausa da mesma Task; encerrar uma Task não afeta
as demais. Tasks e continuações são perdidas ao reiniciar o agente — apenas o
`requestState` do MCP sobrevive ao restart do servidor MCP.

### Descoberta, capabilities e trace

Antes do primeiro `tools/call`, o host faz `tools/list` e lê o resource
`politica://uso`, extraindo a versão da primeira linha. Todo request MCP leva os
campos obrigatórios de `_meta`, a capability `{"elicitation": {"form": {}}}` e
os headers espelhados (`MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name`). O
`traceparent` recebido no header A2A é propagado no `_meta` de todos os requests
daquela Task; o span-id pode mudar, o trace-id não.

### Compatibilidade com o SDK A2A

`a2a-sdk==1.3.1` interpreta a ausência do header `A2A-Version` como `0.3`,
enquanto o contrato do desafio usa v1.0 e omite esse header nos exemplos. O
middleware `VersaoV1Padrao`, em `agente/a2a_app.py`, preenche `A2A-Version: 1.0`
somente para `/a2a` quando o header não veio. O comportamento do SDK está
documentado, não escondido.

### Limitação real do SDK MCP e proteção de fronteira

`mcp==2.3.0` roteia pelo header `MCP-Protocol-Version` antes de validar o corpo.
A evidência está em `mcp/server/streamable_http_manager.py:187–202`, no
comentário `header-only era-routing for now; body-primary classification is a
follow-up`: um header legado faz o SDK escolher o caminho legado mesmo quando o
corpo declara `2026-07-28`, executando a tool em vez de recusar a divergência.
O SDK não oferece opção pública para desativar esse roteamento.

Para cumprir o contrato sem reescrever o protocolo, o middleware ASGI
`ProtocolVersionGuard` (`servidor-mcp/central_salas/version_guard.py`) verifica
apenas esse caso na fronteira HTTP e responde `-32020` antes de a tool executar.
Nos demais casos o request é entregue intacto ao SDK, que continua responsável
pelo transporte, dispatcher, schemas, MRTR e serialização. O teste de regressão
e as evidências completas estão em `servidor-mcp/NOTAS-TECNICAS.md`.

### Escopo deliberadamente pequeno

Não há banco, ORM, LLM, autenticação, streaming, push notification, interface
gráfica nem persistência em disco das reservas. O agente traduz protocolo; as
regras de sala (conflito, política e alternativas) ficam no servidor MCP.

## Saída do validador

Comando executado com os dois processos recém-iniciados, em CPython 3.14.0:

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

Código de saída: **0**.

```text
trace-id desta execucao: 161ee0909c5093b201e5072bb0ce8ece
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```

O mesmo trace-id aparece no stderr do servidor MCP, junto do `tools/list`
anterior ao primeiro `tools/call` do agente e dos ids distintos entre chamada
inicial e retry. As verificações que o validador não cobre — restart do MCP,
expiração, isolamento entre duas Tasks, varredura de tokens e inspeção de logs —
estão cobertas pela suíte em `tests/`.
