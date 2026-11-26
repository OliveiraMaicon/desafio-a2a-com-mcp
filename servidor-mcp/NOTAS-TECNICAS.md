# Transporte MCP: notas técnicas

## Gate de compatibilidade (2026-11-26)

Distribuição oficial conferida no PyPI: `mcp==2.3.0` (wheel
`mcp-2.3.0-py3-none-any.whl`), com `mcp-types==2.3.0`.
Fontes consultadas: https://pypi.org/pypi/mcp/json e documentação v2 via
Context7, https://py.sdk.modelcontextprotocol.io/v2/run e
https://py.sdk.modelcontextprotocol.io/v2/handlers/multi-round-trip.

Imports e assinaturas inspecionados em ambiente virtual novo, Python 3.14.0:

- `from mcp.server import MCPServer`.
- `MCPServer.streamable_http_app(streamable_http_path='/mcp',
  json_response=True, stateless_http=True)` produz a aplicação Starlette.
- `from mcp.types import LATEST_PROTOCOL_VERSION, InputRequiredResult`:
  a constante instalada é `2026-07-28`; o resultado possui `input_requests`,
  `request_state` e `result_type='input_required'` (aliases wire em camelCase).
- `from mcp.server.mcpserver import Resolve, Elicit, Context`:
  `Resolve(fn)`, `Elicit(message, schema)` e `Context.input_responses` /
  `Context.request_state` existem. Tools de alto nível usam dependências
  `Resolve`; `MCPServer.input_required` **não** existe nesta versão.
- `from mcp.server.lowlevel import Server`: `on_call_tool=` é parâmetro do
  construtor, não método decorador; permite `CallToolResult | InputRequiredResult`.
- `from mcp.server.mcpserver import RequestStateSecurity, AESGCMRequestStateCodec`:
  `RequestStateSecurity(keys=[key], ttl=600.0)` usa AES-256-GCM; a fronteira
  verifica expiração, request, audience e principal. Chaves devem ter pelo
  menos 32 bytes. A configuração padrão é efêmera e NÃO serve ao requisito
  futuro de sobrevivência a restart; a próxima change de MRTR configurará a
  chave de ambiente compartilhada. Nenhum protocolo ou criptografia próprios.

Probe HTTP com o SDK puro e `starlette.testclient.TestClient`, sem initialize:

```text
wire01 200 {"jsonrpc":"2.0","id":1,"result":{"resultType":"complete",...}}
missing-meta 400 {"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"params._meta is missing the required envelope key(s): io.modelcontextprotocol/clientCapabilities"}}
```

O SDK já valida o envelope moderno e escolhe o status HTTP correto. Não é
necessário um dispatcher paralelo ou adaptação manual de envelopes/status.
O probe usou apenas uma tool de diagnóstico em memória, sem alterar o starter.

## Ambiente reproduzível

Python mínimo da aplicação: **3.11**, embora o SDK isolado declare 3.10.
Starlette 1.10.0, HTTPX2 2.16.2 e outras dependências resolvidas exigem 3.11.
`pyproject.toml` fixa dependências diretas; `requirements.lock` fixa também
transitivas e backend de build, sem depender de gerenciador global.

Na raiz de um clone limpo:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e '.[test]'
.venv/bin/python -m pip check
.venv/bin/python -m pytest
```

A instalação é editável: os dados continuam nos caminhos do starter, sem
copiar nem incluir `dados/` no pacote. O validador continua independente,
compatível com Python 3.10+ e sem dependências externas.

Ambiente `.venv` criado do zero; lock instalado; instalação editável com os
comandos acima concluída; `pip check`: `No broken requirements found.`
Imports de MCP, MRTR, segurança, Pydantic, Starlette, Uvicorn, HTTPX,
JSON Schema e Pytest conferidos, sem depender dos pacotes globais.

## Processo e caminhos

Antes de iniciar, gere uma chave aleatória e mantenha o mesmo valor entre
reinícios (proteja-o como segredo e não o inclua no repositório):

```bash
export REQUEST_STATE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

Para retomar após reiniciar o terminal, recupere a mesma chave de um gerenciador
de segredos; gerar outra invalida os tokens pendentes.

```bash
.venv/bin/python servidor-mcp/main.py
```

Padrões: `MCP_HOST=127.0.0.1`, `MCP_PORT=7301`, endpoint `/mcp`.
Também é possível chamar o caminho absoluto do script a partir de outro cwd.
`central_salas.paths` resolve `dados/` a partir de `__file__`, não do terminal.
`create_server()` monta o catálogo; `create_app()` delega o transporte ao SDK.

Cada POST em `/mcp` registra no stderr uma linha JSON com `method`, `id` e
`traceparent` (ou `null` quando não disponíveis). O corpo completo, argumentos
e requestState não são registrados. A observação ocorre antes do guard e o
corpo original é reproduzido para o transporte, inclusive em rejeições.

## Bloqueio: header legado contorna a validação moderna

**Implementação pausada no gate 2.3.** Nenhum fallback próprio foi criado e o
teste que falha foi mantido em `tests/test_mcp_transport.py`, caso
`test_header_mismatch_does_not_execute_operation[version-header]`.

Reprodução na distribuição oficial `mcp==2.3.0`:

1. Registrar uma tool `sentinela` que anota sua execução.
2. Enviar `tools/call` com os metadados modernos completos; a versão em
   `params._meta` é `2026-07-28`.
3. Enviar `MCP-Protocol-Version: 2025-11-25`; os headers de método/nome estão
   corretos. A divergência deveria ser recusada com `-32020`, sem executar.

Resultado observado:

