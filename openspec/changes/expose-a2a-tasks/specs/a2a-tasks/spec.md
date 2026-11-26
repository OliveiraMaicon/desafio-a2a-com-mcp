# Spec Delta

## Purpose

Expor a reserva como capacidade A2A v1.0 descobrível, com entrada determinística e Tasks consultáveis que representam identidade, histórico e produto sem revelar a implementação MCP.

## ADDED Requirements

### Requirement: Descoberta A2A v1.0
GET `/.well-known/agent-card.json` SHALL responder HTTP 200 com Agent Card v1.0 válido. O card SHALL declarar supportedInterfaces contendo interface JSONRPC com protocolVersion 1.0 e URL do endpoint `/a2a` na porta padrão 7300, além da skill reservar-sala e modos text/plain. Streaming e push notifications SHALL permanecer desabilitados.

#### Scenario: Card compatível com o cliente do desafio
- **WHEN** um cliente consulta a URI well-known
- **THEN** recebe identidade, capabilities, supportedInterfaces e skill com os nomes de campos da v1.0
- **AND** a URL anunciada corresponde ao endpoint efetivamente servido

### Requirement: Binding JSON-RPC externo
O endpoint `/a2a` SHALL aceitar SendMessage e GetTask em JSON-RPC 2.0 conforme A2A v1.0, incluindo as formas de Message, Task, Artifact, roles e estados exemplificadas no starter. A resposta SHALL preservar o id JSON-RPC da chamada correspondente.

#### Scenario: Métodos públicos acessíveis
- **WHEN** um cliente envia SendMessage ou GetTask com envelope válido
- **THEN** recebe a resposta v1.0 do método com o id JSON-RPC correspondente

### Requirement: Entrada fixa e determinística
Um pedido de reserva SHALL ser interpretado no formato `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>`, sem inferência por LLM. O agente SHALL delegar validade de sala, política, conflitos e alternativas ao MCP, sem rejeitar localmente ids de sala por catálogo próprio.

#### Scenario: Sala desconhecida chega à tool
- **WHEN** o texto bem formado pede sala-delorean
- **THEN** o agente encaminha os argumentos ao MCP para obter sua decisão e mensagem de erro

### Requirement: Identidade e estados da Task
SendMessage sem taskId SHALL criar uma Task com id e contextId próprios e histórico da mensagem recebida. Ela SHALL transitar por TASK_STATE_SUBMITTED e TASK_STATE_WORKING antes de sucesso ou falha. GetTask SHALL refletir o estado corrente, inclusive durante processamento, sem aguardar sua conclusão.

#### Scenario: Task em processamento consultável
- **WHEN** uma chamada MCP está pendente e GetTask consulta a Task já criada
- **THEN** GetTask devolve sua identidade e estado corrente sem bloquear até a tool terminar

### Requirement: Reserva livre concluída com artifact
Uma reserva MCP bem-sucedida SHALL terminar a Task em TASK_STATE_COMPLETED com artifact de name reserva. O artifact SHALL ter identidade própria e conter texto JSON com reserva, sala, inicio, fim, responsavel e politica. A versão politica SHALL ser obtida da leitura do resource pelo host.

#### Scenario: Sucesso de ponta a ponta
- **WHEN** o cliente pede uma sala livre com intervalo válido
- **THEN** SendMessage devolve Task COMPLETED e artifact com a reserva efetivamente criada e politica 2026-11-01
- **AND** GetTask posterior devolve a mesma identidade, estado e artifact

### Requirement: Erros MCP visíveis como falha
Um resultado de execução MCP com isError verdadeiro SHALL terminar a Task em TASK_STATE_FAILED. O texto exato da tool SHALL aparecer na mensagem de status e no histórico, sem artifact de reserva bem-sucedida. Erros de protocolo ou transporte SHALL produzir falha observável sem expor dados privados de continuação.

#### Scenario: Sala inexistente
- **WHEN** o MCP devolve `Sala inexistente: sala-delorean`
- **THEN** a Task termina FAILED com essa mensagem visível no status e histórico

### Requirement: Estados terminais definitivos
Tasks COMPLETED, CANCELED ou FAILED não SHALL voltar a WORKING. SendMessage referenciando qualquer Task terminal SHALL ser recusado com erro A2A/JSON-RPC, sem nova chamada de reserva ao MCP.

#### Scenario: Continuação após conclusão
- **WHEN** um cliente envia nova mensagem referenciando uma Task COMPLETED
- **THEN** recebe erro e a Task mantém seu estado e artifact anteriores

### Requirement: Consulta sem dados privados
GetTask SHALL devolver id, contextId, status, histórico e artifacts existentes, sem estado interno do host. Card, mensagens, artifacts, erros e respostas públicas não SHALL conter requestState ou sua cópia serializada.

#### Scenario: Representação pública restrita
- **WHEN** o cliente consulta uma Task ou recebe erro relacionado a ela
- **THEN** a resposta contém apenas informações públicas e não o estado opaco MCP

### Requirement: Propagação do contexto A2A
O traceparent recebido no header de SendMessage SHALL ser passado ao host MCP na operação da Task, preservando o trace-id. Um request concorrente não SHALL sobrescrever o contexto de outra Task.

#### Scenario: Trace atravessa a fronteira
- **WHEN** SendMessage chega com traceparent conhecido
- **THEN** os requests MCP daquela operação registram o mesmo trace-id no servidor
