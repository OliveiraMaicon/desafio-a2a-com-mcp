# Proposal

## Why

O agente deve ser um cliente MCP real antes de receber uma interface A2A. Separar esse adaptador permite provar descoberta, leitura da política e controle manual de MRTR sem misturar falhas dos dois protocolos.

## What Changes

- Criar host Python usando o cliente do SDK oficial para falar exclusivamente por HTTP com o MCP.
- Descobrir tools em runtime antes de chamar qualquer tool e extrair a versão de `politica://uso`.
- Declarar elicitation form e metadados em cada request, com headers coerentes e traceparent por operação.
- Expor operações internas de iniciar e retomar que devolvem resultado completo ou continuação pendente, sem responder automaticamente à elicitation.
- Guardar e ecoar o token como valor opaco, preservar argumentos e chave da pergunta e obter novo id no retry.
- Testar o cliente isoladamente, inclusive eventual callback necessário apenas para declaração da capability.

## Capabilities

### New Capabilities

- `mcp-host`: descoberta, leitura de contexto e controle explícito das chamadas e continuações MCP pelo agente.

### Modified Capabilities

Nenhuma. O host consome as capabilities do servidor sem alterar suas regras.

## Impact

- Áreas previstas: `agente/`, dependências Python compartilhadas e testes em `tests/`.
- Etapa 4 de 7; aplicar depois de `implement-secure-mrtr`. Próxima: `expose-a2a-tasks`.
- Não expõe A2A ainda e não cria uma segunda implementação do protocolo MCP.
- Não importa código de `servidor-mcp/`, não interpreta `requestState` e não calcula política, conflitos ou alternativas.
