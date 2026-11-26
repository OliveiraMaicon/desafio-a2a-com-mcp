# Proposal

## Why

A capacidade de reservar precisa ser descoberta e consumida por outros agentes sem expor sua implementação MCP. O SDK oficial A2A fornece a fronteira v1.0, enquanto a aplicação mantém o processamento determinístico e o ciclo de vida das Tasks.

## What Changes

- Adotar o SDK oficial A2A Python, em versão exata compatível com v1.0, sem SDK de provedor de LLM.
- Publicar Agent Card em `/.well-known/agent-card.json` e JSON-RPC em `/a2a`, na porta 7300.
- Implementar `SendMessage` e `GetTask` com o parser fixo do desafio.
- Criar e manter Tasks com id, contextId, histórico, transições de estado e artifacts em memória.
- Integrar reservas livres e erros MCP ao host existente; encaminhar traceparent sem estado global compartilhado entre pedidos.
- Impedir retomada de estados terminais e manter o estado privado fora da representação pública.

## Capabilities

### New Capabilities

- `a2a-tasks`: descoberta A2A v1.0, pedidos determinísticos e ciclo de vida público de Tasks para sucesso e falha.

### Modified Capabilities

Nenhuma. A continuação de Tasks pausadas é uma capability separada na próxima change.

## Impact

- Áreas previstas: aplicação, executor e armazenamento em `agente/`, dependências/lock e testes próprios.
- Etapa 5 de 7; aplicar depois de `build-mcp-host`. Próxima: `bridge-task-continuations`.
- Confirmado pelo usuário: Python em ambos os processos e SDK oficial A2A. Armazenamento em memória é o desenho proposto, não uma exigência de persistência adicional.
- Caminhos de conflito são completados na próxima change; esta etapa não deve responder à elicitation sozinha nem fingir reserva concluída.
- Sem streaming público, autenticação, banco, grafo de agentes ou processamento de linguagem natural.
