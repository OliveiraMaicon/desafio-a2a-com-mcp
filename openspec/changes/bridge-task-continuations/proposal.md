# Proposal

## Why

Ter MCP e A2A funcionando separadamente não realiza a ponte: o usuário A2A precisa decidir a escolha solicitada pelo MCP. Esta change conecta os dois ciclos de estado sem bloquear requests, trocar continuações entre Tasks ou vazar o token privado.

## What Changes

- Converter `input_required` em `TASK_STATE_INPUT_REQUIRED` e mensagem exata de alternativas.
- Associar continuação privada a cada Task, separada do armazenamento público do SDK A2A.
- Processar `escolha=<id>` e `escolha=recusar`, mantendo a pausa em escolhas fora do schema.
- Retomar a chamada original com chave e token intactos e id JSON-RPC novo.
- Traduzir sucesso, recusa e falhas do retry em estados e histórico A2A.
- Provar isolamento de duas Tasks pausadas, determinismo das mensagens e ausência do estado opaco em toda resposta pública.

## Capabilities

### New Capabilities

- `task-continuation-bridge`: tradução entre MRTR e Tasks pausadas com continuidade privada por Task.

### Modified Capabilities

Nenhuma. A capability complementa `a2a-tasks` usando o adaptador de `mcp-host`.

## Impact

- Áreas previstas: executor/ponte e armazenamento privado em `agente/`, testes integrados em `tests/`.
- Etapa 6 de 7; aplicar depois de `expose-a2a-tasks`. Próxima: `verify-clean-clone-delivery`.
- Não requer persistência das Tasks após restart do agente; a sobrevivência do token ao restart do MCP já pertence à change de MRTR.
- Não amplia regras de sala no agente, não abre o token e não introduz callbacks esperando entrada humana.
