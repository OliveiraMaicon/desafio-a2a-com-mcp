# Spec Delta

## Purpose

Permitir escolha explícita de sala alternativa por MRTR, preservando integridade, expiração e reconstrução da reserva sem sessão nem armazenamento de continuações no servidor MCP.

## ADDED Requirements

### Requirement: Alternativas determinadas pelo servidor
Em conflito, o servidor SHALL calcular salas livres no intervalo com capacidade maior ou igual à da sala original, ordenar por capacidade crescente e por id alfabético no empate e limitar a três alternativas. Sem alternativas, SHALL devolver resultado completo com isError verdadeiro e `Sem alternativas disponiveis no intervalo`, sem elicitation.

#### Scenario: Alternativas iniciais ordenadas
- **WHEN** sala-garagem é solicitada em 03/11/2026 das 14:00 às 15:00 em UTC-03:00 com os dados iniciais
- **THEN** as alternativas são sala-fusca e sala-mirante, nessa ordem

#### Scenario: Nenhuma sala elegível
- **WHEN** sala-mirante já está ocupada no intervalo solicitado
- **THEN** o conflito devolve o erro exato de ausência de alternativas sem inputRequests

#### Scenario: Corte de três alternativas
- **WHEN** quatro salas livres atendem à capacidade mínima
- **THEN** somente as três primeiras na ordenação definida são oferecidas

### Requirement: Pausa como resposta MRTR
Um conflito com alternativas e capability suficiente SHALL terminar o request com `resultType: input_required`, um requestState não vazio e exatamente uma entrada em inputRequests. Essa entrada SHALL ser `elicitation/create`, mode form, com schema plano exigindo uma string sala restrita às alternativas; enum ordenado ou const para alternativa única são permitidos. O servidor não SHALL iniciar request para o cliente nem aguardar resposta humana na mesma chamada HTTP.

#### Scenario: Pergunta devolvida ao cliente
- **WHEN** ocorre conflito elegível para escolha
- **THEN** a resposta HTTP termina contendo a elicitation e sua chave atribuída pelo servidor
- **AND** nenhuma reserva é criada antes do retry

### Requirement: Capability form obrigatória
Antes de devolver elicitation, o servidor SHALL exigir `elicitation.form` nas capabilities do request atual. Ausência dessa capability SHALL produzir `-32021`, `data.requiredCapabilities` indicando elicitation form e HTTP 400.

#### Scenario: Elicitation genérica não basta
- **WHEN** um conflito chega com capabilities vazias ou com elicitation sem form
- **THEN** o servidor responde `-32021` com HTTP 400, sem devolver elicitation nem criar reserva

### Requirement: Chave externa e estável
A proteção do requestState SHALL usar segredo externo configurado por `REQUEST_STATE_SECRET`, com pelo menos 32 bytes de chave, sem valor hardcoded. A configuração SHALL rejeitar segredo ausente, malformado ou curto em vez de gerar chave efêmera silenciosamente. O segredo não SHALL aparecer em logs ou respostas.

#### Scenario: Configuração inválida
- **WHEN** o processo inicia sem segredo válido de tamanho suficiente
- **THEN** não disponibiliza um servidor que emita tokens sem proteção estável e informa falha de configuração sem revelar o valor

### Requirement: Integridade e expiração do estado
O requestState SHALL ter integridade verificável e validade de 900 segundos. Estado adulterado, expirado ou de operação incompatível SHALL ser recusado com erro JSON-RPC `-32602`, sem mutação de reservas e sem erro interno 500.

#### Scenario: Adulteração detectada
- **WHEN** o cliente modifica caracteres de um token emitido e tenta retomá-lo
- **THEN** recebe `-32602` e nenhuma reserva é criada

#### Scenario: Estado expirado
- **WHEN** o retry ocorre após a expiração de 900 segundos do token
- **THEN** recebe `-32602` e nenhuma reserva é criada

#### Scenario: Estado vinculado à operação
- **WHEN** um token de reserva é apresentado em uma chamada incompatível
- **THEN** o servidor o rejeita sem executar uma reserva

### Requirement: Reconstrução sem memória de continuação
O estado protegido SHALL transportar tudo que é necessário para reconstruir o pedido, inclusive os argumentos originais e a escolha solicitada. A conclusão não SHALL depender de mapa de continuações do processo anterior. Mantidos o segredo, a identidade do servidor e um intervalo ainda disponível, o retry válido SHALL funcionar após restart do MCP.

#### Scenario: Restart entre os dois requests
- **WHEN** o cliente obtém input_required, reinicia apenas o MCP com a mesma configuração e reenvia o token válido com a escolha
- **THEN** a reserva é concluída sem recuperar continuação de disco ou memória do processo anterior

### Requirement: Retry vinculado ao pedido e à pergunta
O retry SHALL receber inputResponses e requestState dentro de params, com a mesma chave de inputRequests. Os argumentos reenviados SHALL coincidir com os argumentos protegidos; divergências SHALL ser rejeitadas com `-32602` antes de criar reserva. Escolhas aceitas SHALL pertencer às alternativas protegidas e a disponibilidade SHALL ser conferida novamente antes da escrita.

#### Scenario: Aceitação válida
- **WHEN** o cliente repete o pedido original com nova identidade JSON-RPC, chave correta e action accept para uma alternativa ainda livre
- **THEN** recebe resultado complete com a reserva na alternativa e os demais dados do pedido original

#### Scenario: Argumentos adulterados
- **WHEN** o retry altera sala original, horário ou responsável em relação ao pedido protegido
- **THEN** recebe `-32602`, sem reserva com os valores adulterados

#### Scenario: Escolha não oferecida
- **WHEN** um cliente MCP aceita uma sala fora do schema protegido
- **THEN** o servidor recusa a continuação e não cria reserva nessa sala

#### Scenario: Alternativa ficou ocupada
- **WHEN** uma alternativa oferecida é ocupada antes do retry
- **THEN** o servidor não cria sobreposição e devolve nova escolha válida ou erro de execução de ausência de alternativas, conforme a disponibilidade atual

### Requirement: Recusa sem erro de execução
Respostas com action decline ou cancel SHALL concluir com resultType complete, isError ausente ou falso e structuredContent com reservado falso e motivo. Não SHALL criar reserva.

#### Scenario: Usuário recusa a elicitation
- **WHEN** um retry válido contém decline ou cancel para a pergunta pendente
- **THEN** a operação termina normalmente sem reserva e sem isError verdadeiro
