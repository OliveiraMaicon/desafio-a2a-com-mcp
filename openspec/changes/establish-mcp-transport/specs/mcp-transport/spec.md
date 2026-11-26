# Spec Delta

## Purpose

Disponibilizar uma fronteira MCP HTTP verificável para descoberta de ferramentas, leitura da política e observação dos requests, sem depender de sessão entre chamadas.

## ADDED Requirements

### Requirement: Endpoint MCP stateless
O servidor SHALL atender Streamable HTTP em `/mcp`, na porta padrão 7301, usando a revisão `2026-07-28`. Cada request SHALL ser validado por seus próprios metadados, sem inferir versão ou capabilities de conexão ou chamada anterior. Resultados bem-sucedidos de descoberta, listagem de salas e leitura de resource SHALL declarar `resultType: complete`; a pausa de reserva é definida separadamente em `room-reservation-mrtr`.

#### Scenario: Descoberta sem handshake anterior
- **WHEN** um cliente envia `tools/list` com metadados e headers válidos diretamente a `/mcp`
- **THEN** o servidor responde HTTP 200 com um resultado completo, sem exigir sessão previamente inicializada

### Requirement: Metadados obrigatórios por request
Requests SHALL conter `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities` em `params._meta`. A ausência de qualquer campo SHALL produzir erro JSON-RPC `-32602` com HTTP 400, preservando o id do request quando disponível.

#### Scenario: Versão ausente
- **WHEN** um request omite a versão em `_meta`, mesmo contendo o header de versão
- **THEN** o servidor responde `-32602` com HTTP 400

#### Scenario: Capabilities ausentes após request válido
- **WHEN** o cliente envia um request válido e depois outro sem clientCapabilities
- **THEN** o segundo é rejeitado com `-32602` e HTTP 400, sem herdar capabilities do primeiro

### Requirement: Headers coerentes com o corpo
O transporte SHALL conferir `MCP-Protocol-Version` e `Mcp-Method` contra o corpo e `Mcp-Name` contra o nome de tool ou URI em `tools/call` e `resources/read`. Divergências SHALL ser recusadas com erro JSON-RPC `-32020`, sem executar a operação.

#### Scenario: Nome espelhado divergente
- **WHEN** `Mcp-Name` indica outra tool ou URI que não a declarada em `params`
- **THEN** o servidor responde `-32020` e não executa a operação

### Requirement: Descoberta e listagem de salas
O servidor SHALL declarar capabilities de tools e resources. `tools/list` SHALL incluir `listar_salas` com `inputSchema` de objeto e `outputSchema` para um objeto com a lista `salas`. A chamada sem argumentos SHALL devolver todas as salas de `dados/salas.json` em `structuredContent` e o mesmo JSON em bloco de texto.

#### Scenario: Listagem compatível com o schema
- **WHEN** o cliente descobre e chama `listar_salas` com `arguments: {}`
- **THEN** recebe as cinco salas do starter, com id, nome, capacidade e recursos
- **AND** o conteúdo estruturado satisfaz o outputSchema e é igual ao JSON desserializado do bloco de texto

### Requirement: Leitura da política
`resources/read` de `politica://uso` SHALL devolver o texto integral de `dados/politica-de-uso.md`, a URI e `mimeType: text/markdown`. A leitura SHALL preservar a primeira linha que declara a versão.

#### Scenario: Política disponibilizada sem transformação
- **WHEN** o cliente lê `politica://uso`
- **THEN** o conteúdo devolvido corresponde ao arquivo original, incluindo `versao: 2026-11-01`

### Requirement: Rejeição de operações desconhecidas
Uma URI de resource inexistente SHALL produzir `-32602`, nunca sucesso com contents vazio. Uma tool inexistente SHALL ser recusada com `-32602` ou resultado `isError: true`, sem mutação de dados.

#### Scenario: Resource inexistente
- **WHEN** o cliente lê `politica://inexistente`
- **THEN** recebe erro JSON-RPC `-32602`

#### Scenario: Tool inexistente
- **WHEN** o cliente chama `voar_delorean`
- **THEN** recebe uma das formas de rejeição permitidas, sem sucesso aparente

### Requirement: Log de requests em stderr
Cada request recebido, inclusive os rejeitados, SHALL gerar registro em stderr com método, id e traceparent recebido em `_meta`, quando presente. O log SHALL evitar despejar corpos completos, segredos ou requestState.

#### Scenario: Contexto de trace preservado no log
- **WHEN** chega um request com traceparent e id conhecidos
- **THEN** seu registro em stderr contém método, id e o traceparent exato recebido

#### Scenario: Request inválido observável
- **WHEN** um request com id e método identificáveis é rejeitado por metadados ausentes
- **THEN** a tentativa também aparece no stderr com esses identificadores
