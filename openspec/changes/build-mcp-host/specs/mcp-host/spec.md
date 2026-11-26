# Spec Delta

## Purpose

Permitir que o agente descubra e consuma o MCP por HTTP, mantendo controle explícito das pausas e retomadas, do contexto de trace e da opacidade do estado de continuação.

## ADDED Requirements

### Requirement: Consumo MCP independente
O host SHALL consumir o servidor MCP por HTTP no endpoint padrão `http://localhost:7301/mcp`. Não SHALL substituir chamadas por imports ou invocações diretas de funções do servidor nem executar regras de sala localmente.

#### Scenario: Reserva depende do servidor remoto
- **WHEN** o host inicia uma reserva
- **THEN** a operação gera um request HTTP MCP observável no servidor separado

### Requirement: Descoberta antes de chamada
Antes do primeiro tools/call, o host SHALL obter tools/list em runtime e conferir a presença e o contrato da tool utilizada. Não SHALL tratar uma lista fixa de schemas como descoberta. Um processo MCP reiniciado ou uma reconexão SHALL poder ser redescoberto sem depender de sessão anterior.

#### Scenario: Ordem de descoberta comprovável
- **WHEN** o host inicia sua primeira reserva após a inicialização
- **THEN** os logs mostram tools/list antes do primeiro tools/call emitido por ele

### Requirement: Versão da política lida do resource
O host SHALL ler politica://uso e extrair a versão da primeira linha. O valor destinado ao artifact SHALL vir dessa leitura, não de constante no agente ou acesso direto ao arquivo do servidor.

#### Scenario: Política fornecida pelo MCP
- **WHEN** o resource retorna `versao: 2026-11-01`
- **THEN** o host disponibiliza 2026-11-01 para o resultado da operação

### Requirement: Metadados e headers completos
Todo request MCP do host SHALL declarar versão `2026-07-28` e clientCapabilities com `elicitation.form` em `_meta`. SHALL enviar MCP-Protocol-Version, Mcp-Method e, para tools/call e resources/read, Mcp-Name coerentes com o corpo.

#### Scenario: Requisitos presentes em cada perna
- **WHEN** o host descobre tools, lê política, chama uma tool ou realiza retry
- **THEN** cada request contém seus próprios metadados e headers válidos

### Requirement: Continuação exposta sem resposta automática
Ao receber input_required, o host SHALL devolver controle à aplicação com a pergunta e o estado pendente intactos. Não SHALL aceitar, recusar ou escolher uma alternativa automaticamente, nem manter a chamada aberta esperando entrada humana.

#### Scenario: Nenhum retry espontâneo
- **WHEN** uma reserva resulta em input_required
- **THEN** o host entrega a continuação pendente e nenhum tools/call adicional acontece até a aplicação fornecer uma resposta explícita

### Requirement: Retomada fiel e identificador novo
Na retomada, o host SHALL repetir nome da tool e argumentos originais, ecoar requestState sem alteração e usar a chave original em inputResponses. Cada retry SHALL receber id JSON-RPC diferente do request anterior, independentemente do id das chamadas A2A futuras. O token não SHALL ser aberto, interpretado ou reconstruído pelo host.

#### Scenario: Escolha encaminhada explicitamente
- **WHEN** a aplicação fornece uma escolha para uma continuação pendente
- **THEN** o próximo request contém a escolha, a chave e o token originais com id novo

### Requirement: Contexto de trace por operação
Quando informado traceparent, todos os requests MCP pertencentes à operação SHALL preservar seu trace-id em `_meta.traceparent`. A continuação SHALL reter o contexto original quando a resposta do usuário não trouxer traceparent. Operações intercaladas não SHALL compartilhar contexto mutável de trace.

#### Scenario: Retomada sem novo header
- **WHEN** uma operação iniciada com traceparent é retomada sem um novo contexto
- **THEN** o retry ainda contém o trace-id da operação inicial

#### Scenario: Duas operações com traces diferentes
- **WHEN** duas operações são executadas de forma intercalada com trace-ids distintos
- **THEN** cada request do host contém o trace-id de sua própria operação

### Requirement: Resultados e falhas preservados
O host SHALL distinguir resultado completo, erro de execução e erro de protocolo. Erros de execução SHALL preservar o texto exato da tool para futura tradução em falha de Task; falhas de transporte ou protocolo não SHALL ser convertidas em reservas bem-sucedidas.

#### Scenario: Mensagem de erro preservada
- **WHEN** o servidor devolve isError verdadeiro com `Sala inexistente: sala-delorean`
- **THEN** o host entrega essa mensagem intacta à aplicação
