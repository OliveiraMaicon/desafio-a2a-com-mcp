# Spec Delta

## Purpose

Conectar a pausa MRTR do servidor MCP à continuidade de uma Task A2A, devolvendo a decisão ao usuário e preservando isolamento e privacidade do estado necessário à retomada.

## ADDED Requirements

### Requirement: Pausa pública sem chamada aberta
Ao receber input_required do MCP, o agente SHALL colocar a Task em TASK_STATE_INPUT_REQUIRED e encerrar o SendMessage com a Task pausada. A mensagem de status e histórico SHALL conter exatamente `alternativas: <ids separados por virgula e espaco>`, sem prefixo, saudação ou quebra de linha, na ordem recebida no enum; const SHALL ser tratado como lista de um elemento.

#### Scenario: Conflito inicial
- **WHEN** uma Task pede sala-garagem em 03/11/2026 das 14:00 às 15:00 em UTC-03:00 com dados iniciais
- **THEN** recebe INPUT_REQUIRED com texto exato `alternativas: sala-fusca, sala-mirante`
- **AND** GetTask mostra a mesma pausa sem manter o request original aberto

### Requirement: Continuação privada isolada por Task
Cada Task pausada SHALL ter sua própria associação com pedido original, chave da pergunta, alternativas, requestState opaco e contexto de trace. Essa associação não SHALL ser incluída em nenhuma serialização pública A2A. O agente não SHALL interpretar o conteúdo do requestState.

#### Scenario: Tokens fora de todas as respostas
- **WHEN** o cliente recebe SendMessage, GetTask, card, artifacts ou erro de uma Task pausada ou retomada
- **THEN** nenhuma dessas respostas contém a chave requestState, o token integral ou sua cópia serializada

### Requirement: Escolha inválida preserva a pausa
Uma continuação `escolha=<id>` fora das alternativas recebidas SHALL manter a Task em INPUT_REQUIRED e repetir o mesmo texto de alternativas. Não SHALL consumir o estado pendente nem enviar retry MCP.

#### Scenario: Sala fora do schema
- **WHEN** o cliente escolhe sala-aquario para uma pausa que oferece sala-fusca e sala-mirante
- **THEN** a Task permanece INPUT_REQUIRED com a mesma mensagem e ainda pode ser retomada com uma escolha válida

### Requirement: Escolha válida retoma o pedido original
SendMessage com taskId da Task pausada e escolha válida SHALL passar a Task para WORKING e retomar o pedido MCP original, não abrir outra reserva com a sala escolhida como novo pedido. O retry SHALL levar a chave de pergunta original, action accept, content.sala, requestState intacto e id JSON-RPC novo. Sucesso SHALL concluir a mesma Task com artifact da reserva resultante.

#### Scenario: Retomada na alternativa escolhida
- **WHEN** o cliente responde escolha=sala-fusca a uma Task pausada que a oferece
- **THEN** a mesma Task termina COMPLETED com artifact referente a sala-fusca e os demais dados originais
- **AND** o log MCP mostra id de retry diferente do request que gerou a pausa

### Requirement: Recusa é processada pelo MCP
`escolha=recusar` SHALL produzir retry com action decline para a pergunta pendente. Após conclusão MCP sem reserva, a Task SHALL terminar TASK_STATE_CANCELED, sem artifact de reserva e sem converter a recusa em falha de execução.

#### Scenario: Cancelamento por recusa
- **WHEN** o cliente recusa uma Task pausada
- **THEN** o MCP recebe decline e a Task termina CANCELED sem reserva criada

### Requirement: Erros ou novas pausas durante retomada
Erro de execução ou protocolo no retry SHALL produzir falha pública da Task sem expor token e sem simular sucesso. Se o MCP devolver novo input_required, o agente SHALL substituir somente a continuação daquela Task e voltar a INPUT_REQUIRED com as novas alternativas.

#### Scenario: Estado expirado entre pausa e escolha
- **WHEN** a escolha chega depois de o requestState expirar e o MCP rejeita o retry
- **THEN** a Task termina FAILED com mensagem pública segura, sem token no erro ou histórico

#### Scenario: Nova escolha necessária
- **WHEN** a disponibilidade mudou e o MCP devolve outra elicitation válida
- **THEN** somente a Task correspondente recebe o novo estado pendente e a nova mensagem de alternativas

### Requirement: Isolamento entre Tasks intercaladas
Duas Tasks pausadas SHALL poder ser retomadas em qualquer ordem sem trocar pedido, responsável, horários, token, chave de pergunta ou contexto de trace. A conclusão de uma não SHALL remover a continuação da outra.

#### Scenario: Duas pausas com intervalos diferentes
- **WHEN** duas Tasks pausam em intervalos distintos e ambas escolhem uma alternativa disponível
- **THEN** cada Task conclui com sua própria reserva, identificadores distintos e os horários e responsáveis corretos

### Requirement: Determinismo da pergunta
Sob o mesmo estado de disponibilidade, pedidos equivalentes que pausam sem criar reserva SHALL produzir texto de alternativas idêntico byte a byte. Identificadores de Task, mensagem e reserva não precisam ser iguais; determinismo não SHALL implicar deduplicação de pedidos que alteram disponibilidade.

#### Scenario: Duas pausas equivalentes
- **WHEN** o mesmo pedido conflitante é enviado duas vezes sem aceitar nenhuma escolha entre eles
- **THEN** as duas Tasks têm identidades distintas e mensagens de alternativas idênticas