```text
body protocol: 2026-07-28
header protocol: 2025-11-25
HTTP: 200
response: {"jsonrpc":"2.0","id":1,"result":{"content":[{"text":"executada","type":"text"}],"isError":false,"structuredContent":{"result":"executada"}}}
calls: ['executada']
```

Evidência na própria distribuição, `mcp/server/streamable_http_manager.py`,
linhas 187–202: o comentário diz `header-only era-routing for now;
body-primary classification is a follow-up`. `handle_modern_request` só é
chamado quando o header não pertence a `HANDSHAKE_PROTOCOL_VERSIONS`; um
header legado entra em `_handle_stateless_request`, apesar do corpo moderno.
Não há parâmetro público de seleção exclusiva da revisão moderna na
assinatura de `MCPServer.streamable_http_app()` desta distribuição.

O sentido inverso (header moderno e versão legada no corpo), divergência de
método, nome de tool e URI são rejeitados corretamente pelo SDK.

Última execução do gate incremental:

```text
.venv/bin/python -m pytest tests/test_mcp_transport.py -q
1 failed, 10 passed in 1.23s
```

Concluídos e assinalados: 1.1, 1.2, 2.1 e 2.2 (**4/12**). O processo sobe
na porta padrão a partir de outro cwd, mas 1.3 permanece aberto até provar
o carregamento dos dados no próprio processo. Catálogo de salas, resource,
log de aplicação e demais gates não foram implementados após o bloqueio.
As tools `consultar_disponibilidade` e `reservar_sala` continuam pertencendo
à próxima change, não a uma redução silenciosa do escopo desta.

Para retomar: resolver a incompatibilidade na distribuição oficial e repetir
o gate, sem remover o teste nem reproduzir manualmente o dispatcher. Esta
limitação também precisa constar na seção de decisões técnicas do README
final, cuja integração pertence ao coordenador da entrega.

## Adaptação da fronteira HTTP

O SDK `mcp==2.3.0` continua responsável pelo transporte, dispatcher e validação
MCP. `ProtocolVersionGuard`, instalado na aplicação ASGI, verifica somente o
caso em que um header legado ou ausente faria o SDK escolher o transporte
legado apesar de o corpo declarar a revisão moderna. Nesse caso responde
`-32020` antes de executar a tool. Nos demais casos, o request é encaminhado
ao SDK, com os fragmentos do corpo preservados.

O teste original de divergência continua ativo. Testes adicionais cobrem os
headers legados suportados, ausência de header, id numérico e textual, JSON
inválido, requisições simultâneas e recepção fragmentada. Essa adaptação não
constitui um dispatcher MCP substituto; a limitação original do SDK e a
justificativa da proteção permanecem documentadas acima.

## Gate incremental concluído

O registro de bloqueio anterior é histórico: após aprovação do guard HTTP, os
testes de transporte passaram. A suíte completa executada nesta etapa produziu
`68 passed, 125 subtests passed`; o teste de processo envia os exemplos wire 01
e 05 por HTTP na porta padrão, inclusive com cwd externo ao projeto. `dados/`,
`exemplos/` e `validador/` permanecem sem alterações no Git.

Nesta etapa o catálogo expõe `listar_salas` e o resource de política. As tools
`consultar_disponibilidade` e `reservar_sala` pertencem à próxima change,
`implement-room-tools`; o validador integral ainda não é gate desta etapa.

## Tools de salas: etapa intermediária

Cada servidor carrega cópias das salas e reservas iniciais em memória. Novas
reservas são visíveis no mesmo processo, mas um restart as perde; `dados/` é
somente leitura. Em conflito, a reserva retorna erro de execução sem criar
reserva nem consumir id. Esse resultado é provisório, não a negociação completa:
o cálculo de alternativas está isolado no domínio e a emissão de elicitation
pertence à change de MRTR. Não há persistência ou controle de escrita concorrente.

## Gate do SDK para MRTR seguro

A suíte anterior passou com `78 passed, 125 subtests passed`. Na distribuição
fixada `mcp==2.3.0`, `MCPServer(..., request_state_security=...)` instala
`RequestStateBoundary`; `RequestStateSecurity(keys=[...], ttl=900.0)` configura
chave e validade, com o nome do servidor como audiência padrão. A fronteira
verifica antes do handler método, nome da operação, digest dos argumentos,
audiência e expiração. `Resolve` e `Elicit` retornam perguntas no protocolo
moderno; o resolver vincula a resposta ao digest da pergunta. A validação de
capability do SDK também aceita `elicitation: {}` como form legado, portanto a
exigência moderna mais estrita desta change precisa ser verificada na aplicação.

### Limitação encontrada no resolver nativo

Na distribuição fixada, `mcp/server/request_state.py`, `_request_identity`
(linhas 271–282), calcula apenas um digest dos argumentos; `_seal` (linhas
424–449) guarda esse digest e o estado interno, não os argumentos. Em
`mcp/server/mcpserver/resolve.py`, `_State` e `_encode_state` (linhas 754–788)
guardam resultados e digests de perguntas, não os argumentos nem as alternativas
originais. Além disso, `_fulfil` (linhas 604–613) volta a perguntar quando a
resposta não usa a chave esperada, em vez de retornar `-32602`.

Assim, o resolver nativo sozinho não satisfaz literalmente a exigência de
transportar argumentos e alternativas no estado protegido nem a rejeição da
chave incorreta. O SDK também permite construir `InputRequiredResult` manualmente
e aplicar sua proteção nativa; avaliar essa alternativa exige decisão explícita
sobre a adaptação do desenho, sem implementar criptografia própria. A change
permanece pausada antes da implementação da negociação.
